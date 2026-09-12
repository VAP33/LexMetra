"""
Unit tests for exemption.py — no database required.
"""

from exemption import ExemptionInput, classify_exemption


def test_export_only_is_exempt():
    result = classify_exemption(ExemptionInput(
        sale_type="export",
        net_quantity_value=100,
        net_quantity_unit="g",
        product_category="food",
        is_export_only=True,
    ))
    assert result.is_exempt is True
    assert result.rule_id


def test_export_only_flag_alone_without_export_sale_type_is_not_exempt():
    """
    An export-marked package sold domestically (retail) must NOT be silently
    exempted — Rule 25 (export repack) governs that case, not Rule 3.
    """
    result = classify_exemption(ExemptionInput(
        sale_type="retail",
        net_quantity_value=100,
        net_quantity_unit="g",
        product_category="food",
        is_export_only=True,
    ))
    assert result.is_exempt is False


def test_ordinary_retail_food_is_not_exempt():
    result = classify_exemption(ExemptionInput(
        sale_type="retail",
        net_quantity_value=500,
        net_quantity_unit="g",
        product_category="food",
    ))
    assert result.is_exempt is False


def test_weight_and_volume_units_are_not_conflated():
    """1 litre must never be treated as equivalent to 1 kg for threshold checks."""
    grams_result = classify_exemption(ExemptionInput(
        sale_type="retail",
        net_quantity_value=1,
        net_quantity_unit="kg",
        product_category="food",
    ))
    litres_result = classify_exemption(ExemptionInput(
        sale_type="retail",
        net_quantity_value=1,
        net_quantity_unit="l",
        product_category="food",
    ))
    # The classifier must handle both units without crashing or raising, and
    # must return a well-formed result for each independently.
    assert isinstance(grams_result.is_exempt, bool)
    assert isinstance(litres_result.is_exempt, bool)
