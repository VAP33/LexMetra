"""Tests for First, Second, Third, and Seventh Schedules."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.schedules import (
    lookup_mpe,
    lookup_standard_pack_size,
    lookup_min_numeral_height,
    validate_third_schedule_unit,
)


# ---------------------------------------------------------------------------
# First Schedule: Maximum Permissible Errors
# ---------------------------------------------------------------------------

def test_first_schedule_mpe_small_pack():
    # 50g tier: 9% of 40g = 3.6g
    mpe = lookup_mpe(40.0, "g")
    assert mpe["supported"] is True
    assert mpe["max_permissible_error"] == 3.6
    assert mpe["max_permissible_error_unit"] == "g"


def test_first_schedule_mpe_fixed_tier():
    # 50g to 100g: fixed 4.5g
    mpe = lookup_mpe(80.0, "g")
    assert mpe["supported"] is True
    assert mpe["max_permissible_error"] == 4.5

    # 500g to 1000g: fixed 15g
    mpe_1kg = lookup_mpe(1.0, "kg")
    assert mpe_1kg["supported"] is True
    assert mpe_1kg["max_permissible_error"] == 15.0


def test_first_schedule_mpe_volume():
    # 200ml to 300ml: fixed 9ml
    mpe_vol = lookup_mpe(250.0, "ml")
    assert mpe_vol["supported"] is True
    assert mpe_vol["max_permissible_error"] == 9.0
    assert mpe_vol["max_permissible_error_unit"] == "ml"


# ---------------------------------------------------------------------------
# Second Schedule: Standard Pack Sizes
# ---------------------------------------------------------------------------

def test_second_schedule_permitted_pack_size():
    # Tea: 250g is standard
    res = lookup_standard_pack_size("Tea", 250.0, "g")
    assert res["is_scheduled"] is True
    assert res["is_standard"] is True

    # Biscuits: 100g is standard
    res_bisc = lookup_standard_pack_size("Biscuits", 100.0, "g")
    assert res_bisc["is_scheduled"] is True
    assert res_bisc["is_standard"] is True


def test_second_schedule_non_standard_pack_size():
    # Tea: 350g is not in permitted sizes
    res = lookup_standard_pack_size("Tea", 350.0, "g")
    assert res["is_scheduled"] is True
    assert res["is_standard"] is False
    assert "not a permitted standard pack size" in res["reason"]


def test_second_schedule_unscheduled_commodity():
    # Electronic goods are not subject to standard pack sizes in Second Schedule
    res = lookup_standard_pack_size("Smartphone", 1.0, "number")
    assert res["is_scheduled"] is False
    assert res["is_standard"] is True


# ---------------------------------------------------------------------------
# Third Schedule: Unit Symbols
# ---------------------------------------------------------------------------

def test_third_schedule_valid_symbols():
    for sym in ["g", "kg", "mg", "ml", "l", "L", "m", "cm", "mm", "N", "U"]:
        res = validate_third_schedule_unit(sym)
        assert res["valid"] is True, f"Expected {sym} to be valid"


def test_third_schedule_invalid_common_symbols():
    # 'gms' violates Third Schedule (must be 'g')
    res = validate_third_schedule_unit("gms")
    assert res["valid"] is False
    assert res["suggested"] == "g"

    # 'kgs' violates Third Schedule (must be 'kg')
    res_kg = validate_third_schedule_unit("kgs")
    assert res_kg["valid"] is False
    assert res_kg["suggested"] == "kg"


# ---------------------------------------------------------------------------
# Seventh Schedule: Numeral and Letter Heights
# ---------------------------------------------------------------------------

def test_seventh_schedule_small_pdp():
    # PDP area <= 50 cm²: normal height 1.0 mm, blown/moulded 2.0 mm
    h_norm = lookup_min_numeral_height(40.0, "normal")
    assert h_norm["required_minimum_height_mm"] == 1.0

    h_blown = lookup_min_numeral_height(40.0, "blown_plastic_bottle")
    assert h_blown["required_minimum_height_mm"] == 2.0


def test_seventh_schedule_medium_and_large_pdp():
    # PDP area 200 cm² (between 100 and 500): 2.5 mm normal
    h_med = lookup_min_numeral_height(200.0, "normal")
    assert h_med["required_minimum_height_mm"] == 2.5

    # PDP area > 2500 cm²: 6.0 mm normal
    h_large = lookup_min_numeral_height(3000.0, "normal")
    assert h_large["required_minimum_height_mm"] == 6.0
