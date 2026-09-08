"""
Dedicated legal-decision-safety regression suite.

These tests exist to lock in, as explicit and permanent regressions, the
single most important architectural rule in this project (see
CLAUDE MASTERPROMPT.txt / master spec Part 21):

    VISION extracts evidence.
    The DETERMINISTIC RULE ENGINE makes the compliance decision.

Concretely and testably, that means:
    1. UNCERTAIN evidence can never directly produce a legal FAIL.
    2. NOT_OBSERVED evidence can never directly produce a legal FAIL unless
       the inspection has independently established sufficient package
       coverage (i.e. "not seen" != "not present").
    3. CONFLICTING evidence (independent OCR engines/images disagreeing)
       can never be silently resolved into a confident PASS or FAIL.

Tests 1-2 exercise rule_engine.py directly (no DB required). Test 3
exercises the full bridge from evidence_fusion's CONFLICTING output, through
main._field_to_raw_extraction, into rule_engine.run_inspection - i.e. the
actual code path a real inspection uses, not just the rule engine in
isolation.
"""

from schema import (
    EvidenceStatus,
    FactStatus,
    GeometryType,
    ImageQuality,
    SurfaceObservation,
)
from rule_engine import RawExtraction, run_inspection
from evidence_fusion import classify_multi_engine
from ocr_extraction import OcrLine
from main import _field_to_raw_extraction


def _surface(coverage: float, quality_status: str = "USABLE") -> SurfaceObservation:
    return SurfaceObservation(
        surface_id="s1",
        image_id="img1",
        evidence_coverage=coverage,
        image_quality=ImageQuality(status=EvidenceStatus(quality_status)),
    )


# ---------------------------------------------------------------------------
# 1. UNCERTAIN evidence can never directly produce FAIL
# ---------------------------------------------------------------------------

def test_low_confidence_field_never_fails_only_uncertain():
    extractions = {
        "common_name": RawExtraction(field="common_name", value="maybe flour?", confidence=0.12),
        "mrp": RawExtraction(field="mrp", value="illegible", confidence=0.05),
    }
    result = run_inspection(
        inspection_id="safety-uncertain-1",
        sale_type="retail",
        product_category="household",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=None,
        extractions=extractions,
    )
    statuses = {f.field: f.status for f in result.facts}
    assert statuses.get("common_name") == FactStatus.UNCERTAIN
    assert statuses.get("mrp") == FactStatus.UNCERTAIN
    assert FactStatus.FAIL not in statuses.values()


# ---------------------------------------------------------------------------
# 2. NOT_OBSERVED can never produce FAIL without sufficient coverage
# ---------------------------------------------------------------------------

def test_absent_field_with_low_coverage_is_uncertain():
    result = run_inspection(
        inspection_id="safety-notobserved-low-coverage",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions={},
        captures=[_surface(coverage=0.30)],  # well under the 0.70 threshold
    )
    statuses = {f.field: f.status for f in result.facts}
    assert FactStatus.FAIL not in statuses.values()
    assert FactStatus.UNCERTAIN in statuses.values()


def test_absent_field_with_sufficient_coverage_may_fail():
    """
    The mirror case: once coverage genuinely establishes the surface was
    seen thoroughly and a required declaration is still absent, FAIL becomes
    legitimate. This is not a bug in the invariant - it is the invariant's
    other half ("not seen" != "not present", but "thoroughly seen and still
    absent" IS legally meaningful).
    """
    result = run_inspection(
        inspection_id="safety-notobserved-high-coverage",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions={},
        captures=[_surface(coverage=0.95)],
    )
    statuses = {f.field: f.status for f in result.facts}
    assert FactStatus.FAIL in statuses.values()


def test_absent_field_with_only_low_quality_capture_stays_uncertain():
    """
    High "coverage" claimed on a LOW_QUALITY capture must not count - a bad
    photo cannot be used to justify a confident FAIL for absence.
    """
    result = run_inspection(
        inspection_id="safety-notobserved-badquality",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions={},
        captures=[_surface(coverage=0.95, quality_status="INVALID")],
    )
    statuses = {f.field: f.status for f in result.facts}
    assert FactStatus.FAIL not in statuses.values()


# ---------------------------------------------------------------------------
# 3. CONFLICTING evidence can never silently become a definitive value
# ---------------------------------------------------------------------------

def test_conflicting_ocr_engines_never_resolve_to_confident_pass_or_fail():
    """
    Full real bridge: two OCR engines disagree on MRP. evidence_fusion
    correctly flags this CONFLICTING and reduces confidence - but this test
    proves the safety net in main._field_to_raw_extraction ALSO independently
    forces it below the rule engine's low-confidence threshold, so a
    CONFLICTING field can never end up legally PASS or FAIL even if some
    future change to evidence_fusion's confidence math were to regress.
    """
    tesseract_lines = [OcrLine(text="MRP Rs 149.00", bbox=(0, 0, 150, 20), confidence=0.97)]
    paddle_lines = [OcrLine(text="MRP Rs 449.00", bbox=(0, 0, 150, 20), confidence=0.97)]

    fused = classify_multi_engine({"tesseract": tesseract_lines, "paddleocr": paddle_lines})
    assert fused["mrp"]["verification"] == "CONFLICTING"

    raw = _field_to_raw_extraction("mrp", fused["mrp"])
    assert raw.confidence <= 0.05, "CONFLICTING field must be forced below the low-confidence threshold"

    result = run_inspection(
        inspection_id="safety-conflicting-1",
        sale_type="retail",
        product_category="household",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=None,
        extractions={"mrp": raw},
    )
    statuses = {f.field: f.status for f in result.facts}
    assert statuses.get("mrp") == FactStatus.UNCERTAIN
    assert statuses.get("mrp") != FactStatus.PASS
    assert statuses.get("mrp") != FactStatus.FAIL
