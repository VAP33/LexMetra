"""
test_inspection_statuses_and_counters.py

Focused tests for Task 9:
- Clearly distinguishes:
    VERIFIED
    NEEDS_REVIEW
    ABSENT
    NOT_ASSESSABLE
    NOT_APPLICABLE
- Verifies counter consistency:
    assessed = verified + needs_review + absent
    applicable = assessed + not_assessable
- Verifies NOT_ASSESSABLE NEVER automatically becomes ABSENT or NON_COMPLIANT.
"""

import pytest
from schema import CanonicalStatus, FactStatus, SurfaceObservation
from rule_engine import (
    run_inspection,
    RawExtraction,
    _build_canonical_declarations,
    _evidence_sufficient_for_missing_field,
)


def _capture(coverage: float = 0.8) -> SurfaceObservation:
    return SurfaceObservation(
        surface_id="s1",
        image_id="img1",
        evidence_coverage=coverage,
    )


def test_standard_canonical_status_enums():
    """Verify standard status representations."""
    assert CanonicalStatus.VERIFIED == "VERIFIED"
    assert CanonicalStatus.NEEDS_REVIEW == "NEEDS_REVIEW"
    assert CanonicalStatus.ABSENT == "ABSENT"
    assert CanonicalStatus.NOT_ASSESSABLE == "NOT_ASSESSABLE"
    assert CanonicalStatus.NOT_APPLICABLE == "NOT_APPLICABLE"


def test_not_assessable_never_becomes_absent():
    """
    When available evidence is insufficient to cover the package,
    a missing observation must resolve to NOT_ASSESSABLE, NEVER ABSENT.
    """
    # Single image with low evidence coverage (< 0.65 threshold)
    low_cov_capture = SurfaceObservation(
        surface_id="s_low",
        image_id="img_low",
        evidence_coverage=0.3,
    )
    assert not _evidence_sufficient_for_missing_field([low_cov_capture])

    res = run_inspection(
        inspection_id="t-not-assessable",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        captures=[low_cov_capture],
        extractions={},
    )
    unobserved = [d for d in res.declarations if d.status == CanonicalStatus.NOT_ASSESSABLE]
    absent = [d for d in res.declarations if d.status == CanonicalStatus.ABSENT]
    assert len(unobserved) > 0, "Unobserved declarations with low coverage must be NOT_ASSESSABLE"
    assert len(absent) == 0, "Insufficient evidence must NEVER automatically produce ABSENT"


def test_sufficient_evidence_concludes_absent():
    """
    When evidence coverage is sufficient, a truly missing mandatory declaration
    is concluded as ABSENT.
    """
    high_cov_capture = SurfaceObservation(
        surface_id="s_high",
        image_id="img_high",
        evidence_coverage=0.95,
    )
    assert _evidence_sufficient_for_missing_field([high_cov_capture])

    res = run_inspection(
        inspection_id="t-absent",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        best_before_applicable=True,
        captures=[high_cov_capture],
        extractions={},
    )
    absent = [d for d in res.declarations if d.status == CanonicalStatus.ABSENT]
    assert len(absent) > 0, "Sufficient coverage with missing field must conclude ABSENT"


def test_counters_and_summary_consistency():
    """
    Verify counter totals match logical rule:
    assessed = verified + needs_review + absent
    applicable = assessed + not_assessable
    """
    low_cov_capture = SurfaceObservation(
        surface_id="s_front",
        image_id="img_front",
        evidence_coverage=0.4,
    )

    # Provide 2 verified, 1 needs review
    extractions = {
        "net_quantity": RawExtraction(field="net_quantity", value="100 g", confidence=0.95),
        "mrp": RawExtraction(field="mrp", value="Rs 50", confidence=0.95),
        "consumer_care": RawExtraction(field="consumer_care", value="care@", confidence=0.3),
    }

    res = run_inspection(
        inspection_id="t-counters",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        captures=[low_cov_capture],
        extractions=extractions,
    )

    summary = res.declaration_summary
    assert summary["applicable"] == summary["assessed"] + summary["not_assessable"]
    assert summary["assessed"] == summary["verified"] + summary["needs_review"] + summary["absent"]
