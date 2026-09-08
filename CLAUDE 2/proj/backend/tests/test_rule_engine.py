"""
Unit tests for rule_engine.py — no database required.

These tests exercise the core legal-engine principle directly:
    sufficient positive evidence -> PASS
    sufficient evidence of absence -> FAIL
    insufficient evidence -> UNCERTAIN
    scope exemption -> EXEMPT
"""

from schema import FactStatus, MeasurementMode
from rule_engine import RawExtraction, run_inspection


def _extraction(value, confidence=0.9):
    return RawExtraction(field="x", value=value, confidence=confidence)


def test_export_only_package_is_exempt():
    result = run_inspection(
        inspection_id="t-exempt-1",
        sale_type="export",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions={},
        is_export_only=True,
    )
    assert result.overall_status == FactStatus.EXEMPT
    assert result.exempt_reason


def test_well_evidenced_retail_declarations_pass():
    extractions = {
        "manufacturer_name_address": _extraction("ACME Pvt Ltd, Pune"),
        "common_name": _extraction("Refined Wheat Flour"),
        "net_quantity": _extraction("100 g"),
        "mrp": _extraction("MRP Rs 50"),
        "mfg_date": _extraction("08/2026"),
        "consumer_care": _extraction("1800-000-000"),
        "unit_sale_price": _extraction("Rs 50 per 100 g"),
    }
    result = run_inspection(
        inspection_id="t-pass-1",
        sale_type="retail",
        product_category="household",  # not perishable -> best_before not required
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions=extractions,
    )
    statuses = {f.field: f.status for f in result.facts}
    assert statuses.get("manufacturer_name_address") == FactStatus.PASS
    assert statuses.get("common_name") == FactStatus.PASS


def test_missing_declaration_without_sufficient_coverage_is_uncertain_not_fail():
    """
    Critical legal-safety invariant: absence of OCR evidence with no capture
    coverage information must NOT be treated as proof of non-compliance.
    """
    result = run_inspection(
        inspection_id="t-uncertain-1",
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions={},  # nothing extracted, no captures supplied
    )
    statuses = {f.field: f.status for f in result.facts}
    # Every required Rule 6 field should be UNCERTAIN, never FAIL, when there
    # is no capture-coverage evidence to justify a FAIL.
    assert FactStatus.FAIL not in statuses.values()
    assert FactStatus.UNCERTAIN in statuses.values()
    assert result.overall_status == FactStatus.UNCERTAIN


def test_low_confidence_extraction_is_uncertain_not_pass():
    extractions = {
        "common_name": _extraction("possibly flour??", confidence=0.1),
    }
    result = run_inspection(
        inspection_id="t-lowconf-1",
        sale_type="retail",
        product_category="household",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=50,
        extractions=extractions,
    )
    common_name_facts = [f for f in result.facts if f.field == "common_name"]
    assert common_name_facts
    assert common_name_facts[0].status == FactStatus.UNCERTAIN


def test_wholesale_sale_type_evaluates_rule24_not_rule6():
    extractions = {
        "manufacturer_name": _extraction("ACME Foods Pvt Ltd, Pune"),
        "common_name": _extraction("Refined Wheat Flour"),
        "wholesale_count_or_net_quantity": _extraction("5000 g"),
    }
    result = run_inspection(
        inspection_id="t-wholesale-1",
        sale_type="wholesale",
        product_category="food",
        net_quantity_value=5000,
        net_quantity_unit="g",
        mrp=None,
        extractions=extractions,
    )
    rule_ids = {f.rule_id for f in result.facts if f.rule_id}
    assert "LMPC-2011-R24-WHOLESALE" in rule_ids
    assert "LMPC-2011-R6-DECLARATIONS" not in rule_ids


def test_invalid_net_quantity_raises():
    import pytest

    with pytest.raises(ValueError):
        run_inspection(
            inspection_id="t-invalid-1",
            sale_type="retail",
            product_category="food",
            net_quantity_value=0,
            net_quantity_unit="g",
            mrp=50,
            extractions={},
        )
