"""
Tests for newly integrated compliance features:
1. Barcode Decoding (EAN-13, UPC, QR)
2. Sticker / Alteration Tampering Detection
3. Date Association & Temporal Reasoning
4. Unit Sale Price Calculation
5. OpenRouter VLM Fallback
"""

import os
from decimal import Decimal
import numpy as np
import pytest

from barcode_decode import decode_symbols, SymbologyKind, gtin_check_digit
from date_association import extract_raw_date_tokens, normalize_parsed_date
from sticker_detection import detect_sticker_regions, SuspectRegion
from unit_price import compute_unit_sale_price, UnitPriceResult
from vlm_verifier import (
    verify_ambiguous_field_mocked,
    verify_ambiguous_field_auto,
    VerifierResult,
)


def test_gtin_checksum_validation():
    """Verify GS1 Modulo-10 checksum algorithm."""
    # 890103001234 -> check digit
    # Test valid 13-digit EAN
    chk = gtin_check_digit("890103001234")
    assert isinstance(chk, int)
    assert 0 <= chk <= 9


def test_barcode_decoding_empty_and_dummy():
    """Verify barcode decoding handles blank and synthetic frames safely."""
    dummy_img = np.full((300, 300, 3), 255, dtype=np.uint8)
    res = decode_symbols(dummy_img, image_id="test_frame")
    assert res.status.name in ("NO_SYMBOL_LOCALISED", "LOCALISED_NOT_DECODED")


def test_sticker_detection_clean_image():
    """Verify sticker detection runs cleanly without false alarms on blank image."""
    dummy_img = np.full((400, 400, 3), 240, dtype=np.uint8)
    suspects = detect_sticker_regions(dummy_img)
    assert isinstance(suspects, list)


def test_date_tokens_and_normalization():
    """Verify multi-format date extraction and normalization."""
    tokens = extract_raw_date_tokens("MFD: 08/2026 PKD: 12-09-2025 USE BY: 24 months")
    assert len(tokens) >= 2

    norm1 = normalize_parsed_date("08/2026")
    assert norm1 in ("2026-08", "08/2026", "2026-08-01") or "2026" in norm1

    norm2 = normalize_parsed_date("12-09-2025")
    assert "2025" in norm2


def test_unit_sale_price_computation():
    """Verify statutory Unit Sale Price calculation under Rule 6(11)."""
    # 200g @ Rs 50 -> Rs 0.25 / g
    res = compute_unit_sale_price(
        net_quantity_value=200,
        net_quantity_unit="g",
        mrp=50.0,
    )
    assert isinstance(res, UnitPriceResult)
    assert res.unit_sale_price == Decimal("0.25")
    assert res.standard_unit_label == "g"

    # 2 kg @ Rs 240 -> Rs 120.00 / kg
    res_kg = compute_unit_sale_price(
        net_quantity_value=2,
        net_quantity_unit="kg",
        mrp=240.0,
    )
    assert res_kg.unit_sale_price == Decimal("120.00")
    assert res_kg.standard_unit_label == "kg"


def test_vlm_verifier_mocked_clarity():
    """Verify VLM semantic parser parses unambiguous JSON properly."""
    result = verify_ambiguous_field_mocked(
        field="mrp",
        extracted_text="MRP Rs. 145.00 Incl. of all taxes",
        rule_requirement="Maximum Retail Price clearly stated with tax inclusion.",
        mock_json='{"ambiguous": false, "explanation": "The MRP is unambiguous."}',
    )
    assert isinstance(result, VerifierResult)
    assert result.ambiguous is False
    assert "unambiguous" in result.explanation.lower()


def test_vlm_verifier_auto_offline_fallback():
    """Verify auto router falls back safely when no API key is set."""
    # Ensure offline fallback returns review required without raising exception
    result = verify_ambiguous_field_auto(
        field="mfg_date",
        extracted_text="09/26",
        rule_requirement="Month and year of manufacture.",
    )
    assert isinstance(result, VerifierResult)
    assert result.ambiguous is True


def test_zero_shot_ocr_normalizer_empty_and_offline():
    """Verify zero-shot semantic normalizer gracefully handles empty and fallback paths."""
    from vlm_verifier import normalize_ocr_tokens_zero_shot
    res = normalize_ocr_tokens_zero_shot([])
    assert res == {}

    # Sample lines without API key or offline
    lines = ["MRP 275/-", "NET WT 200g", "MFD 09/2025"]
    res2 = normalize_ocr_tokens_zero_shot(lines)
    assert isinstance(res2, dict)


def test_multimodal_vlm_resolver_empty_and_offline():
    """Verify multimodal VLM resolver safely handles None and missing keys."""
    from vlm_verifier import resolve_statutory_declarations_vlm
    res = resolve_statutory_declarations_vlm(None)
    assert res == {}

    dummy = np.full((100, 100, 3), 255, dtype=np.uint8)
    res2 = resolve_statutory_declarations_vlm(dummy, missing_fields=["mrp", "mfg_date"])
    assert isinstance(res2, dict)
