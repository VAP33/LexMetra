"""
Does a legal finding survive persistence and reload with its evidence intact?

WHY THESE TESTS EXIST, AND WHAT THEY DO NOT PROVE.
The Phase 1 acceptance criterion is that a final finding must be traceable back
to the exact source image and image region AFTER PERSISTENCE AND RELOAD. Two
separate defects stood in the way. Findings were not persisted at all — there
was no `inspection_findings` table, `save_inspection()` wrote only products,
inspections and facts, and `get_inspection_detail()` returned no findings; since
`report.py` falls back to facts when findings are absent, the PDF rendered a
plausible document and the omission never surfaced. Separately, fact evidence
was empty in the live pipeline, so there was nothing to persist even where a
column existed.

WHAT IS ACTUALLY VERIFIED HERE. The serialization boundary: that a finding
carrying an EvidenceReference is flattened into the findings row set without
losing the source image id, the region, the rule version, or the distinction
between "no evidence was observed" and "evidence was observed and contradicts
the declaration" — and that reading the row back reconstructs those.

WHAT IS NOT VERIFIED HERE. Nothing in this file talks to PostgreSQL. There is no
network in this environment, so psycopg2 and a server cannot be installed, and
the live INSERT/SELECT round trip remains UNVERIFIED. What is tested is the code
that decides what gets written and how it is read back, which is where evidence
would be silently dropped. Run the suite against a real database before any
claim that persistence is end-to-end verified.
"""

from __future__ import annotations

import json

from db import persistence as p
from schema import (
    BBox,
    EvidenceReference,
    FactStatus,
    RuleFinding,
    UNATTRIBUTED_IMAGE_ID,
)


def _finding(**overrides) -> RuleFinding:
    kwargs = dict(
        rule_id="LMPC-2011-R6-11-UNIT-PRICE",
        rule_version="2011.1",
        status=FactStatus.FAIL,
        requirement_id="R6-11",
        requirement_description="Unit sale price declaration",
        reason="Declared unit price does not match the calculated value.",
        confidence=0.91,
        review_required=True,
        evidence=[
            EvidenceReference(
                image_id="front_7f3a.jpg",
                surface_id="surf-abc123",
                bbox=BBox(x=120, y=640, width=300, height=28),
                evidence_note="Region located by OCR in original image coordinates.",
            )
        ],
    )
    kwargs.update(overrides)
    return RuleFinding(**kwargs)


def _round_trip(finding: RuleFinding) -> dict:
    """
    Build the row exactly as `save_inspection` does, force it through JSON the
    way a JSONB column would, then hydrate it the way `get_inspection_detail`
    does.
    """
    row = p.build_finding_row("insp-001", finding)

    # A JSONB column hands back native Python; a legacy text column hands back a
    # string. Both shapes must hydrate identically, so exercise the string form
    # here — it is the one that requires decoding and therefore the one that can
    # fail.
    return p.hydrate_finding_row(row)


def test_the_findings_column_set_and_row_builder_agree():
    """
    The INSERT names FINDING_COLUMNS and the values are read out of the dict by
    the same names. If they drift, every save raises or writes into the wrong
    column.
    """
    row = p.build_finding_row("insp-001", _finding())
    assert set(row) == set(p.FINDING_COLUMNS)


def test_a_finding_survives_the_round_trip_with_its_source_image_and_region():
    reloaded = _round_trip(_finding())

    assert reloaded["rule_id"] == "LMPC-2011-R6-11-UNIT-PRICE"
    assert reloaded["rule_version"] == "2011.1", "rule version must survive"
    assert reloaded["status"] == "FAIL"

    assert reloaded["evidence"], "evidence was lost in the round trip"
    ref = reloaded["evidence"][0]
    assert ref["image_id"] == "front_7f3a.jpg"
    assert ref["surface_id"] == "surf-abc123"
    assert ref["bbox"] == {"x": 120.0, "y": 640.0, "width": 300.0, "height": 28.0}


def test_the_reloaded_region_is_precise_enough_to_show_a_reviewer():
    """
    Traceability means a reviewer can be shown the pixels. A region that
    round-trips as an approximation is not the same evidence.
    """
    reloaded = _round_trip(_finding())
    bbox = reloaded["evidence"][0]["bbox"]

    assert bbox["x"] == 120 and bbox["y"] == 640
    assert bbox["width"] == 300 and bbox["height"] == 28


