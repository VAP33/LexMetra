"""
Unit tests for backend/regulatory_adapter.py.
Verifies contract preservation, field mapping, absence handling, and status independence.
"""

from datetime import date
from schema import FactStatus, ProductInspection
from regulatory_adapter import build_generic_evidence, evaluate_regulatory_compliance
from localization.models import LocalizedEvidence, LocalizationStatus


def test_build_generic_evidence_preserves_inputs():
    extractions = {
        "mrp": {"value": 150.0, "raw_text": "MRP Rs 150.00", "confidence": 0.95, "surface_id": "face_1"},
        "common_name": {"value": "Biscuits", "raw_text": "Biscuits", "confidence": 0.90, "surface_id": "face_1"},
    }
    # Clone to verify zero mutation
    import copy
    extractions_copy = copy.deepcopy(extractions)

    ev = build_generic_evidence(
        extractions=extractions,
        mrp=150.0,
        net_quantity_value=100.0,
        net_quantity_unit="g",
        is_imported=False,
    )

    assert extractions == extractions_copy
    assert ev.resolve("declared.mrp") == 150.0
    assert ev.resolve("declared.common_name") == "Biscuits"
    assert ev.resolve("declared.net_quantity") == 100.0
    assert ev.resolve("declared.net_quantity.unit") == "g"
    assert ev.context.get("is_imported") is False




def test_evaluate_regulatory_compliance_returns_valid_inspection():
    extractions = {
        "mrp": {"value": 100.0, "raw_text": "MRP Rs 100.00", "confidence": 0.92},
        "net_quantity": {"value": "50 g", "normalized_value": 50.0, "confidence": 0.90},
        "mfg_date": {"value": "01/2026", "confidence": 0.85},
        "best_before_use_by": {"value": "12/2026", "confidence": 0.85},
        "manufacturer_name_address": {"value": "Bakery Pvt Ltd, Mumbai", "confidence": 0.88},
        "consumer_care": {"value": "care@bakery.com", "confidence": 0.85},
        "common_name": {"value": "Cookies", "confidence": 0.95},
    }

    product_inspection, report = evaluate_regulatory_compliance(
        inspection_id="test-insp-001",
        sale_type="retail",
        product_category="packaged_food",
        net_quantity_value=50.0,
        net_quantity_unit="g",
        mrp=100.0,
        extractions=extractions,
        inspection_date=date(2026, 9, 1),
    )

    assert isinstance(product_inspection, ProductInspection)
    assert product_inspection.inspection_id == "test-insp-001"
    assert len(product_inspection.findings) > 0
    assert "IN-LMPC-2011" in (product_inspection.applicable_rule_version or "")
    assert report.ruleset_id == "IN-LMPC-2011"
    assert report.ruleset_version is not None
    # Findings must have both rule_id and status
    for finding in product_inspection.findings:
        assert finding.rule_id is not None
        assert isinstance(finding.status, FactStatus)



def test_missing_mrp_evidence_results_in_failure():
    # Only common_name provided, mandatory MRP is missing
    extractions = {
        "common_name": {"value": "Cookies", "confidence": 0.95},
    }

    product_inspection, report = evaluate_regulatory_compliance(
        inspection_id="test-insp-002",
        sale_type="retail",
        product_category="packaged_food",
        net_quantity_value=None,
        net_quantity_unit=None,
        mrp=None,
        extractions=extractions,
        inspection_date=date(2026, 9, 1),
    )

    assert product_inspection.overall_status == FactStatus.FAIL
    mrp_finding = next((f for f in product_inspection.findings if "MRP" in f.rule_id), None)
    assert mrp_finding is not None
    assert mrp_finding.status in (FactStatus.FAIL, FactStatus.UNCERTAIN)
