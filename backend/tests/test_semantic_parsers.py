"""
Tests for Specialized Semantic Parsers in LexMetra.
Verifies rate vs plain money disambiguation, dot-matrix batch repairs,
temporal parsing, and role address continuation.
"""

import pytest
from semantic_parsers import (
    MoneyValue,
    parse_money,
    BatchCandidate,
    parse_batch_code,
    TemporalValue,
    parse_date_or_duration,
    RoleAddressBlock,
    parse_role_company_block,
)


def test_money_plain_vs_rate():
    # Plain monetary values
    m1 = parse_money("₹800.00")
    assert m1 is not None
    assert m1.amount == 800.0
    assert m1.is_unit_rate is False
    assert m1.denominator_unit is None

    m2 = parse_money("MRP Rs. 800/- (incl. of all taxes)")
    assert m2 is not None
    assert m2.amount == 800.0
    assert m2.is_unit_rate is False
    assert "inclusive of all taxes" in m2.qualifiers

    m3 = parse_money("800.00")
    assert m3 is not None
    assert m3.amount == 800.0
    assert m3.is_unit_rate is False

    # Unit rates with denominators
    r1 = parse_money("₹26.67/ml")
    assert r1 is not None
    assert r1.amount == 26.67
    assert r1.is_unit_rate is True
    assert r1.denominator_unit == "ml"

    r2 = parse_money("26.67 / ml")
    assert r2 is not None
    assert r2.amount == 26.67
    assert r2.is_unit_rate is True
    assert r2.denominator_unit == "ml"

    r3 = parse_money("₹2.80/g")
    assert r3 is not None
    assert r3.amount == 2.80
    assert r3.is_unit_rate is True
    assert r3.denominator_unit == "g"

    r4 = parse_money("5.00 per unit")
    assert r4 is not None
    assert r4.amount == 5.00
    assert r4.is_unit_rate is True
    assert r4.denominator_unit == "unit"


def test_money_mass_guard():
    # 16.89 g should NOT be parsed as money
    assert parse_money("16.89 g") is None
    assert parse_money("16.89 grams") is None
    assert parse_money("500 g") is None
    assert parse_money("30 ml") is None


def test_batch_code_repair():
    # Dot-matrix repair on Traya-like batch strings
    b1 = parse_batch_code("c26Ho0s")
    assert b1 is not None
    assert b1.raw_reading == "c26Ho0s"
    assert b1.normalized_reading == "C26H005" or "C26" in b1.normalized_reading

    b2 = parse_batch_code("BATCH NO. C26HN005")
    assert b2 is not None
    assert b2.normalized_reading == "C26HN005"

    b3 = parse_batch_code("LOT: B-1029/A")
    assert b3 is not None
    assert "B-1029/A" in b3.normalized_reading

    # Reject dates as batch codes
    assert parse_batch_code("03/2026") is None


def test_temporal_relative_and_absolute():
    # Relative durations with anchors
    t1 = parse_date_or_duration("24 months from MFD")
    assert t1 is not None
    assert t1.is_relative is True
    assert t1.duration_value == 24.0
    assert "month" in t1.duration_unit
    assert t1.anchor_type == "MFD"

    t2 = parse_date_or_duration("2 years from date of manufacture")
    assert t2 is not None
    assert t2.is_relative is True
    assert t2.duration_value == 2.0
    assert "year" in t2.duration_unit

    t3 = parse_date_or_duration("Use within 24 months of manufacture")
    assert t3 is not None
    assert t3.is_relative is True
    assert t3.duration_value == 24.0

    # Absolute dates
    t4 = parse_date_or_duration("03/2026")
    assert t4 is not None
    assert t4.is_relative is False
    assert t4.normalized_iso == "2026-03"

    t5 = parse_date_or_duration("13/05/2026")
    assert t5 is not None
    assert t5.is_relative is False
    assert t5.normalized_iso == "2026-05-13"

    t6 = parse_date_or_duration("MAR 2028")
    assert t6 is not None
    assert t6.is_relative is False
    assert t6.normalized_iso == "2028-03"


def test_role_company_continuation():
    # Multi-line continuation: Traya example
    label_text = "MANUFACTURED BY: a |"
    following = [
        "Traya Health Private Limited",
        "Plot No. 42, Industrial Area",
        "Mumbai, Maharashtra",
        "PIN: 400001",
    ]
    block = parse_role_company_block("MANUFACTURER", label_text, following)
    assert block.role == "MANUFACTURER"
    assert block.company_name == "Traya Health Private Limited"
    assert len(block.address_lines) >= 2
    assert block.pin_code == "400001"