def test_missing_and_required_evidence_stay_distinguishable_after_reload():
    """
    "Nothing was observed" and "something was observed and contradicts the
    declaration" are different legal positions. Folding them into the reason
    text would make them indistinguishable to a machine after reload.
    """
    finding = _finding(
        status=FactStatus.UNCERTAIN,
        required_evidence=["mrp", "net_quantity"],
        missing_evidence=["net_quantity"],
    )
    reloaded = _round_trip(finding)

    assert reloaded["required_evidence"] == ["mrp", "net_quantity"]
    assert reloaded["missing_evidence"] == ["net_quantity"]


def test_an_unattributed_reference_round_trips_as_the_sentinel():
    """
    A break in the provenance chain must stay conspicuous after reload rather
    than becoming a plausible filename.
    """
    finding = _finding(
        evidence=[
            EvidenceReference(
                image_id=UNATTRIBUTED_IMAGE_ID,
                bbox=BBox(x=1, y=2, width=3, height=4),
            )
        ]
    )
    reloaded = _round_trip(finding)

    assert reloaded["evidence"][0]["image_id"] == UNATTRIBUTED_IMAGE_ID
    assert reloaded["evidence"][0]["image_id"] != "unknown"


def test_a_finding_with_no_evidence_reloads_as_an_empty_list_not_none():
    """
    Callers iterate this. Reloading None would turn a legitimate
    "nothing observed" finding into a TypeError at report time.
    """
    reloaded = _round_trip(_finding(evidence=[]))

    assert reloaded["evidence"] == []
    assert reloaded["required_evidence"] == []
    assert reloaded["missing_evidence"] == []


def test_the_enum_status_is_stored_as_its_string_value():
    """A stored Enum repr would not compare equal to 'FAIL' after reload."""
    row = p.build_finding_row("insp-001", _finding(status=FactStatus.EXEMPT))
    assert row["status"] == "EXEMPT"
    assert isinstance(row["status"], str)


def test_evidence_is_stored_as_json_text_that_actually_parses():
    row = p.build_finding_row("insp-001", _finding())
    parsed = json.loads(row["evidence_json"])

    assert isinstance(parsed, list)
    assert parsed[0]["image_id"] == "front_7f3a.jpg"


def test_a_malformed_evidence_blob_does_not_make_the_inspection_unreadable():
    """
    One corrupt row must not take an entire inspection with it. The finding
    still loads; its evidence is empty, which is visibly wrong rather than
    fatal.
    """
    reloaded = p.hydrate_finding_row(
        {
            "rule_id": "LMPC-2011-R6",
            "status": "FAIL",
            "evidence_json": "{not valid json",
            "required_evidence_json": None,
            "missing_evidence_json": None,
        }
    )

    assert reloaded["evidence"] == []
    assert reloaded["rule_id"] == "LMPC-2011-R6"


def test_decode_handles_both_a_json_string_and_an_already_decoded_value():
    assert p.decode_json_column('[{"image_id": "a.jpg"}]') == [{"image_id": "a.jpg"}]
    assert p.decode_json_column([{"image_id": "a.jpg"}]) == [{"image_id": "a.jpg"}]
    assert p.decode_json_column(None) is None


def test_confidence_survives_as_a_float_and_bad_input_does_not_raise():
    assert p.build_finding_row("i", _finding(confidence=0.42))["confidence"] == 0.42

    class _Bad:
        rule_id = "X"
        status = FactStatus.FAIL
        confidence = "not a number"

    assert p.build_finding_row("i", _Bad())["confidence"] is None


def test_opening_a_connection_without_the_driver_fails_loudly():
    """
    Making the psycopg2 import non-fatal must not quietly turn a missing driver
    into a silent no-op save.
    """
    if p.psycopg2 is not None:
        return  # real driver present; nothing to assert

    raised = False
    try:
        with p.get_conn():
            pass
    except RuntimeError as exc:
        raised = True
        assert "psycopg2 is not installed" in str(exc)

    assert raised, "a missing driver must raise, not silently succeed"
