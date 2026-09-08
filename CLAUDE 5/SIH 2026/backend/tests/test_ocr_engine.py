"""
Tests for `ocr_engine` and the field-extraction invariants in `ocr_extraction`.

Two families, kept visibly separate:

BEHAVIOURAL
    Fusion groups passes over the same pixels, mosaic geometry round-trips,
    region prioritisation ranks declarations above decoration, and the read
    budget accounts for every detected region.

LEGAL-SAFETY INVARIANTS
    These encode the non-negotiable semantics of the whole pipeline. A failure
    here is a correctness failure with legal consequences:
      - NOT_OBSERVED != MISSING, and an unread region is never an absence claim
      - CONFLICTING evidence must never silently become a definitive value
      - low OCR confidence must never itself become non-compliance
      - poor image quality must never itself become non-compliance
      - nothing is averaged, and no reported string is one no engine produced
      - withheld readings are WITHHELD FROM EXTRACTION, never deleted: they stay
        in the observation list and in the provenance, with a stated reason
      - symbology never reaches a text engine, and text sitting on a barcode is
        quarantined rather than trusted
      - a bare length reading such as '17m' must never become a net quantity,
        while a labelled 'Net Quantity: 12 m' still must

THE '17m' REGRESSION IS PROTECTED HERE, AND THE COMMENT MATTERS.
'17m' is REAL INK on dataset image 0 — small print above the barcode on the Bru
jar — and OCR reads it correctly. The defect was never a misread: it was the
extraction layer's unlabelled-quantity fallback promoting a bare length to
`net_quantity`. The guard therefore lives in extraction, and the test asserts
both halves: the bare reading is refused, and the lawfully labelled one is kept.
Goods ARE sold by length in India, so refusing all metres would be its own bug.

Synthetic fixtures here are clearly synthetic and are labelled as such. They
test LOGIC. Real-photo behaviour is measured separately by
`backend/tools/bench_ocr.py`, which is the only thing allowed to make accuracy
claims.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import ocr_engine as oe  # noqa: E402
import ocr_extraction as ox  # noqa: E402
import region_detection as rd  # noqa: E402
from orientation import Orientation  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic fixtures (clearly synthetic; they test logic, not accuracy)
# ---------------------------------------------------------------------------


def _obs(
    text: str,
    bbox=(10, 10, 120, 20),
    confidence: float = 0.9,
    *,
    variant: str = "v0",
    orientation: Orientation = Orientation.DEG_0,
    region_id: str = "r0",
    region_type: rd.RegionType = rd.RegionType.TEXT,
    region_bbox=(0, 0, 200, 200),
    engine=None,
) -> oe.OcrObservation:
    """One synthetic OCR observation with plausible geometry."""
    return oe.OcrObservation(
        text=text,
        bbox=tuple(int(v) for v in bbox),
        confidence=float(confidence),
        engine=engine if engine is not None else oe.OcrEngineName.TESSERACT,
        orientation=orientation,
        variant_name=variant,
        variant_recipe=("synthetic",),
        region_id=region_id,
        region_type=region_type,
        region_bbox=tuple(int(v) for v in region_bbox),
    )


def _line(text: str, bbox=(10, 10, 120, 20), confidence: float = 0.9) -> ox.OcrLine:
    return ox.OcrLine(text=text, bbox=tuple(int(v) for v in bbox), confidence=confidence)


def _text_panel(width: int = 420, height: int = 150) -> np.ndarray:
    """A light BGR panel carrying three lines of legible synthetic declarations."""
    img = np.full((height, width, 3), 244, np.uint8)
    for text, y in (
        ("NET QUANTITY 100 g", 40),
        ("MRP Rs 45.00", 80),
        ("MFD 03/2026", 120),
    ):
        cv2.putText(
            img, text, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (18, 18, 18), 2,
            cv2.LINE_AA,
        )
    return img


def _region(
    bbox,
    region_type: rd.RegionType = rd.RegionType.TEXT,
    confidence: float = 0.8,
    region_id: str = "r",
) -> rd.DetectedRegion:
    return rd.region_from_bbox(
        tuple(int(v) for v in bbox), region_type=region_type, confidence=confidence
    )


# ---------------------------------------------------------------------------
# LEGAL-SAFETY INVARIANTS: withholding is not deletion
# ---------------------------------------------------------------------------


def test_withheld_readings_are_retained_in_observations_and_provenance():
    """
    Withholding a reading from EXTRACTION must never remove it from the record.

    A reading we refuse to extract from is still evidence about the photograph,
    and a reviewer must be able to see it and disagree with us. So the junk
    reading has to appear in `observations`, be absent from `lines`, and be
    listed in the provenance WITH A REASON.
    """
    good = _obs("NET QUANTITY 100 g", bbox=(10, 10, 200, 22))
    junk = _obs("| | |", bbox=(10, 60, 200, 22))

    reading = oe.ImageReading(
        observations=[good, junk],
        region_readings=[],
        detection=rd.DetectionResult(regions=[], image_width=300, image_height=200),
        engines_used=(oe.OcrEngineName.TESSERACT,),
        engine_notes=[],
        recapture_guidance=[],
        conflicts=[],
        elapsed_seconds=0.1,
    )

    assert junk in reading.observations, "the withheld reading was deleted"
    # `.lines` is the adapter handed to the field extractor, so compare on text.
    offered = [line.text for line in reading.lines]
    assert junk.text not in offered, "junk reached the extraction input"
    assert good.text in offered

    prov = reading.provenance()
    assert prov["extractable_observation_count"] == 1
    withheld = prov["withheld_observations"]
    assert len(withheld) == 1
    assert withheld[0]["text"] == "| | |"
    assert withheld[0]["reason"], "a withheld reading must carry a stated reason"
    semantics = str(prov["withholding_semantics"]).lower()
    assert "not_observed" in semantics or "not observed" in semantics
    assert "missing" in semantics


def test_withholding_cannot_create_a_missing_finding():
    """
    "NOT_OBSERVED != MISSING." "Low OCR confidence must NEVER itself become
    legal non-compliance."

    The provenance must say so in words, because the note is what a reviewer or
    an authority actually reads.
    """
    reading = oe.ImageReading(
        observations=[_obs("!!", bbox=(0, 0, 40, 20))],
        region_readings=[],
        detection=rd.DetectionResult(regions=[], image_width=100, image_height=100),
        engines_used=(oe.OcrEngineName.TESSERACT,),
        engine_notes=[],
        recapture_guidance=[],
        conflicts=[],
        elapsed_seconds=0.0,
    )
    semantics = str(reading.provenance()["withholding_semantics"]).lower()
    assert "cannot" in semantics or "never" in semantics
    assert "missing" in semantics


def test_full_text_excludes_junk_but_the_audit_text_keeps_everything():
    """
    Two text views, deliberately: one for extraction, one for audit. Collapsing
    them into one would force a choice between feeding junk to the parser and
    hiding evidence from the reviewer.
    """
    good = _obs("MRP Rs 45.00", bbox=(10, 10, 200, 22))
    junk = _obs("~", bbox=(10, 60, 200, 22))
    reading = oe.ImageReading(
        observations=[good, junk],
        region_readings=[],
        detection=rd.DetectionResult(regions=[], image_width=300, image_height=200),
        engines_used=(oe.OcrEngineName.TESSERACT,),
        engine_notes=[],
        recapture_guidance=[],
        conflicts=[],
        elapsed_seconds=0.0,
    )
    assert "MRP" in reading.full_text
    assert "~" not in reading.full_text
    assert "~" in reading.full_text_audit


# ---------------------------------------------------------------------------
# LEGAL-SAFETY INVARIANTS: the plausibility gate
# ---------------------------------------------------------------------------


def test_read_density_is_orientation_independent():
    """
    Density is characters per glyph-slot along the LONG axis. Using width/height
    instead of long/short would invert the measure for a 90-degree-rotated
    region and quarantine perfectly good vertical declarations.
    """
    horizontal = _obs("NET QUANTITY 100 g", bbox=(0, 0, 200, 24))
    vertical = _obs("NET QUANTITY 100 g", bbox=(0, 0, 24, 200))
    assert horizontal.read_density == pytest.approx(vertical.read_density)


def test_barcode_stripe_readings_are_recognised_as_typographic_noise():
    """
    Real strings observed on dataset image 3's barcode, with the gate that
    actually catches each one. Asserting the SPECIFIC gate matters: it documents
    that the shape gate is three independent checks, and it fails loudly if a
    future change moves a string from one gate to another and back out again.
    """
    cases = {
        # string            gate that must reject it
        "| | | | | [|": "alnum",       # no alphanumerics at all
        "'": "alnum",
        "~ -": "alnum",
        "| 17m": "density",            # 3 chars spread across a 430px-wide box
        "oe IE ai": "density",
        "a le ie:": "density",
    }
    for junk, expected_gate in cases.items():
        obs = _obs(junk, bbox=(0, 0, 430, 30))
        assert not obs.is_plausible_text, f"{junk!r} passed the plausibility gate"

        stripped = junk.strip()
        alnum = sum(1 for ch in stripped if ch.isalnum())
        gate = "alnum" if alnum < oe.MIN_PLAUSIBLE_ALNUM else "density"
        assert gate == expected_gate, (
            f"{junk!r} is now rejected by the {gate} gate, not {expected_gate}"
        )


def test_the_shape_gate_does_not_pretend_to_catch_everything():
    """
    HONESTY TEST. Some junk passes the shape gate, and the design depends on
    knowing which.

    '| U9 028735249' (a barcode's digit row, read as text on image 3) and a bare
    '17m' (real small print on image 0) both look statistically like text. They
    are caught at OTHER layers — the symbology containment quarantine and the
    extraction-layer length guard respectively. If the shape gate ever appears to
    catch them, the gate has been tightened to where it will also start
    discarding real declarations, and the layered defence has been quietly
    replaced by one over-aggressive filter.
    """
    passes_shape_gate = (
        ("| U9 028735249", (0, 0, 430, 30)),
        ("17m", (746, 1320, 33, 16)),
    )
    for text, bbox in passes_shape_gate:
        assert _obs(text, bbox=bbox).is_plausible_text, (
            f"{text!r} is now caught by the shape gate; verify that real "
            "declarations are not being caught with it"
        )


def test_real_declarations_pass_the_plausibility_gate():
    """The gate must be far away from legitimate text, not marginally clear of it."""
    for text in (
        "NET QUANTITY 100 g",
        "MRP Rs. 45.00 (Incl. of all taxes)",
        "Best before 9 months from packaging",
        "500g",
        "Mfd by: ACME Foods Pvt Ltd, Pune 411001",
    ):
        obs = _obs(text, bbox=(0, 0, max(60, len(text) * 12), 26))
        assert obs.is_plausible_text, f"{text!r} was withheld from extraction"
        assert obs.usable_for_extraction


def test_the_density_gate_has_a_wide_measured_margin():
    """
    A gate that only just separates junk from text will drift under any change to
    preprocessing. Both strings are real readings from dataset images, in their
    real boxes.
    """
    junk = _obs("| 17m", bbox=(0, 0, 430, 30)).read_density
    text = _obs(
        "Bru Instant is made from a fine blend", bbox=(0, 0, 509, 34)
    ).read_density
    assert junk < oe.MIN_READ_DENSITY < text, (
        f"gate {oe.MIN_READ_DENSITY} no longer separates junk={junk:.3f} from "
        f"text={text:.3f}"
    )
    assert text > junk * 4.0, f"margin too narrow: junk={junk:.3f} text={text:.3f}"


def test_a_withheld_reading_is_still_a_reading_not_a_zero_confidence_one():
    """
    The gate is about SHAPE, not confidence. Tesseract is perfectly capable of
    reporting high confidence on stripe noise, so gating on confidence alone
    would let it through — and gating text OUT for low confidence would turn a
    blurry photograph into non-compliance.
    """
    confident_junk = _obs("| | | | | [|", bbox=(0, 0, 430, 30), confidence=0.99)
    assert not confident_junk.usable_for_extraction

    faint_text = _obs("NET QUANTITY 100 g", bbox=(0, 0, 220, 24), confidence=0.05)
    assert faint_text.usable_for_extraction, (
        "low confidence must not withhold real text; it is reported WITH its low "
        "confidence instead"
    )


# ---------------------------------------------------------------------------
# LEGAL-SAFETY INVARIANTS: symbology never reaches a text engine
# ---------------------------------------------------------------------------


def test_symbology_regions_are_refused_as_reading_input():
    """
    "Barcode and QR go to the decoder, never to a text engine." Passing one in
    must be an error, not a silently-accepted request.
    """
    image = _text_panel()
    barcode = _region((10, 10, 100, 40), rd.RegionType.BARCODE)
    with pytest.raises(ValueError):
        oe.read_regions(image, [barcode])


def test_text_sitting_on_a_barcode_is_skipped_before_ocr_is_paid_for():
    """
    A text region almost entirely inside a barcode footprint is stripe noise.
    It is skipped, and the skip must be recorded as reduced coverage, NOT as
    guidance blaming the photographer — the photograph is fine, the region is.
    """
    image = _text_panel()
    barcode = _region((100, 20, 200, 90), rd.RegionType.BARCODE)
    on_top = _region((110, 30, 180, 70), rd.RegionType.TEXT)

    readings, calls = oe.read_regions(image, [on_top], symbology_regions=[barcode])
    assert len(readings) == 1
    assert readings[0].observations == []
    assert readings[0].recapture_guidance == [], (
        "skipping a barcode region must not ask the user to retake the photo"
    )
    assert calls == 0, "no OCR call should be paid for a barcode region"


def test_flag_symbology_noise_quarantines_without_deleting():
    """
    Quarantine sets a flag and appends an explanation. It must not drop the
    observation, because the reviewer needs to see what we refused to use.
    """
    inside = _obs("| 17m", bbox=(120, 40, 40, 16))
    outside = _obs("NET QUANTITY 100 g", bbox=(10, 200, 200, 22))
    observations = [inside, outside]

    count = oe.flag_symbology_noise(observations, [(100, 20, 200, 90)])

    assert count == 1
    assert inside.symbology_noise is True
    assert outside.symbology_noise is False
    assert not inside.usable_for_extraction
    assert outside.usable_for_extraction
    assert len(observations) == 2, "quarantine deleted an observation"
    assert any("barcode" in n.lower() or "symbology" in n.lower() for n in inside.notes)


def test_quarantine_is_idempotent():
    """
    It runs once per region reading and again after cross-region fusion, so
    running it twice must not double-count or double-annotate.
    """
    obs = [_obs("| |", bbox=(120, 40, 40, 16))]
    first = oe.flag_symbology_noise(obs, [(100, 20, 200, 90)])
    notes_after_first = tuple(obs[0].notes)
    second = oe.flag_symbology_noise(obs, [(100, 20, 200, 90)])
    assert first == 1
    assert second == 0, "the same reading was quarantined twice"
    assert tuple(obs[0].notes) == notes_after_first


def test_a_reading_merely_near_a_barcode_is_not_quarantined():
    """
    The guard is CONTAINMENT, not proximity. Declarations are routinely printed
    immediately above a barcode — on dataset image 0 the real '17m' print sits
    39px above the barcode's top edge — so a proximity rule would quarantine
    legitimate small print.
    """
    near = _obs("NET WT 100 g", bbox=(100, 0, 120, 18))
    count = oe.flag_symbology_noise([near], [(100, 20, 200, 90)])
    assert count == 0
    assert near.usable_for_extraction


# ---------------------------------------------------------------------------
# LEGAL-SAFETY INVARIANTS: fusion never invents or silently resolves
# ---------------------------------------------------------------------------


def test_a_single_wrong_digit_is_a_conflict_not_a_corroboration():
    """
    THE NUMERIC-AGREEMENT REGRESSION. Found by this test, not by inspection.

    'NET QUANTITY 100 g' and 'NET QUANTITY 700 g' differ by one character out of
    eighteen, so the glyph-similarity ratio is 0.93 — above AGREEMENT_SIMILARITY
    (0.86). Before `readings_agree()` existed, fusion therefore reported these two
    as CORROBORATED and gave the surviving reading a confidence BONUS: two passes
    that flatly disagree about the net quantity were presented as confirming it.

    The quantity IS the declaration. A wrong digit here is not a near-miss, it is
    a different legal fact, and it must reach a human.
    """
    a = _obs("NET QUANTITY 100 g", bbox=(10, 10, 200, 22), confidence=0.9, variant="v1")
    b = _obs("NET QUANTITY 700 g", bbox=(11, 11, 199, 22), confidence=0.8, variant="v2")

    assert oe.text_similarity(a.text, b.text) >= oe.AGREEMENT_SIMILARITY, (
        "fixture no longer exercises the bug: these strings must still be similar"
    )
    assert not oe.readings_agree(a.text, b.text)

    fused, conflicts = oe.fuse_observations([a, b])
    assert fused[0].fusion_state is oe.FusionState.CONFLICTING
    assert fused[0].confidence <= 0.9, "a numeric conflict earned a confidence bonus"
    assert conflicts[0]["numeric_disagreement"] is True
    assert "DIFFERENT NUMBERS" in " ".join(fused[0].notes)


def test_numeric_signature_ignores_known_glyph_confusions():
    """
    The digit check must not manufacture conflicts out of the glyph confusions the
    similarity metric already understands. '1OO' and '100' are the same reading
    seen through a confusable O/0, so they must still corroborate.
    """
    assert oe.numeric_signature("NET QTY 1OO g") == oe.numeric_signature("NET QTY 100 g")
    assert oe.readings_agree("NET QTY 1OO g", "NET QTY 100 g")


def test_numeric_signature_is_ordered_and_keeps_every_run():
    """
    Order and multiplicity matter: '100 g at Rs 45' and '45 g at Rs 100' are
    different declarations, and a set-based signature would call them equal.
    """
    assert oe.numeric_signature("NET 100 g MRP 45") == ("100", "45")
    assert oe.numeric_signature("NET 45 g MRP 100") == ("45", "100")
    assert not oe.readings_agree("NET 100 g MRP 45", "NET 45 g MRP 100")


def test_text_only_readings_still_corroborate_normally():
    """The digit rule must not affect declarations that contain no digits."""
    a = _obs("Mfd by ACME Foods", bbox=(10, 10, 200, 22), variant="v1")
    b = _obs("Mfd by ACME Foods", bbox=(11, 10, 200, 22), variant="v2")
    fused, conflicts = oe.fuse_observations([a, b])
    assert fused[0].fusion_state is oe.FusionState.CORROBORATED
    assert not conflicts


def test_conflicting_readings_are_marked_and_never_silently_resolved():
    """
    "CONFLICTING evidence must NEVER silently become a definitive value."

    Two passes read the same pixels as materially different text. One is
    reported so the text is not lost, but it must be flagged CONFLICTING and
    every rival must be attached.
    """
    a = _obs("NET QUANTITY 100 g", bbox=(10, 10, 200, 22), confidence=0.9, variant="v1")
    b = _obs("NET QUANTITY 700 g", bbox=(11, 11, 199, 22), confidence=0.8, variant="v2")

    fused, conflicts = oe.fuse_observations([a, b])

    assert len(fused) == 1
    winner = fused[0]
    assert winner.fusion_state is oe.FusionState.CONFLICTING
    assert winner.alternatives, "the rival reading was discarded"
    assert any("700" in alt for alt in winner.alternatives)
    assert conflicts, "the conflict was not reported to the caller"


def test_a_conflict_never_produces_a_string_no_engine_read():
    """
    "Never average. Never silently choose." The reported text must be exactly
    one of the inputs — never a merge, an edit distance midpoint, or a
    character-wise vote.
    """
    texts = {"NET QUANTITY 100 g", "NET QUANTITY 700 g", "NEI QUANIIIY 1OO g"}
    candidates = [
        _obs(t, bbox=(10 + i, 10 + i, 200, 22), confidence=0.9 - 0.1 * i, variant=f"v{i}")
        for i, t in enumerate(sorted(texts))
    ]
    fused, _conflicts = oe.fuse_observations(candidates)
    for obs in fused:
        assert obs.text in texts, f"fusion invented {obs.text!r}"


def test_corroboration_cannot_manufacture_certainty():
    """
    Two equally poor reads agreeing are still two poor reads. The bonus is
    bounded, so corroborating 0.2 and 0.2 must not approach 1.0.
    """
    a = _obs("NET QUANTITY 100 g", bbox=(10, 10, 200, 22), confidence=0.2, variant="v1")
    b = _obs("NET QUANTITY 100 g", bbox=(11, 10, 200, 22), confidence=0.2, variant="v2")
    fused, conflicts = oe.fuse_observations([a, b])

    assert len(fused) == 1
    assert fused[0].fusion_state is oe.FusionState.CORROBORATED
    assert not conflicts
    assert fused[0].confidence <= 1.0
    assert fused[0].confidence < 0.6, (
        f"corroboration inflated 0.2+0.2 to {fused[0].confidence:.2f}"
    )
    assert fused[0].confidence > 0.2, "corroboration earned no credit at all"


def test_nothing_is_dropped_for_being_low_confidence():
    """
    "Low OCR confidence must NEVER itself become legal non-compliance."
    Discarding a faint reading is how a present declaration becomes an apparent
    absence, so fusion keeps it and reports the confidence instead.
    """
    faint = _obs("NET QUANTITY 100 g", bbox=(10, 10, 200, 22), confidence=0.01)
    fused, _c = oe.fuse_observations([faint])
    assert len(fused) == 1
    assert fused[0].confidence == pytest.approx(0.01)


def test_readings_at_different_locations_are_not_fused():
    """Distinct declarations must stay distinct; fusion is spatial, not textual."""
    a = _obs("NET QUANTITY 100 g", bbox=(10, 10, 200, 22))
    b = _obs("MRP Rs 45.00", bbox=(10, 300, 200, 22))
    fused, conflicts = oe.fuse_observations([a, b])
    assert len(fused) == 2
    assert not conflicts


def test_single_source_is_reported_as_unconfirmed_not_as_agreement():
    single = _obs("NET QUANTITY 100 g", bbox=(10, 10, 200, 22))
    fused, _c = oe.fuse_observations([single])
    assert fused[0].fusion_state is oe.FusionState.SINGLE_SOURCE
    assert fused[0].corroborated_by == 1


def test_fusion_of_nothing_is_empty_and_not_an_error():
    fused, conflicts = oe.fuse_observations([])
    assert fused == []
    assert conflicts == []


# ---------------------------------------------------------------------------
# LEGAL-SAFETY INVARIANTS: the read budget is coverage, never absence
# ---------------------------------------------------------------------------


def test_unread_regions_are_accounted_for_and_never_treated_as_absence():
    """
    Every detected region must land in exactly one of `to_read` / `not_reached`,
    so the audit trail can state why each area was or was not read. An unread
    area is NOT_OBSERVED.
    """
    regions = [
        _region((0, i * 30, 100, 25), rd.RegionType.TEXT, confidence=0.5 + i * 0.01)
        for i in range(20)
    ]
    to_read, not_reached = oe.select_regions_to_read(regions, 6)

    assert len(to_read) == 6
    assert len(not_reached) == 14
    assert len(set(id(r) for r in to_read) & set(id(r) for r in not_reached)) == 0
    assert len(to_read) + len(not_reached) == len(regions)


def test_overlapping_reads_are_deliberately_not_deduplicated():
    """
    A REGRESSION GUARD for a measured negative result.

    De-duplicating regions that sit inside a region already being read looked
    like a free 36% speedup. Measurement showed it cost 27% of image 7's
    characters and, worse, converted image 0's CONFLICTING prose lines into
    unearned SINGLE_SOURCE readings — overlapping reads are the only source of
    corroboration within one image. See the note above
    `select_regions_to_read()`. If someone reintroduces the optimisation, this
    fails.
    """
    container = _region((0, 0, 400, 400), rd.RegionType.DECLARATION_TEXT, 0.9)
    inside = _region((10, 10, 380, 380), rd.RegionType.LABEL, 0.85)
    to_read, not_reached = oe.select_regions_to_read([container, inside], 14)
    assert len(to_read) == 2, "a contained region was dropped from the read set"
    assert not not_reached


def test_the_read_budget_is_never_zero():
    """A degenerate cap must still read something rather than reading nothing."""
    regions = [_region((0, 0, 100, 25), rd.RegionType.TEXT)]
    for cap in (0, -5):
        to_read, _skipped = oe.select_regions_to_read(regions, cap)
        assert len(to_read) == 1


def test_declarations_outrank_decoration_for_the_limited_budget():
    """
    Priority is type x confidence x log(area). A confident little graphic must
    not displace the dense declaration panel, which is what plain
    confidence-ordering does on real photographs.
    """
    declaration = _region((0, 0, 500, 400), rd.RegionType.DECLARATION_TEXT, 0.55)
    sharp_speck = _region((0, 0, 30, 20), rd.RegionType.UNKNOWN, 0.99)
    to_read, _s = oe.select_regions_to_read([sharp_speck, declaration], 1)
    assert to_read[0].region_type is rd.RegionType.DECLARATION_TEXT


def test_selection_is_deterministic():
    """
    Two runs on the same input must choose the same regions. A nondeterministic
    read set makes an inspection unreproducible, which is disqualifying for
    evidence regardless of accuracy.
    """
    regions = [
        _region((i * 7, i * 11, 100 + i, 25), rd.RegionType.TEXT, confidence=0.7)
        for i in range(12)
    ]
    first, skip_a = oe.select_regions_to_read(list(regions), 5)
    second, skip_b = oe.select_regions_to_read(list(regions), 5)
    assert [r.bbox for r in first] == [r.bbox for r in second]
    assert [r.bbox for r in skip_a] == [r.bbox for r in skip_b]


# ---------------------------------------------------------------------------
# LEGAL-SAFETY INVARIANTS: the '17m' extraction guard
# ---------------------------------------------------------------------------


def test_a_bare_length_reading_never_becomes_a_net_quantity():
    """
    THE '17m' REGRESSION.

    '17m' is real print above the barcode on dataset image 0 and OCR reads it
    correctly. The defect was the unlabelled-quantity fallback promoting it to
    `net_quantity` as 17 metres. A net quantity claim invented from a print code
    is a fabricated declaration, and it could produce a FAIL against a package
    that is in fact compliant.
    """
    for junk in ("17m", "17 m", "42cm", "8 metres"):
        fields = ox.classify_fields([_line(junk, bbox=(746, 1320, 33, 16))])
        net = fields.get("net_quantity") or {}
        assert not net.get("value"), (
            f"{junk!r} was promoted to net_quantity as {net.get('value')!r}"
        )


def test_a_labelled_length_declaration_is_still_extracted():
    """
    Goods ARE lawfully sold by length in India. Refusing every metre reading
    would trade one bug for another, so the guard requires CONTEXT, not a
    blanket ban on the unit.
    """
    fields = ox.classify_fields([_line("Net Quantity: 12 m", bbox=(10, 10, 300, 24))])
    net = fields.get("net_quantity") or {}
    assert net.get("value"), "a labelled length declaration was refused"
    assert "12" in str(net.get("value"))


def test_ordinary_net_quantity_declarations_are_unaffected_by_the_guard():
    """The guard must be narrow. These are the common real-world forms."""
    for text, expect in (
        ("Net Qty. 100 g", "100"),
        ("500g", "500"),
        ("NET WT 1.5 kg", "1.5"),
        ("200 ml", "200"),
        ("Net Weight: 250 gm", "250"),
    ):
        fields = ox.classify_fields([_line(text, bbox=(10, 10, 300, 24))])
        net = fields.get("net_quantity") or {}
        assert net.get("value"), f"{text!r} produced no net quantity"
        assert expect in str(net.get("value")), (
            f"{text!r} extracted {net.get('value')!r}, expected to contain {expect!r}"
        )


def test_extraction_reports_absence_of_a_field_as_not_found_not_as_missing():
    """
    "NOT_OBSERVED != MISSING." The extractor's job ends at "I did not read
    this". Only the deterministic rule engine may decide that a declaration is
    absent, and only after applicability and exemption.
    """
    fields = ox.classify_fields([_line("SOME BRAND NAME", bbox=(10, 10, 200, 24))])
    net = fields.get("net_quantity") or {}
    assert not net.get("value")
    blob = str(fields).upper()
    assert "MISSING" not in blob, (
        "the extraction layer used the word MISSING, which is a legal conclusion "
        "it is not entitled to draw"
    )


# ---------------------------------------------------------------------------
# LEGAL-SAFETY INVARIANTS: the '16.89 gMs' money guard
# ---------------------------------------------------------------------------
#
# Sibling of the '17m' guard above, and found the same way: by dumping what
# extraction ACTUALLY returned for the `images dataset` photographs instead of
# trusting that a field count meant recall.
#
# On dataset image 3 the value line associated with the MRP label was read as
# 'i Pr : 16.89 gMs (Incj Of al] taxes : 40/ f'. The bare branch of `_MONEY_RE`
# matches any two-decimal number with no currency marker, so 16.89 — a mass in
# GRAMS from the nutrition block — became `mrp.numeric_value`.
#
# That number is the numerator of the Rule 6(11) unit-sale-price consistency
# check, so a mass substituted for the retail price can make a correctly priced
# package contradict its own declared unit price: a fabricated FAIL against a
# compliant package.


def test_a_mass_reading_never_becomes_a_price():
    """
    THE '16.89 gMs' REGRESSION, asserted on the exact strings measured from
    dataset image 3 rather than on invented ones.
    """
    for text in (
        "i Pr : 16.89 gMs (Incj Of al] taxes : 40/ f",  # verbatim from image 3
        "16.89 gms",
        "Carbohydrates 573.18 g",
        "Energy 250.00 kcal",
        "Net 500.00 ml",
        "Fat 12.50 %",
    ):
        assert ox._extract_money(text) is None, (
            f"{text!r} yielded a price of {ox._extract_money(text)!r}; a "
            "measurement was accepted as a rupee amount"
        )


def test_the_garbled_mrp_line_from_image_3_is_refused_as_a_value_shape():
    """
    The whole point of the gate: this string must not qualify as a declared MRP.
    Refusal means the field is simply not extracted, which downstream is
    NOT_OBSERVED — never MISSING, and never a FAIL on its own.
    """
    garbled = "i Pr : 16.89 gMs (Incj Of al] taxes : 40/ f"
    assert ox._value_shape("mrp", garbled) is False
    assert ox._value_shape("unit_sale_price", garbled) is False


def test_ordinary_price_declarations_survive_the_money_guard():
    """
    The guard must be narrow, and this is the half that stops it from being a
    recall regression dressed up as a safety fix. `_extract_money` is called on
    the value line ALREADY associated with an MRP label, so the bare '45.00'
    form is the common real-world case and must keep working.
    """
    for text, expect in (
        ("45.00", 45.00),
        ("MRP Rs. 45.00", 45.00),
        ("Rs.120.50", 120.50),
        ("₹ 120", 120.0),
        ("1,250.00", 1250.00),
        ("45.00 per kg", 45.00),  # lawful unit-price form: 'per' intervenes
    ):
        assert ox._extract_money(text) == expect, (
            f"{text!r} extracted {ox._extract_money(text)!r}, expected {expect!r}"
        )


def test_an_explicit_currency_marker_is_not_second_guessed():
    """
    A printed '₹'/'Rs'/'INR' is strong evidence of price-hood. The guard applies
    only to BARE numbers, exactly as the '17m' guard applies only to bare length
    tokens, so a marked amount is trusted even in an odd-looking line.
    """
    assert ox._extract_money("Rs 16.89 gms") == 16.89


def test_scanning_continues_past_a_rejected_measurement():
    """
    Rejecting a candidate must not blind the parser to a real price later in the
    same line, or the guard would cause the very under-extraction it is meant to
    avoid.
    """
    assert ox._extract_money("junk 16.89 gMs then MRP 40.00 only") == 40.00


def test_a_rejected_price_never_becomes_a_numeric_value_on_the_field():
    """
    End-to-end through `classify_fields`: the caller must not attach
    `numeric_value` from a refused candidate, because that attribute — not the
    display string — is what reaches the Rule 6(11) arithmetic.
    """
    fields = ox.classify_fields(
        [_line("MRP", bbox=(10, 10, 60, 24)),
         _line("16.89 gMs", bbox=(10, 40, 120, 24))]
    )
    mrp = fields.get("mrp") or {}
    assert mrp.get("numeric_value") is None, (
        f"a mass reached mrp.numeric_value as {mrp.get('numeric_value')!r}, "
        "which feeds the unit-sale-price check"
    )


# ---------------------------------------------------------------------------
# BEHAVIOURAL: mosaic geometry
# ---------------------------------------------------------------------------


def test_mosaic_tile_maps_a_box_back_into_tile_local_coordinates():
    tile = oe._MosaicTile(plan_index=0, origin=(4, 120), shape=(60, 200))
    assert tile.to_local((14, 130, 30, 12)) == (10, 10, 30, 12)


def test_mosaic_tile_attribution_requires_overlap_not_just_a_row():
    """
    A stray box in the mosaic's right-hand padding shares rows with a tile but
    does not touch it. Attributing it to that tile would place a reading on the
    wrong region of the package.
    """
    tile = oe._MosaicTile(plan_index=0, origin=(0, 100), shape=(50, 120))
    assert tile.contains_line((10, 120, 40, 12)) is True
    assert tile.contains_line((400, 120, 40, 12)) is False   # same rows, no overlap
    assert tile.contains_line((10, 400, 40, 12)) is False    # different rows


def test_tile_scale_is_inverted_before_the_variant_mapping():
    """
    The read path downscales tiles to bound the mosaic, so coordinates come back
    through FOUR inversions and `tile_scale` is the first. A half-scale tile must
    map a box back to double the size.
    """
    tile = oe._MosaicTile(plan_index=0, origin=(0, 0), shape=(50, 100), tile_scale=0.5)
    local = tile.to_local((10, 10, 20, 8))
    inv = 1.0 / tile.tile_scale
    scaled = (
        int(round(local[0] * inv)),
        int(round(local[1] * inv)),
        int(round(local[2] * inv)),
        int(round(local[3] * inv)),
    )
    assert scaled == (20, 20, 40, 16)


def test_cap_long_side_reports_the_scale_it_applied():
    big = np.full((200, 900), 200, np.uint8)
    capped, scale = oe._cap_long_side(big, 300)
    assert max(capped.shape[:2]) <= 300
    assert scale == pytest.approx(300 / 900, rel=0.02)
    # An image already within the cap is returned unscaled.
    small = np.full((50, 80), 200, np.uint8)
    unchanged, unit = oe._cap_long_side(small, 300)
    assert unit == 1.0
    assert unchanged.shape == small.shape


def test_containment_is_a_fraction_of_the_inner_box():
    assert oe._containment((10, 10, 10, 10), (0, 0, 100, 100)) == pytest.approx(1.0)
    assert oe._containment((0, 0, 100, 100), (10, 10, 10, 10)) == pytest.approx(0.01)
    assert oe._containment((500, 500, 10, 10), (0, 0, 100, 100)) == 0.0


# ---------------------------------------------------------------------------
# BEHAVIOURAL: end-to-end on a synthetic panel
# ---------------------------------------------------------------------------


def test_reading_a_synthetic_panel_produces_extractable_text():
    """
    A smoke test through the real reading path: crop, orient, preprocess,
    mosaic, OCR, map back. It asserts the pipeline RUNS and produces usable
    output on legible synthetic text — it makes no accuracy claim, which is the
    benchmark's job.
    """
    image = _text_panel()
    region = _region((0, 0, image.shape[1], image.shape[0]), rd.RegionType.TEXT, 0.9)
    readings, calls = oe.read_regions(image, [region])

    assert len(readings) == 1
    assert calls >= 1
    text = " ".join(o.text for o in readings[0].observations).upper()
    assert "NET" in text or "QUANTITY" in text, f"read nothing usable: {text!r}"


def test_reading_does_not_mutate_the_input_image():
    """
    "The preprocessing pipeline must preserve the ORIGINAL IMAGE unchanged."
    """
    image = _text_panel()
    before = image.copy()
    region = _region((0, 0, image.shape[1], image.shape[0]), rd.RegionType.TEXT, 0.9)
    oe.read_regions(image, [region])
    assert np.array_equal(image, before), "reading modified the source image"


def test_every_observation_carries_full_provenance_back_to_its_region():
    image = _text_panel()
    region = _region((0, 0, image.shape[1], image.shape[0]), rd.RegionType.TEXT, 0.9)
    readings, _calls = oe.read_regions(image, [region])
    for obs in readings[0].observations:
        assert obs.region_id
        assert obs.variant_name
        assert obs.variant_recipe, "no preprocessing recipe recorded"
        assert obs.orientation in tuple(Orientation)
        assert 0.0 <= obs.confidence <= 1.0
        x, y, w, h = obs.bbox
        assert w > 0 and h > 0
        assert 0 <= x <= image.shape[1] and 0 <= y <= image.shape[0]


def test_region_offset_is_applied_to_every_output_bbox():
    """
    Callers whose `image` is itself a crop rely on this to get original-image
    coordinates. A missed offset silently attaches readings to the wrong place.
    """
    image = _text_panel()
    region = _region((0, 0, image.shape[1], image.shape[0]), rd.RegionType.TEXT, 0.9)
    plain, _a = oe.read_regions(image, [region])
    shifted, _b = oe.read_regions(image, [region], region_offset=(1000, 2000))

    if not plain[0].observations or not shifted[0].observations:
        pytest.skip("OCR produced no observations on this synthetic panel")
    assert min(o.bbox[0] for o in shifted[0].observations) >= 1000
    assert min(o.bbox[1] for o in shifted[0].observations) >= 2000


def test_empty_image_is_rejected_rather_than_silently_handled():
    with pytest.raises(ValueError):
        oe.read_image(np.zeros((0, 0, 3), np.uint8))


def test_normalisation_and_similarity_are_symmetric_and_bounded():
    assert oe.normalise_for_comparison("  NET  Qty.  100 g ") == (
        oe.normalise_for_comparison("net qty 100 g")
    )
    a, b = "NET QUANTITY 100 g", "NET QUANTITY 700 g"
    assert oe.text_similarity(a, b) == pytest.approx(oe.text_similarity(b, a))
    assert 0.0 <= oe.text_similarity(a, b) <= 1.0
    assert oe.text_similarity(a, a) == pytest.approx(1.0)
    assert oe.text_similarity("", "") == pytest.approx(1.0) or (
        oe.text_similarity("", "") == 0.0
    )


def test_active_engines_reports_what_actually_ran():
    """
    PaddleOCR is off by default and cannot be installed here. The engine list
    must reflect reality rather than the configured intent, so a report never
    claims an engine that did not run.
    """
    engines, notes = oe.active_engines()
    assert engines, "no OCR engine is available"
    joined = " ".join(notes).lower()
    if not any(getattr(e, "name", "") == oe.OcrEngineName.PADDLEOCR for e in engines):
        assert "paddle" in joined, (
            "PaddleOCR's absence must be stated in the provenance, not left implied"
        )


# ---------------------------------------------------------------------------
# LEGAL-SAFETY INVARIANTS: the nutrition-panel ambiguity guard
# ---------------------------------------------------------------------------
#
# "Never average. Never silently choose."
#
# The unlabelled-quantity fallback used to sort candidate quantities by OCR
# score and take the winner. A nutrition panel is full of bare masses, so on a
# back-of-pack photograph the declared net quantity was effectively decided by
# which nutrition row OCR happened to read most confidently.
#
# Measured on `images dataset` image 3: '16.89 gms' — a nutrition row — was
# promoted to net_quantity at confidence 0.56, ABOVE the 0.55 threshold the rule
# engine uses, so it would have been treated as the declared quantity and fed to
# the Second Schedule pack-size test.


def test_disagreeing_unlabelled_quantities_are_refused_rather_than_ranked():
    """
    Several bare masses that disagree are ambiguity, not evidence. Picking the
    highest-scoring one manufactures a declaration.
    """
    lines = [
        _line("16.89 gms", bbox=(10, 0, 200, 24), confidence=0.70),
        _line("11.68 g", bbox=(10, 40, 200, 24), confidence=0.60),
        _line("5.4 kg", bbox=(10, 80, 200, 24), confidence=0.50),
    ]
    net = ox.classify_fields(lines).get("net_quantity") or {}
    assert not net.get("value"), (
        f"one of several disagreeing bare quantities was chosen: "
        f"{net.get('value')!r}"
    )


def test_a_single_unlabelled_quantity_is_still_extracted():
    """
    The guard must not become a blanket refusal. '500g' alone on a front panel
    is an ordinary declaration and there is nothing to be ambiguous about.
    """
    net = ox.classify_fields([_line("500 g", bbox=(10, 10, 200, 24))]) \
        .get("net_quantity") or {}
    assert net.get("value"), "a single unambiguous bare quantity was refused"
    assert net.get("numeric_value") == 500.0


def test_the_same_quantity_read_twice_is_not_treated_as_a_disagreement():
    """
    Packs print the net quantity on more than one panel. Two readings of the
    SAME value corroborate each other; only differing values are ambiguous.
    """
    lines = [
        _line("500 g", bbox=(10, 0, 200, 24), confidence=0.90),
        _line("500 gms", bbox=(10, 60, 200, 24), confidence=0.80),
    ]
    net = ox.classify_fields(lines).get("net_quantity") or {}
    assert net.get("value"), "duplicate readings of one value were refused"
    assert net.get("numeric_value") == 500.0


def test_labelled_net_quantity_wins_over_unlabelled_nutrition_noise():
    """
    Explicit net-quantity wording is labelled evidence and must be preferred
    even when louder, higher-confidence bare numbers are present.
    """
    lines = [
        _line("16.89 gms", bbox=(10, 0, 200, 24), confidence=0.95),
        _line("11.68 g", bbox=(10, 40, 200, 24), confidence=0.90),
        _line("Net Wt 500 g", bbox=(10, 80, 200, 24), confidence=0.60),
    ]
    net = ox.classify_fields(lines).get("net_quantity") or {}
    assert net.get("numeric_value") == 500.0, (
        f"labelled evidence lost to bare numbers; got {net.get('value')!r}"
    )
