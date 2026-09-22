"""
Tests for Structured Temporal Reasoning Engine in LexMetra.
Verifies relative shelf-life endpoint derivation, bidirectional consistency,
and absence of false "expiry missing" conclusions.
"""

import pytest
from temporal_reasoning import (
    compute_derived_endpoint,
    calculate_implied_duration_months,
    resolve_temporal_evidence,
)


def test_relative_endpoint_derivation():
    # 03/2026 + 24 months = 2028-03
    derived = compute_derived_endpoint("2026-03", 24.0, "months")
    assert derived == "2028-03"

    # 2026-05-15 + 180 days
    derived_days = compute_derived_endpoint("2026-05-15", 180.0, "days")
    assert derived_days is not None
    assert derived_days.startswith("2026-11")

    # 2025-01 + 2 years
    derived_years = compute_derived_endpoint("2025-01", 2.0, "years")
    assert derived_years == "2027-01"


def test_implied_duration_calculation():
    # 2026-03 to 2028-03 = 24 months
    dur = calculate_implied_duration_months("2026-03", "2028-03")
    assert dur == 24.0

    # 2026-01 to 2026-07 = 6 months
    dur2 = calculate_implied_duration_months("2026-01", "2026-07")
    assert dur2 == 6.0


def test_resolve_temporal_evidence_relative_best_before():
    # Traya case: MFD = 03/2026, Best Before = 24 months from MFD
    ev = resolve_temporal_evidence(
        mfg_raw="MFG. DATE: 03-2026",
        best_before_raw="Best Before: 24 months from MFD",
    )
    assert "mfg_date" in ev
    assert ev["mfg_date"].absolute_date == "2026-03"

    assert "best_before" in ev
    bb = ev["best_before"]
    assert bb.duration_value == 24.0
    assert bb.derived_date == "2028-03"
    assert bb.derivation_method == "ANCHOR_ADDITION"
    assert bb.contradiction_status == "NONE"


def test_resolve_temporal_evidence_contradiction():
    # Expiry before MFD
    ev = resolve_temporal_evidence(
        mfg_raw="03/2026",
        expiry_raw="03/2025",
    )
    assert ev["expiry_date"].contradiction_status == "EXPIRY_BEFORE_MFD"

    # Declared 24 months but actual dates give 12 months
    ev2 = resolve_temporal_evidence(
        mfg_raw="03/2026",
        expiry_raw="03/2027",
        best_before_raw="24 months from MFD",
    )
    assert ev2["best_before"].contradiction_status == "DURATION_MISMATCH"
