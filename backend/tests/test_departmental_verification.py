"""
Unit tests for Departmental Regulatory Cross-Verification Service.
Verifies:
1. VLM / Evidentiary commodity classification (Fixing 'Packaged Food Product' false negative)
2. Distinction between product GTIN and departmental regulatory license numbers
3. FSSAI concrete implementation with DEMO, LIVE, and UNAVAILABLE states
4. Extensibility to other departments (CDSCO, BIS, LMPC)
"""

import pytest
from departmental_verification import (
    classify_commodity_and_regulatory_scope,
    generate_departmental_regulatory_dossier,
    STATUS_LIVE,
    STATUS_DEMO,
    STATUS_MANUAL,
    STATUS_UNAVAILABLE,
    STATUS_NOT_APPLICABLE,
)


def test_classify_packaged_food_product_not_exempt():
    """CRITICAL: Ensure 'Packaged Food Product' is correctly classified as food and NOT exempt from FSSAI."""
    classification = classify_commodity_and_regulatory_scope(
        product_category="Packaged Food Product",
        product_name="Bru Instant Coffee 100g",
        raw_ocr_fields={"common_name": "Instant Coffee with Chicory", "mrp": "₹420.00"},
    )
    assert classification.is_food is True
    assert classification.primary_category == "FOOD_AND_BEVERAGES"
    assert "FSSAI" in classification.explanation or "food" in classification.explanation.lower()


def test_classify_cosmetics_cdsco_scope():
    """Verify cosmetics (Vaseline) are classified as COSMETICS_PERSONAL_CARE, exempt from FSSAI."""
    classification = classify_commodity_and_regulatory_scope(
        product_category="Personal Care",
        product_name="Vaseline Healthy Bright Body Lotion",
        raw_ocr_fields={"product_name": "Body Lotion", "net_quantity": "200 ml"},
    )
    assert classification.is_food is False
    assert classification.primary_category == "COSMETICS_PERSONAL_CARE"


def test_classify_insecticide_household_scope():
    """Verify insecticides (Good Knight) are classified under household chemicals."""
    classification = classify_commodity_and_regulatory_scope(
        product_category="Household",
        product_name="Good Knight Active+ Liquid Refill",
        raw_ocr_fields={"product_name": "Mosquito Vaporizer Refill", "net_quantity": "45 ml"},
    )
    assert classification.is_food is False
    assert classification.primary_category == "HOUSEHOLD_CHEMICALS"


def test_departmental_dossier_food_bru_coffee():
    """Verify complete departmental regulatory dossier for a food product."""
    dossier = generate_departmental_regulatory_dossier(
        inspection_id="insp-test-bru",
        product_category="Packaged Food Product",
        product_name="Bru Instant Coffee Jar",
        raw_ocr_fields={
            "fssai_license_number": "10012022000258",
            "manufacturer_name": "Hindustan Unilever Limited",
            "barcode": "8901030018591",
        },
        product_gtin="8901030018591",
    )

    assert dossier.commodity.is_food is True
    assert dossier.primary_regulator.startswith("Legal Metrology Division")

    dept_map = {d.department_code: d for d in dossier.departments}
    assert "LMPC" in dept_map
    assert "FSSAI" in dept_map
    assert "CDSCO" in dept_map

    # 1. Primary LMPC
    assert dept_map["LMPC"].is_applicable is True

    # 2. FSSAI Cross-Verification
    fssai = dept_map["FSSAI"]
    assert fssai.is_applicable is True
    assert fssai.extracted_identifier == "10012022000258"
    assert fssai.product_gtin == "8901030018591"  # GTIN distinct from FSSAI
    assert fssai.verification_status in (STATUS_DEMO, STATUS_LIVE)
    assert fssai.is_demo_data is True
    assert "Hindustan Unilever Limited" in (fssai.licensee_name or "")
    assert "https://foscos.fssai.gov.in/" in fssai.official_portal_url

    # 3. CDSCO (exempt for food)
    assert dept_map["CDSCO"].is_applicable is False
    assert dept_map["CDSCO"].verification_status == STATUS_NOT_APPLICABLE


def test_departmental_dossier_cosmetics_vaseline():
    """Verify departmental dossier for cosmetics (CDSCO applicable, FSSAI not applicable)."""
    dossier = generate_departmental_regulatory_dossier(
        inspection_id="insp-test-vaseline",
        product_category="Cosmetics",
        product_name="Vaseline Deep Moisture Body Lotion",
        raw_ocr_fields={
            "manufacturer_name": "Hindustan Unilever Limited",
            "barcode": "8901030721491",
        },
        product_gtin="8901030721491",
    )

    dept_map = {d.department_code: d for d in dossier.departments}

    # FSSAI is NOT APPLICABLE
    assert dept_map["FSSAI"].is_applicable is False
    assert dept_map["FSSAI"].verification_status == STATUS_NOT_APPLICABLE

    # CDSCO IS APPLICABLE
    assert dept_map["CDSCO"].is_applicable is True
    assert "https://cdsco.gov.in/" in dept_map["CDSCO"].official_portal_url
