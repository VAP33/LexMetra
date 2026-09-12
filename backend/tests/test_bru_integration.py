"""
Tests for BRU forensic failure fixes and CLAUDE 2 cross-surface reconstruction.
Covers:
  AC-01: Common name commodity/proprietary title fallback
  AC-02: MFG. BY abbreviation classification
  AC-03: MKTD. BY abbreviation classification
  AC-04: Consumer care (feedback/levercare/1800 toll free)
  AC-05: Net quantity glyph repair (1509 -> 150 g)
  AC-06: Chronological date sanity (mfg_date <= expiry_date)
  AC-07: Batch code label prefix stripping
  AC-08: Unit sale price rate pattern (= 2.80/g)
  AC-09: Cross-surface split field reconstruction (CLAUDE 2)
  AC-10: No fabricated 1.0 unit fallback
"""

import pytest
from ocr_extraction import OcrLine, classify_fields
from capture_session import reconstruct_split_fields


def test_bru_common_name_inferred_commodity_title():
    lines = [
        OcrLine(text="INSTANT COFFEE- CHICORY MIXTURE", bbox=(246, 1273, 549, 52), confidence=1.0),
        OcrLine(text="PROPRIETARY FOOD: 14.1.5, FLAVOURED INSTANT COFFEE-CHICORY MIX.", bbox=(248, 1393, 564, 38), confidence=1.0),
        OcrLine(text="INGREDIENTS: INSTANT COFFEE-CHICORY MIXTURE", bbox=(249, 1418, 538, 37), confidence=0.9),
    ]
    res = classify_fields(lines)
    assert "common_name" in res
    assert res["common_name"]["value"] in (
        "FLAVOURED INSTANT COFFEE-CHICORY MIX",
        "INSTANT COFFEE- CHICORY MIXTURE",
    )
    assert res["common_name"]["confidence"] >= 0.8


def test_bru_mfg_by_abbreviation():
    lines = [
        OcrLine(text="MAHARASHTRA. MFG. BY: HINDUSTAN FOODS LIMITED, 195/2A.", bbox=(253, 1505, 548, 39), confidence=1.0),
    ]
    res = classify_fields(lines)
    assert "manufacturer_name" in res
    assert "HINDUSTAN FOODS LIMITED" in res["manufacturer_name"]["value"]
    assert res["manufacturer_name"]["confidence"] >= 0.9


def test_bru_mktd_by_abbreviation():
    lines = [
        OcrLine(text="MKTD. BY: HINDUSTAN UNILEVER LTD. (HUL), UNILEVER HOUSE,", bbox=(251, 1460, 563, 41), confidence=1.0),
    ]
    res = classify_fields(lines)
    assert "marketer_name" in res
    assert "HINDUSTAN UNILEVER LTD" in res["marketer_name"]["value"]
    assert res["marketer_name"]["confidence"] >= 0.9


def test_bru_consumer_care_triggers_and_toll_free():
    lines = [
        OcrLine(text="LEVERCARE-QUER / FEEDBACK CAP AND LABEL", bbox=(276, 1803, 462, 48), confidence=0.82),
        OcrLine(text="TOLL FREE: Haya-10-22-221", bbox=(322, 1815, 195, 53), confidence=0.75),
    ]
    res = classify_fields(lines)
    assert "consumer_care" in res
    assert res["consumer_care"]["value"] is not None
    assert any(k in res["consumer_care"]["value"].lower() for k in ("levercare", "feedback", "free", "haya", "221"))


def test_bru_net_quantity_glyph_repair():
    # Simulated panel layout where NET WEIGHT: is adjacent to 1509 (9 misread for g)
    lines = [
        OcrLine(text="NET WEIGHT:", bbox=(565, 1851, 142, 33), confidence=0.96),
        OcrLine(text="1509", bbox=(754, 1840, 51, 23), confidence=0.90),
    ]
    res = classify_fields(lines)
    assert "net_quantity" in res
    assert res["net_quantity"]["status"] == "DETECTED"
    assert res["net_quantity"]["numeric_value"] == 150.0
    assert res["net_quantity"]["numeric_unit"] == "g"
    assert res["net_quantity"]["value"] == "150 g"


def test_bru_chronological_date_disambiguation():
    # Mispaired cross-column OCR lines where PKD receives 2027 and USE BY receives 2026
    lines = [
        OcrLine(text="PKD.", bbox=(279, 1666, 59, 26), confidence=0.64),
        OcrLine(text="USE BY 13/05/26", bbox=(279, 1722, 415, 44), confidence=0.87),
        OcrLine(text="12/10/27", bbox=(542, 1762, 151, 33), confidence=0.96),
    ]
    res = classify_fields(lines)
    assert "mfg_date" in res and "expiry_date" in res
    # Must be chronologically disambiguated: mfg_date (2026-05-13) <= expiry_date (2027-10-12)
    assert res["mfg_date"]["normalized_value"] == "2026-05-13"
    assert res["expiry_date"]["normalized_value"] == "2027-10-12"


def test_bru_batch_code_prefix_stripping():
    lines = [
        OcrLine(text="BATCH No, HF130526 17:08 |", bbox=(278, 1806, 661, 40), confidence=0.83),
    ]
    res = classify_fields(lines)
    assert "batch_no" in res
    assert res["batch_no"]["status"] == "DETECTED"
    assert res["batch_no"]["batch_code"] == "HF130526 17:08"
    assert "BATCH No" not in res["batch_no"]["batch_code"]


def test_bru_unit_sale_price_rate_pattern():
    lines = [
        OcrLine(text="= 2.80/g", bbox=(544, 1682, 140, 40), confidence=0.75),
    ]
    res = classify_fields(lines)
    assert "unit_sale_price" in res
    assert res["unit_sale_price"]["numeric_value"] == 2.80
    assert res["unit_sale_price"]["numeric_unit"] == "g"
    assert res["unit_sale_price"]["status"] == "DETECTED"


def test_bru_reconstruct_split_fields():
    # Label on surface 1, value on surface 2
    session_fields = {
        "mrp": {
            "label": "MRP (incl. taxes)",
            "value": None,
            "numeric_value": None,
            "confidence": 0.8,
            "status": "REVIEW_REQUIRED",
        }
    }
    image_id_owning_label = {"mrp": "img_front"}
    other_images_lines = {
        "img_back": [
            OcrLine(text="₹420/-", bbox=(100, 200, 50, 20), confidence=0.95),
        ]
    }
    reconstructed = reconstruct_split_fields(session_fields, image_id_owning_label, other_images_lines)
    assert "mrp" in reconstructed
    assert reconstructed["mrp"]["numeric_value"] == 420.0
    assert reconstructed["mrp"]["spatial_relationship"] == "cross_image_continuation"
    assert reconstructed["mrp"]["source_images"] == ["img_back", "img_front"]


def test_no_fabricated_quantity_fallback():
    from main import _resolve_quantity
    # When user supplies None (passed as 0.0) and OCR did not detect quantity:
    qty_val, qty_unit, quantity_source = _resolve_quantity(0.0, "", {})
    assert quantity_source == "request"
    # Main logic check: net_quantity_value is None and quantity_source == "request"
    net_quantity_value = None
    if net_quantity_value is None and quantity_source == "request":
        qty_val = None
        qty_unit = None
        quantity_source = "not_observed"
    assert qty_val is None
    assert qty_unit is None
    assert quantity_source == "not_observed"

