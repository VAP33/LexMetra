"""
Does the report say only what the evidence supports?

WHY THESE TESTS EXIST.
`report.py` printed a closing statement asserting that "Every finding above is
traceable to a versioned rule identifier, the underlying extracted evidence, and
a confidence score" — while the table it rendered contained only the rule id,
status, reason and confidence. No source image, no region, no rule version. The
document made a traceability claim that nothing in the document supported.

Worse, the row source was chosen by `rows_source = findings if findings else
facts`. Because findings were never persisted, that fallback was the branch
always taken in the live path: every generated report rendered extracted FACTS
under a "Rule Findings" heading, beneath a sentence claiming each row was
traceable to a versioned rule. Facts are observations; findings are legal
conclusions. The substitution was silent, and the resulting document looked
entirely plausible, which is why it survived.

WHAT IS VERIFIED HERE. That the section reports what is actually present: that a
located finding prints its source image and region, that an absent region is
disclosed rather than glossed, that the UNATTRIBUTED sentinel stays conspicuous,
that facts standing in for findings are labelled as such, and that the closing
statement is derived from the rows rather than fixed.

WHAT IS NOT VERIFIED HERE. These tests assert the section MODEL, not the drawn
pixels. One test does build a real PDF to prove the renderer consumes the model
without raising, but no test reads text back out of the PDF — there is no PDF
text extractor in this environment. Visually inspect a generated report before
claiming the layout is correct.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import pytest

import report
from report import _NO_EVIDENCE, build_findings_section, build_inspection_report_pdf
from schema import (
    BBox,
    EvidenceReference,
    FactStatus,
    RuleFinding,
    UNATTRIBUTED_IMAGE_ID,
)


def _located_finding(**overrides) -> RuleFinding:
    kwargs = dict(
        rule_id="LMPC-2011-R6-1-MRP",
        rule_version="2011.1",
        status=FactStatus.FAIL,
        reason="Declared MRP is not in the prescribed form.",
        confidence=0.9,
        evidence=[
            EvidenceReference(
                image_id="front_7f3a.jpg",
                surface_id="surf-abc",
                bbox=BBox(x=120, y=640, width=300, height=28),
            )
        ],
    )
    kwargs.update(overrides)
    return RuleFinding(**kwargs)


def _inspection(**overrides) -> dict:
    data = {
        "inspection_id": "insp-001",
        "product_id": "prod-1",
        "product_category": "food",
        "sale_type": "retail",
        "overall_status": "FAIL",
        "findings": [],
        "facts": [],
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# The evidence column: can a reviewer be sent to the pixels?
# ---------------------------------------------------------------------------


def test_a_located_finding_prints_its_source_image_and_region():
    section = build_findings_section(
        _inspection(findings=[_located_finding()])
    )

    cell = section["rows"][0]["evidence"]
    assert "front_7f3a.jpg" in cell, "the source image must be named in the report"
    assert "120" in cell and "640" in cell, "the region origin must be printed"
    assert "300" in cell and "28" in cell, "the region size must be printed"


def test_the_printed_region_is_in_original_image_pixels_not_a_summary():
    """
    The whole point of the region is that a reviewer opens the stored original
    and looks at those coordinates. A relative or rounded figure would not let
    them do that.
    """
    section = build_findings_section(
        _inspection(findings=[_located_finding()])
    )
    assert section["rows"][0]["evidence"] == "front_7f3a.jpg @ (120,640) 300x28px"


def test_a_finding_with_no_evidence_says_so_rather_than_looking_complete():
    section = build_findings_section(
        _inspection(findings=[_located_finding(evidence=[])])
    )
    assert section["rows"][0]["evidence"] == _NO_EVIDENCE


def test_an_unattributed_source_stays_conspicuous_in_the_report():
    """
    A provenance break must be visible to a reader of the printed page, not just
    representable in the data model.
    """
    finding = _located_finding(
        evidence=[
            EvidenceReference(
                image_id=UNATTRIBUTED_IMAGE_ID,
                bbox=BBox(x=1, y=2, width=3, height=4),
            )
        ]
    )
    cell = build_findings_section(_inspection(findings=[finding]))["rows"][0]["evidence"]

    assert "SOURCE IMAGE NOT RECORDED" in cell
    # The raw sentinel is an internal token; it must not be the thing a human
    # is asked to interpret, but it must also not be silently dropped.
    assert cell != _NO_EVIDENCE


def test_a_source_image_without_a_region_is_reported_as_such():
    finding = _located_finding(
        evidence=[EvidenceReference(image_id="back_1c2d.jpg", bbox=None)]
    )
    cell = build_findings_section(_inspection(findings=[finding]))["rows"][0]["evidence"]

    assert "back_1c2d.jpg" in cell
    assert "region not recorded" in cell


def test_evidence_reloaded_from_the_database_renders_identically():
    """
    In the live path the report is built from rows read back out of `evidence_json`,
    which are plain dicts, not EvidenceReference objects. If the report only
    understood the model objects, every real report would show no evidence while
    every test showed evidence.
    """
    from_model = build_findings_section(
        _inspection(findings=[_located_finding()])
    )["rows"][0]["evidence"]

    reloaded = {
        "rule_id": "LMPC-2011-R6-1-MRP",
        "rule_version": "2011.1",
        "status": "FAIL",
        "reason": "Declared MRP is not in the prescribed form.",
        "confidence": 0.9,
        "evidence": [
            {
                "image_id": "front_7f3a.jpg",
                "surface_id": "surf-abc",
                "bbox": {"x": 120.0, "y": 640.0, "width": 300.0, "height": 28.0},
            }
        ],
    }
    from_db = build_findings_section(
        _inspection(findings=[reloaded])
    )["rows"][0]["evidence"]

    assert from_db == from_model


# ---------------------------------------------------------------------------
# Facts must never be presented as findings
# ---------------------------------------------------------------------------


def test_facts_standing_in_for_findings_are_labelled_not_disguised():
    section = build_findings_section(
        _inspection(facts=[{"field": "mrp", "status": "PASS", "confidence": 0.8}])
    )

    assert section["showing_facts"] is True
    assert "Rule Findings" != section["heading"]
    assert "Extracted Facts" in section["heading"]
    assert section["warning"] is not None
    assert "NOT rule findings" in section["warning"]


def test_the_closing_statement_does_not_claim_traceability_for_facts():
    section = build_findings_section(
        _inspection(facts=[{"field": "mrp", "status": "PASS", "confidence": 0.8}])
    )

    closing = section["closing"]
    assert "not legal findings" in closing
    assert "No rule version applies" in closing
    # The old text claimed each row named a versioned rule identifier.
    assert "traceable to a versioned rule identifier" not in closing


def test_real_findings_are_headed_as_findings():
    section = build_findings_section(
        _inspection(findings=[_located_finding()], facts=[{"field": "mrp"}])
    )
    assert section["showing_facts"] is False
    assert section["heading"] == "Rule Findings"
    assert section["warning"] is None


def test_findings_present_are_preferred_over_facts():
    """Facts must not dilute or replace the legal conclusions when both exist."""
    section = build_findings_section(
        _inspection(
            findings=[_located_finding()],
            facts=[{"field": "mrp"}, {"field": "net_quantity"}],
        )
    )
    assert len(section["rows"]) == 1
    assert section["rows"][0]["label"] == "LMPC-2011-R6-1-MRP"


def test_a_database_read_failure_is_disclosed_as_a_warning():
    """
    `get_inspection_detail` sets `findings_unavailable` when the findings SELECT
    fails. A report built from that must not quietly present facts as if the
    evaluation record were intact.
    """
    section = build_findings_section(
        _inspection(
            facts=[{"field": "mrp", "status": "PASS"}],
            findings_unavailable=True,
        )
    )

    assert section["warning"] is not None
    assert "could not be read back" in section["warning"]
    assert "must not be relied upon" in section["warning"]


# ---------------------------------------------------------------------------
# The closing statement is derived, not fixed
# ---------------------------------------------------------------------------


def test_the_closing_statement_counts_findings_that_cannot_be_shown():
    section = build_findings_section(
        _inspection(findings=[_located_finding(), _located_finding(evidence=[])])
    )

    closing = section["closing"]
    assert "1 of 2 findings cannot be shown to a reviewer in context" in closing


def test_a_region_without_a_source_image_also_counts_as_unshowable():
    """
    A region is only actionable if a reviewer knows which photograph it indexes
    into. Counting only the no-evidence-at-all case understated the gap in
    exactly the situation where provenance had broken: the finding printed a
    precise-looking rectangle and the closing statement declared full
    traceability.
    """
    unattributed = _located_finding(
        evidence=[
            EvidenceReference(
                image_id=UNATTRIBUTED_IMAGE_ID,
                bbox=BBox(x=115, y=700, width=420, height=52),
            )
        ]
    )
    section = build_findings_section(
        _inspection(findings=[_located_finding(), unattributed])
    )

    assert section["rows"][0]["locatable"] is True
    assert section["rows"][1]["locatable"] is False
    assert "1 of 2 findings cannot be shown" in section["closing"]


def test_a_source_image_with_no_region_is_not_locatable_either():
    """
    Naming the photograph is not enough. "Somewhere on this label" is not a
    region a reviewer can be pointed at.
    """
    finding = _located_finding(
        evidence=[EvidenceReference(image_id="back_1c2d.jpg", bbox=None)]
    )
    section = build_findings_section(_inspection(findings=[finding]))
    assert section["rows"][0]["locatable"] is False


def test_one_locatable_reference_is_enough_for_the_finding():
    """A finding resting on several observations is showable if any one of them is."""
    finding = _located_finding(
        evidence=[
            EvidenceReference(image_id=UNATTRIBUTED_IMAGE_ID, bbox=None),
            EvidenceReference(
                image_id="front_7f3a.jpg", bbox=BBox(x=1, y=2, width=3, height=4)
            ),
        ]
    )
    section = build_findings_section(_inspection(findings=[finding]))
    assert section["rows"][0]["locatable"] is True
    assert "cannot be shown" not in section["closing"]


def test_the_closing_statement_adds_no_caveat_when_all_findings_are_located():
    section = build_findings_section(
        _inspection(findings=[_located_finding(), _located_finding()])
    )
    assert "cannot be shown" not in section["closing"]


def test_uncertain_is_still_described_as_insufficient_evidence_not_non_compliance():
    """Invariant: UNCERTAIN must never read as a finding of non-compliance."""
    section = build_findings_section(
        _inspection(findings=[_located_finding(status=FactStatus.UNCERTAIN)])
    )
    closing = section["closing"]
    assert "insufficient evidence" in closing
    assert "not a legal determination of non-compliance" in closing


def test_an_empty_inspection_refuses_to_imply_a_determination():
    section = build_findings_section(_inspection())

    assert section["rows"] == []
    assert "should be read as a compliance determination" in section["closing"]


# ---------------------------------------------------------------------------
# Missing evidence stays a distinct legal position on the page
# ---------------------------------------------------------------------------


def test_evidence_that_was_never_observed_is_named_in_the_reason():
    """
    "Nothing was observed" and "something was observed and contradicts the
    declaration" are different legal positions. The reader must not have to
    infer which one produced the status.
    """
    finding = _located_finding(
        status=FactStatus.UNCERTAIN,
        reason="Cannot evaluate.",
        required_evidence=["mrp", "net_quantity"],
        missing_evidence=["net_quantity"],
    )
    reason = build_findings_section(_inspection(findings=[finding]))["rows"][0]["reason"]

    assert "Cannot evaluate." in reason
    assert "net_quantity" in reason
    assert "not observed" in reason


def test_no_missing_evidence_adds_no_noise_to_the_reason():
    reason = build_findings_section(
        _inspection(findings=[_located_finding()])
    )["rows"][0]["reason"]
    assert reason == "Declared MRP is not in the prescribed form."


# ---------------------------------------------------------------------------
# Rule version
# ---------------------------------------------------------------------------


def test_the_rule_version_reaches_the_page():
    """Invariant 17 requires traceability to a rule VERSION, not just a rule id."""
    row = build_findings_section(
        _inspection(findings=[_located_finding()])
    )["rows"][0]
    assert row["rule_version"] == "2011.1"


def test_a_missing_rule_version_is_shown_as_absent_rather_than_omitted():
    row = build_findings_section(
        _inspection(findings=[_located_finding(rule_version=None)])
    )["rows"][0]
    assert row["rule_version"] == "-"


# ---------------------------------------------------------------------------
# The renderer still works
# ---------------------------------------------------------------------------


def test_the_pdf_renders_from_the_section_model_without_raising():
    """
    Proves the drawing code consumes the model. It does NOT prove the layout is
    correct — nothing here reads text back out of the PDF.
    """
    pdf = build_inspection_report_pdf(
        _inspection(
            findings=[
                _located_finding(),
                _located_finding(evidence=[], rule_version=None),
                _located_finding(
                    evidence=[
                        EvidenceReference(
                            image_id=UNATTRIBUTED_IMAGE_ID,
                            bbox=BBox(x=1, y=2, width=3, height=4),
                        )
                    ]
                ),
            ]
        )
    )

    assert pdf.startswith(b"%PDF"), "output is not a PDF"
    assert len(pdf) > 1500, "PDF is implausibly small to contain a findings table"


def test_the_pdf_renders_when_only_facts_exist():
    pdf = build_inspection_report_pdf(
        _inspection(facts=[{"field": "mrp", "status": "PASS", "confidence": 0.8}])
    )
    assert pdf.startswith(b"%PDF")


def test_the_pdf_renders_for_an_empty_inspection():
    assert build_inspection_report_pdf(_inspection()).startswith(b"%PDF")


def test_a_malformed_bbox_does_not_break_the_report():
    """
    A corrupt region must cost the reader that one region, not the whole
    document.
    """
    finding = {
        "rule_id": "LMPC-2011-R6",
        "status": "FAIL",
        "evidence": [{"image_id": "a.jpg", "bbox": {"x": "??", "y": 1}}],
    }
    cell = build_findings_section(_inspection(findings=[finding]))["rows"][0]["evidence"]

    assert "a.jpg" in cell
    assert "region not recorded" in cell


def test_a_non_numeric_confidence_does_not_break_the_report():
    finding = {"rule_id": "R", "status": "FAIL", "confidence": "high"}
    row = build_findings_section(_inspection(findings=[finding]))["rows"][0]
    assert row["confidence"] == "-"


def test_the_disclaimer_still_states_it_is_not_a_legal_determination():
    assert "NOT" in report.DISCLAIMER
    assert "final legal determination" in report.DISCLAIMER


# ---------------------------------------------------------------------------
# The rendered document itself
# ---------------------------------------------------------------------------
#
# Everything above asserts the section MODEL. The acceptance criterion is about
# the document an inspector actually receives, so where a PDF text extractor is
# available these tests read the text back out of the generated PDF. That is how
# the "Rule versionStatus" header collision was caught: the model was correct and
# a bare-string header cell overflowed into the next column at render time,
# which no model-level assertion could have seen.

_PDFTOTEXT = shutil.which("pdftotext")


def _pdf_text(inspection: dict) -> str:
    pdf = build_inspection_report_pdf(inspection)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "r.pdf")
        with open(path, "wb") as handle:
            handle.write(pdf)
        out = subprocess.run(
            [_PDFTOTEXT, "-layout", path, "-"],
            capture_output=True, check=True,
        )
    return out.stdout.decode("utf-8", "replace")


@pytest.mark.skipif(
    _PDFTOTEXT is None,
    reason="pdftotext (poppler-utils) not installed; the rendered PDF cannot be "
           "read back, so only the section model is verified in this environment",
)
def test_the_source_image_and_region_appear_in_the_rendered_pdf():
    text = _pdf_text(_inspection(findings=[_located_finding()]))

    assert "front_7f3a.jpg" in text, "source image did not reach the printed page"
    assert "(120,640)" in text, "region origin did not reach the printed page"
    assert "300x28px" in text, "region size did not reach the printed page"


@pytest.mark.skipif(_PDFTOTEXT is None, reason="pdftotext not installed")
def test_the_rendered_column_headers_do_not_run_together():
    """
    A bare string in a table header cell cannot wrap, so a header wider than its
    column overflows into the neighbouring one and the printed table reads
    "Rule versionStatus".
    """
    text = _pdf_text(_inspection(findings=[_located_finding()]))

    assert "versionStatus" not in text
    assert "FieldRule" not in text
    assert "ReasonEvidence" not in text
    assert "EvidenceConf" not in text


@pytest.mark.skipif(_PDFTOTEXT is None, reason="pdftotext not installed")
def test_the_rendered_pdf_discloses_a_provenance_break():
    finding = _located_finding(
        evidence=[
            EvidenceReference(
                image_id=UNATTRIBUTED_IMAGE_ID,
                bbox=BBox(x=115, y=700, width=420, height=52),
            )
        ]
    )
    text = _pdf_text(_inspection(findings=[finding]))

    # Wrapping may split the phrase across lines, so check the words survive
    # rather than the exact run of text.
    assert "SOURCE IMAGE NOT" in text
    assert "RECORDED" in text
    assert "1 of 1 findings cannot be shown to a reviewer in context" in text


@pytest.mark.skipif(_PDFTOTEXT is None, reason="pdftotext not installed")
def test_the_rendered_pdf_does_not_present_facts_as_rule_findings():
    text = _pdf_text(
        _inspection(facts=[{"field": "mrp", "status": "PASS", "confidence": 0.8}])
    )

    assert "Extracted Facts" in text
    assert "NOT rule findings" in text
    assert "traceable to a versioned rule identifier" not in text


@pytest.mark.skipif(_PDFTOTEXT is None, reason="pdftotext not installed")
def test_the_rendered_pdf_names_evidence_that_was_never_observed():
    finding = _located_finding(
        status=FactStatus.UNCERTAIN,
        reason="Cannot evaluate.",
        required_evidence=["net_quantity"],
        missing_evidence=["net_quantity"],
        evidence=[],
    )
    text = _pdf_text(_inspection(findings=[finding]))

    assert "net_quantity" in text
    assert "not observed" in text
    assert "no evidence recorded" in text

