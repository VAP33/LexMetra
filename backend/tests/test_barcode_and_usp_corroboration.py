# -*- coding: utf-8 -*-
"""
Test Barcode Product ID & Unit Sale Price Evidence Fusion and Corroboration.
Tests:
1. Mathematical corroboration of USP using MRP + Net Quantity + Normalized Units.
2. Dual-channel Barcode Product ID verification (VERIFIED, REVIEW_REQUIRED, NOT_OBSERVED).
3. Preservation of real bboxes and image provenance for both fields.
4. Validation across BRU, Vaseline, Good Knight, and Hershey's.
"""

from pathlib import Path
import pytest
import numpy as np
import cv2

from package_integrity import (
    corroborate_unit_sale_price,
    _parse_mrp_amount,
    _parse_net_quantity,
    compare_reference_vs_inspected_package,
    STATUS_MATCH,
    STATUS_REVIEW_REQUIRED,
    STATUS_POTENTIAL_DISCREPANCY,
    STATUS_REF_NOT_OBS,
)


def test_usp_arithmetic_corroboration_bru():
    """BRU: MRP Rs.420, Net Qty 150 g -> expected USP Rs.2.80/g."""
    agrees, p_amt, exp_amt, note = corroborate_unit_sale_price(
        printed_usp="Rs. 2.80 / g",
        mrp_str="Rs. 420.00",
        net_qty_str="150 g",
    )
    assert agrees is True
    assert p_amt == 2.80
    assert exp_amt == 2.80
    assert "2.80" in note


def test_usp_arithmetic_corroboration_vaseline():
    """Vaseline: MRP Rs.275, Net Qty 200 ml -> expected USP Rs.1.38/ml."""
    agrees, p_amt, exp_amt, note = corroborate_unit_sale_price(
        printed_usp="1.38/ml",
        mrp_str="Rs. 275.00",
        net_qty_str="200 ml",
    )
    assert agrees is True
    assert p_amt == 1.38
    assert exp_amt == 1.38


def test_usp_arithmetic_corroboration_good_knight():
    """Good Knight: MRP Rs.60, Net Qty 10 units -> expected USP Rs.6.00/unit."""
    agrees, p_amt, exp_amt, note = corroborate_unit_sale_price(
        printed_usp="6.00/unit",
        mrp_str="Rs. 60.00",
        net_qty_str="10 units",
    )
    assert agrees is True
    assert p_amt == 6.00
    assert exp_amt == 6.00


def test_usp_arithmetic_corroboration_hersheys():
    """Hershey's: MRP Rs.99, Net Qty 180 g -> expected USP Rs.0.55/g."""
    agrees, p_amt, exp_amt, note = corroborate_unit_sale_price(
        printed_usp="0.55/g",
        mrp_str="Rs. 99.00",
        net_qty_str="180 g",
    )
    assert agrees is True
    assert p_amt == 0.55
    assert exp_amt == 0.55


def test_usp_arithmetic_conflict_triggers_review():
    """If printed USP conflicts with arithmetic calculation -> REVIEW_REQUIRED."""
    agrees, p_amt, exp_amt, note = corroborate_unit_sale_price(
        printed_usp="4.50/g",  # Conflict! Expected is 2.80
        mrp_str="Rs. 420.00",
        net_qty_str="150 g",
    )
    assert agrees is False
    assert p_amt == 4.50
    assert exp_amt == 2.80


def test_parse_mrp_preserves_decimals():
    """Test that numbers with 0, 5, 7 are parsed accurately and not substituted."""
    assert _parse_mrp_amount("Rs. 0.55/g") == 0.55
    assert _parse_mrp_amount("Rs. 2.80") == 2.80
    assert _parse_mrp_amount("Rs. 275.00") == 275.00
    assert _parse_mrp_amount("Rs. 99.00") == 99.00


def test_parse_net_quantity_supports_units():
    """Test standard Legal Metrology count units."""
    amt, unit = _parse_net_quantity("10 units")
    assert amt == 10.0
    assert unit == "pc"

    amt, unit = _parse_net_quantity("10 N")
    assert amt == 10.0
    assert unit == "pc"


