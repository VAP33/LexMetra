"""
Unit tests for capture_session.py — no database required.
"""

import capture_session as cs
from schema import EvidenceStatus, ImageQuality


def _field(value, confidence=0.9):
    return {"value": value, "confidence": confidence}


def test_bridge_maps_manufacturer_name_to_combined_field():
    classified = {"manufacturer_name": _field("ACME Pvt Ltd, Pune")}
    bridged = cs.bridge_classified_fields(classified)
    assert "manufacturer_name_address" in bridged
    assert bridged["manufacturer_name_address"]["value"] == "ACME Pvt Ltd, Pune"


def test_bridge_maps_expiry_date_to_best_before():
    classified = {"expiry_date": _field("12/2026")}
    bridged = cs.bridge_classified_fields(classified)
    assert bridged["best_before_use_by"]["value"] == "12/2026"


def test_bridge_does_not_overwrite_existing_direct_field():
    classified = {
        "manufacturer_name": _field("wrong source"),
        "manufacturer_name_address": _field("correct direct value"),
    }
    bridged = cs.bridge_classified_fields(classified)
    assert bridged["manufacturer_name_address"]["value"] == "correct direct value"


def test_merge_keeps_higher_confidence_observation():
    accumulated = {"mrp": _field("MRP 45", confidence=0.4)}
    new = {"mrp": _field("MRP Rs 50", confidence=0.9)}
    merged = cs.merge_classified_fields(accumulated, new)
    assert merged["mrp"]["value"] == "MRP Rs 50"


def test_merge_does_not_downgrade_existing_good_reading():
    accumulated = {"mrp": _field("MRP Rs 50", confidence=0.9)}
    new = {"mrp": _field("blurry guess", confidence=0.2)}
    merged = cs.merge_classified_fields(accumulated, new)
    assert merged["mrp"]["value"] == "MRP Rs 50"


def test_compute_coverage_reflects_bridged_fields_not_raw_ocr_names():
    """
    Regression test: coverage must use the SAME field-name bridge as the
    final rule engine (manufacturer_name -> manufacturer_name_address),
    otherwise the capture UI would perpetually report a field as "missing"
    even though it has already been extracted under its OCR name.
    """
    merged_fields = {
        "manufacturer_name": _field("ACME Pvt Ltd, Pune", confidence=0.9),
        "common_name": _field("Refined Wheat Flour", confidence=0.9),
        "net_quantity": _field("100 g", confidence=0.9),
        "mrp": _field("Rs 50", confidence=0.9),
        "mfg_date": _field("08/2026", confidence=0.9),
        "consumer_care": _field("1800-000-000", confidence=0.9),
        "unit_sale_price": _field("Rs 50/100g", confidence=0.9),
    }
    context = {
        "is_imported": False,
        "best_before_applicable": False,  # household, not perishable
        "unit_price_rule_applies": True,
    }
    coverage, missing = cs.compute_coverage("retail", context, merged_fields)
    assert "manufacturer_name_address" not in missing
    assert coverage == 1.0


def test_guidance_reports_sufficient_when_coverage_high():
    quality = ImageQuality(status=EvidenceStatus.USABLE)
    messages = cs.guidance_messages(quality, 0.9, [])
    assert any("sufficient" in m.lower() for m in messages)


def test_guidance_suggests_specific_missing_fields():
    quality = ImageQuality(status=EvidenceStatus.USABLE)
    messages = cs.guidance_messages(quality, 0.3, ["mrp", "common_name"])
    joined = " ".join(messages).lower()
    assert "mrp" in joined or "maximum retail price" in joined


def test_parse_surface_type_unknown_falls_back():
    from schema import SurfaceType
    assert cs.parse_surface_type("front").name == "FRONT"
    assert cs.parse_surface_type("not-a-real-surface") == SurfaceType.UNKNOWN
    assert cs.parse_surface_type(None) == SurfaceType.UNKNOWN
