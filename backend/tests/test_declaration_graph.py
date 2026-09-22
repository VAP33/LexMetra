"""
Tests for Heterogeneous Declaration Graph Resolver in LexMetra.
Verifies candidate preservation without consumption during discovery,
synthetic MRP/USP disambiguation, sequence reasoning, and abstention logic.
"""

import pytest
from declaration_graph import (
    DeclarationGraphResolver,
    OcrLineView,
    cluster_declaration_blocks,
)


class MockOcrLine:
    def __init__(self, text: str, bbox: tuple, confidence: float = 0.9):
        self.text = text
        self.bbox = bbox
        self.confidence = confidence


def test_mrp_usp_synthetic_ambiguity():
    """
    Mandatory Amendment 30:
    Labels: MRP, USP
    Values: ₹800.00, ₹26.67/ml
    Neither value consumed during discovery;
    Global resolver accurately maps:
      MRP -> ₹800.00
      USP -> ₹26.67/ml
    """
    lines = [
        MockOcrLine("MAXIMUM RETAIL PRICE (MRP):", (50, 100, 200, 25)),
        MockOcrLine("₹ 800.00 (INCL. OF ALL TAXES)", (260, 100, 180, 25)),
        MockOcrLine("UNIT SALE PRICE (USP):", (50, 140, 180, 25)),
        MockOcrLine("₹ 26.67/ml", (260, 140, 120, 25)),
    ]

    resolver = DeclarationGraphResolver()
    resolved = resolver.resolve(lines)

    assert "mrp" in resolved
    assert resolved["mrp"].status == "RESOLVED"
    assert resolved["mrp"].display_value == "₹800"
    assert resolved["mrp"].value.amount == 800.0
    assert resolved["mrp"].value.is_unit_rate is False

    assert "unit_sale_price" in resolved
    assert resolved["unit_sale_price"].status == "RESOLVED"
    assert resolved["unit_sale_price"].display_value == "₹26.67/ml"
    assert resolved["unit_sale_price"].value.amount == 26.67
    assert resolved["unit_sale_price"].value.is_unit_rate is True
    assert resolved["unit_sale_price"].value.denominator_unit == "ml"

    # Verify explainability: alternative candidates retained
    assert len(resolved["mrp"].alternative_candidates) > 0
    assert len(resolved["unit_sale_price"].alternative_candidates) > 0


def test_traya_stamp_block_resolution():
    """
    Mandatory Amendment 3 & 29:
    Realistic Traya declaration block layout:
    MRP, USP, BATCH NO, MFG DATE
    """
    lines = [
        MockOcrLine("M.R.P. :", (50, 200, 80, 25)),
        MockOcrLine("₹ 800.00", (140, 200, 90, 25)),
        MockOcrLine("USP :", (50, 235, 60, 25)),
        MockOcrLine("₹ 26.67/ml", (140, 235, 110, 25)),
        MockOcrLine("BATCH NO. :", (50, 270, 90, 25)),
        MockOcrLine("c26Ho0s", (150, 270, 80, 25)),  # Dot-matrix OCR reading
        MockOcrLine("MFG. DATE :", (50, 305, 90, 25)),
        MockOcrLine("03/2026", (150, 305, 80, 25)),
    ]

    resolver = DeclarationGraphResolver()
    resolved = resolver.resolve(lines)

    assert resolved["mrp"].status == "RESOLVED"
    assert resolved["mrp"].value.amount == 800.0

    assert resolved["unit_sale_price"].status == "RESOLVED"
    assert resolved["unit_sale_price"].value.amount == 26.67
    assert resolved["unit_sale_price"].value.denominator_unit == "ml"

    assert resolved["batch_no"].status == "RESOLVED"
    assert "C26" in resolved["batch_no"].display_value

    assert resolved["mfg_date"].status == "RESOLVED"
    assert resolved["mfg_date"].display_value == "2026-03" or "03/2026" in resolved["mfg_date"].display_value


def test_resolver_abstention():
    """
    Mandatory Amendment 5:
    When no plausible candidates exist, resolver abstains with INSUFFICIENT_EVIDENCE
    rather than fabricating a false winner.
    """
    lines = [
        MockOcrLine("M.R.P. :", (50, 100, 80, 25)),
        MockOcrLine("Lorem ipsum dolor sit amet", (50, 400, 200, 25)),
    ]

    resolver = DeclarationGraphResolver()
    resolved = resolver.resolve(lines)

    assert "mrp" in resolved
    assert resolved["mrp"].status in ("INSUFFICIENT_EVIDENCE", "UNRESOLVED")
    assert resolved["mrp"].value is None


def test_company_role_multiline_continuation():
    """
    Mandatory Amendment 15:
    Role label followed by company name and address lines across multiple lines
    without premature inline truncation.
    """
    lines = [
        MockOcrLine("MANUFACTURED BY: a |", (50, 100, 150, 25)),
        MockOcrLine("Traya Health Private Limited", (50, 130, 220, 25)),
        MockOcrLine("Plot No. 42, Industrial Area", (50, 160, 200, 25)),
        MockOcrLine("Mumbai, Maharashtra - 400001", (50, 190, 210, 25)),
    ]

    resolver = DeclarationGraphResolver()
    resolved = resolver.resolve(lines)

    assert "manufacturer_name" in resolved
    mfg = resolved["manufacturer_name"]
    assert mfg.status == "RESOLVED"
    assert mfg.display_value == "Traya Health Private Limited"
    assert "Plot No. 42" in mfg.raw_text
    assert mfg.details["pin_code"] == "400001"