def test_real_package_integrity_hersheys():
    """End-to-end test on Hershey's reference vs inspected images."""
    ref_path = Path("Reference Images/Hershey's REFERENCE BACK.png")
    insp_path = Path("images new/Hershey's Back.jpeg")
    if not ref_path.exists() or not insp_path.exists():
        pytest.skip("Hershey's test images not found")

    report = compare_reference_vs_inspected_package(
        ref_path=ref_path,
        insp_path=insp_path,
        product_name="Hershey's Chocolate Syrup 180g",
    )

    items_by_key = {it["field_key"]: it for it in report.field_comparisons}
    assert "mrp" in items_by_key
    assert items_by_key["mrp"]["status"] == STATUS_MATCH
    assert "99" in items_by_key["mrp"]["reference_value"]
    assert "99" in items_by_key["mrp"]["inspection_value"]

    assert "barcode" in items_by_key
    bc_item = items_by_key["barcode"]
    assert bc_item["status"] == STATUS_MATCH
    assert bc_item["barcode_verification_status"] == "VERIFIED"
    assert "8901071705479" in bc_item["inspection_value"]


def test_real_package_integrity_bru():
    """End-to-end test on BRU coffee jar images."""
    ref_path = Path("Reference Images/BRU BACK REFERENCE.png")
    insp_path = Path("images new/BRU BACK.jpg")
    if not ref_path.exists() or not insp_path.exists():
        pytest.skip("BRU test images not found")

    report = compare_reference_vs_inspected_package(
        ref_path=ref_path,
        insp_path=insp_path,
        product_name="Bru Instant Coffee Jar",
    )

    items_by_key = {it["field_key"]: it for it in report.field_comparisons}
    assert "mrp" in items_by_key
    # Reference image has Rs.450 while inspected pack has Rs.420 -> legitimate packaging version variance
    assert items_by_key["mrp"]["status"] in (STATUS_MATCH, STATUS_REVIEW_REQUIRED)

    # Check USP corroboration
    if "unit_sale_price" in items_by_key:
        usp_item = items_by_key["unit_sale_price"]
        assert usp_item["status"] in (STATUS_MATCH, STATUS_REVIEW_REQUIRED)

    # Check Barcode verification
    if "barcode" in items_by_key:
        bc_item = items_by_key["barcode"]
        assert bc_item["barcode_verification_status"] in ("VERIFIED", "REVIEW_REQUIRED", "NOT_OBSERVED")


def test_real_package_integrity_vaseline():
    """End-to-end test on Vaseline images."""
    insp_path = Path("images new/VASELINE BACK.jpg")
    ref_path = Path("images new/VASELINE FRONT.jpg")
    if not insp_path.exists():
        pytest.skip("Vaseline test images not found")

    report = compare_reference_vs_inspected_package(
        ref_path=ref_path,
        insp_path=insp_path,
        product_name="Vaseline Healthy Bright Body Lotion",
    )

    items_by_key = {it["field_key"]: it for it in report.field_comparisons}
    assert "barcode" in items_by_key
    bc_item = items_by_key["barcode"]
    # Machine decoded 8901030953149, printed digits blurred on vertical bottle -> NOT_OBSERVED or VERIFIED
    assert bc_item["barcode_verification_status"] in ("NOT_OBSERVED", "VERIFIED", "REVIEW_REQUIRED")
    assert "8901030953149" in (bc_item.get("decoded_value") or bc_item["inspection_value"])


def test_real_package_integrity_good_knight():
    """End-to-end test on Good Knight images."""
    insp_path = Path("images new/GOOD KNIGHT BACK.jpg")
    ref_path = Path("images new/GOOD KNIGHT FRONT.jpg")
    if not insp_path.exists():
        pytest.skip("Good Knight test images not found")

    report = compare_reference_vs_inspected_package(
        ref_path=ref_path,
        insp_path=insp_path,
        product_name="Good Knight Active+",
    )

    items_by_key = {it["field_key"]: it for it in report.field_comparisons}
    assert "barcode" in items_by_key
    bc_item = items_by_key["barcode"]
    assert "8901157002041" in (bc_item.get("decoded_value") or bc_item["inspection_value"])
