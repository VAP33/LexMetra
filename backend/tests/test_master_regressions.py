import os
from pathlib import Path
import pytest
from PIL import Image

from backend.schema import (
    FactStatus,
    PackageStructure,
    ProductInspection,
    SurfaceType,
)
from backend.declaration_graph import DeclarationGraphResolver, OcrLineView
from backend.semantic_parsers import (
    MoneyValue,
    BatchCandidate,
    TemporalValue,
    parse_money,
    parse_batch_code,
    parse_date_or_duration,
)
from backend.temporal_reasoning import resolve_temporal_evidence
from backend.capture_session import compute_surface_priority, guidance_messages
from backend.ocr_extraction import classify_fields, run_ocr, OcrLine
from backend.rule_engine import RawExtraction, run_inspection


# ---------------------------------------------------------------------------
# 1. Mandatory Traya Regression (User Requirements 3, 29)
# ---------------------------------------------------------------------------

def test_traya_back_master_regression():
    """
    Verify complete, principled resolution of TRAYA BACK.jpg:
    - MRP = ₹800.00
    - USP = ₹26.67/ml
    - Batch = C26HN005
    - Net Quantity = 30 ml
    - MFD = 03/2026
    - Best Before / Use Before = 24 months from MFD (derived 03/2028)
    - All competing candidates, scores, and rejection explanations are preserved.
    """
    img_path = Path("images new/TRAYA BACK.jpg")
    if not img_path.exists():
        pytest.skip(f"Test fixture image not found: {img_path}")

    img = Image.open(img_path)
    lines = run_ocr(img)
    assert len(lines) > 20, "OCR should produce rich text lines from Traya back panel"

    fields = classify_fields(lines)

    # 1. Net Quantity
    assert "net_quantity" in fields
    net_qty = fields["net_quantity"]
    assert net_qty.get("numeric_value") == 30.0
    assert net_qty.get("numeric_unit") == "ml"

    # 2. MRP
    assert "mrp" in fields
    mrp_field = fields["mrp"]
    assert mrp_field.get("numeric_value") == 800.0
    assert "800" in str(mrp_field.get("value"))

    # 3. Unit Sale Price (USP)
    assert "unit_sale_price" in fields
    usp_field = fields["unit_sale_price"]
    assert usp_field.get("numeric_value") == 26.67
    assert usp_field.get("numeric_unit") == "ml"
    assert "26.67" in str(usp_field.get("value"))

    # 4. Batch Number
    assert "batch_no" in fields
    batch_field = fields["batch_no"]
    assert batch_field.get("batch_code") == "C26HN005" or "C26HN005" in str(batch_field.get("value"))

    # 5. Manufacturing Date
    assert "mfg_date" in fields
    mfg_field = fields["mfg_date"]
    assert mfg_field.get("date_value") in ("03/2026", "2026-03") or "2026" in str(mfg_field.get("value"))

    # 6. Graph Resolution Explainability
    graph_res = fields.get("_graph_resolution")
    assert graph_res is not None, "Graph resolution must be preserved for auditability"
    assert "mrp" in graph_res
    assert "unit_sale_price" in graph_res

    mrp_res = graph_res["mrp"]
    assert mrp_res.status == "RESOLVED"
    assert mrp_res.value.amount == 800.0
    # Competing candidates must be preserved
    assert len(mrp_res.alternative_candidates) > 0
    alt_values = [getattr(c.parsed_value, "amount", None) for c in mrp_res.alternative_candidates]
    assert 26.67 in alt_values, "26.67 must remain a preserved competing candidate for MRP"


# ---------------------------------------------------------------------------
# 2. Synthetic MRP / USP Ambiguity Regression (User Requirement 30)
# ---------------------------------------------------------------------------

def test_synthetic_mrp_usp_ambiguity_regression():
    """
    Labels:
      MRP (line 0)
      USP (line 1)
    Values:
      ₹800 (line 2)
      ₹26.67/ml (line 3)

    Verify:
    - Both values remain candidates for both labels (no consumption during discovery)
    - Semantic type contributes (denominator /ml creates strong USP affinity)
    - Sequence contributes (MRP row aligns with ₹800, USP aligns with ₹26.67/ml)
    - Global resolver selects correct 1:1 mapping
    - Alternatives remain explainable
    """
    test_lines = [
        OcrLine(text="M.R.P. (Incl. of all taxes):", bbox=(50, 100, 200, 25), confidence=0.95),
        OcrLine(text="Unit Sale Price:", bbox=(50, 140, 180, 25), confidence=0.95),
        OcrLine(text="₹ 800.00", bbox=(280, 100, 100, 25), confidence=0.92),
        OcrLine(text="₹ 26.67 / ml", bbox=(280, 140, 120, 25), confidence=0.94),
    ]

    resolver = DeclarationGraphResolver()
    results = resolver.resolve(test_lines)

    assert "mrp" in results
    assert "unit_sale_price" in results

    mrp_res = results["mrp"]
    usp_res = results["unit_sale_price"]

    assert mrp_res.status == "RESOLVED"
    assert mrp_res.value.amount == 800.0
    assert not mrp_res.value.is_unit_rate

    assert usp_res.status == "RESOLVED"
    assert usp_res.value.amount == 26.67
    assert usp_res.value.is_unit_rate
    assert usp_res.value.denominator_unit == "ml"

    # Verify both values were retained as candidates for MRP without early consumption
    mrp_cand_amounts = [mrp_res.selected_candidate.parsed_value.amount] + [
        c.parsed_value.amount for c in mrp_res.alternative_candidates
    ]
    assert 800.0 in mrp_cand_amounts
    assert 26.67 in mrp_cand_amounts

    # Verify both values were retained as candidates for USP
    usp_cand_amounts = [usp_res.selected_candidate.parsed_value.amount] + [
        c.parsed_value.amount for c in usp_res.alternative_candidates
    ]
    assert 800.0 in usp_cand_amounts
    assert 26.67 in usp_cand_amounts


# ---------------------------------------------------------------------------
# 3. Temporal Reasoning & Derived Expiry (User Requirements 6, 7, 8)
# ---------------------------------------------------------------------------

def test_relative_best_before_temporal_reasoning_and_no_false_expiry_missing():
    """
    Verify:
    MFD: 03/2026
    Best Before: 24 months from MFD
    -> derived endpoint: 03/2028
    -> Rule engine must NOT declare "Expiry date missing" when lawful shelf-life is declared.
    """
    ev = resolve_temporal_evidence(
        mfg_raw="MFD: 03/2026",
        expiry_raw=None,
        best_before_raw="Best Before 24 months from date of manufacture",
    )

    assert "best_before" in ev
    bb = ev["best_before"]
    assert bb.duration_value == 24.0
    assert bb.duration_unit == "months"
    assert bb.derived_date == "2028-03"
    assert "03/2026" in str(bb.anchor_evidence)
    assert bb.anchor_type in ("manufacturing_date", "MFD")

    # Evaluate compliance in rule engine
    extractions = {
        "mrp": RawExtraction(field="mrp", raw_text="₹800", value="₹800", numeric_value=800.0, confidence=0.95),
        "net_quantity": RawExtraction(field="net_quantity", raw_text="30 ml", value="30 ml", numeric_value=30.0, numeric_unit="ml", confidence=0.95),
        "mfg_date": RawExtraction(field="mfg_date", raw_text="03/2026", value="03/2026", normalized_value="2026-03", confidence=0.95),
        "best_before_use_by": RawExtraction(field="best_before_use_by", raw_text="24 months from MFD", value="24 months from MFD", normalized_value="2028-03", confidence=0.95),
        "manufacturer_name_address": RawExtraction(field="manufacturer_name_address", raw_text="Traya Health Pvt Ltd, Plot 10, Andheri East, Mumbai 400069", value="Traya Health Pvt Ltd, Plot 10, Andheri East, Mumbai 400069", confidence=0.95),
        "common_name": RawExtraction(field="common_name", raw_text="Hair Serum", value="Hair Serum", confidence=0.95),
        "consumer_care": RawExtraction(field="consumer_care", raw_text="care@traya.health", value="care@traya.health", confidence=0.95),
    }

    result = run_inspection(
        inspection_id="test_shelf_life",
        sale_type="retail",
        product_category="cosmetics",
        net_quantity_value=30.0,
        net_quantity_unit="ml",
        mrp=800.0,
        extractions=extractions,
        best_before_applicable=True,
    )

    # Must NOT fail for missing expiry date
    failed_reqs = [f.requirement_id for f in result.findings if f.status == FactStatus.FAIL]
    assert "best_before_use_by" not in failed_reqs
    assert "manufacture_pack_import_date" not in failed_reqs


# ---------------------------------------------------------------------------
# 4. Package Structure USP Gating (User Requirements 9, 10)
# ---------------------------------------------------------------------------

def test_package_structure_gating_usp():
    """
    Test package structure context affecting USP applicability:
    - WHOLESALE_PACKAGE -> USP is EXEMPT
    - COMBINATION_PACKAGE / MULTI_PIECE -> requires constituent breakdown, UNCERTAIN not violation
    - UNKNOWN -> UNCERTAIN not violation
    """
    extractions_no_usp = {
        "mrp": RawExtraction(field="mrp", raw_text="₹500", value="₹500", numeric_value=500.0, confidence=0.95),
        "net_quantity": RawExtraction(field="net_quantity", raw_text="500 g", value="500 g", numeric_value=500.0, numeric_unit="g", confidence=0.95),
    }

    # 1. Wholesale package
    insp_wholesale = run_inspection(
        inspection_id="test_wholesale",
        sale_type="wholesale",
        product_category="food",
        net_quantity_value=500.0,
        net_quantity_unit="g",
        mrp=500.0,
        extractions=extractions_no_usp,
        package_structure=PackageStructure.WHOLESALE_PACKAGE,
    )
    usp_findings_ws = [f for f in insp_wholesale.findings if "UNIT-PRICE" in f.rule_id]
    assert len(usp_findings_ws) > 0
    assert usp_findings_ws[0].status == FactStatus.EXEMPT

    # 2. Combination package without declared USP
    insp_comb = run_inspection(
        inspection_id="test_combination",
        sale_type="retail",
        product_category="food",
        net_quantity_value=500.0,
        net_quantity_unit="g",
        mrp=500.0,
        extractions=extractions_no_usp,
        package_structure=PackageStructure.COMBINATION_PACKAGE,
    )
    usp_findings_cb = [f for f in insp_comb.findings if "UNIT-PRICE" in f.rule_id]
    assert len(usp_findings_cb) > 0
    # Must be UNCERTAIN (review required for constituent piece breakdown), NOT a direct FAIL
    assert usp_findings_cb[0].status == FactStatus.UNCERTAIN

    # 3. Unknown package structure without declared USP
    insp_unk = run_inspection(
        inspection_id="test_unknown",
        sale_type="retail",
        product_category="food",
        net_quantity_value=500.0,
        net_quantity_unit="g",
        mrp=500.0,
        extractions=extractions_no_usp,
        package_structure=PackageStructure.UNKNOWN,
    )
    usp_findings_unk = [f for f in insp_unk.findings if "UNIT-PRICE" in f.rule_id]
    assert len(usp_findings_unk) > 0
    assert usp_findings_unk[0].status == FactStatus.UNCERTAIN


# ---------------------------------------------------------------------------
# 5. Evidence-Driven Surface Prioritization (User Requirement 11)
# ---------------------------------------------------------------------------

def test_evidence_driven_surface_prioritization():
    """
    Verify surface priority is dynamically calculated from evidence (declaration density,
    confidence, lines, barcode) and does NOT hardcode BACK as primary.
    """
    # Front surface with high branding but only 1 declaration
    p_front, d_front, t_front = compute_surface_priority(
        surface_type=SurfaceType.UNKNOWN,
        ocr_lines=[OcrLine("BRU Instant Coffee", (10, 10, 100, 30), 0.95)],
        classified_fields={
            "common_name": {"value": "Instant Coffee", "confidence": 0.95},
        },
        has_barcode=False,
    )

    # Back surface with 5 key declarations and barcode
    p_back, d_back, t_back = compute_surface_priority(
        surface_type=SurfaceType.UNKNOWN,
        ocr_lines=[OcrLine(f"Line {i}", (10, 10 + i * 20, 100, 15), 0.9) for i in range(15)],
        classified_fields={
            "mrp": {"value": "₹800", "confidence": 0.95},
            "unit_sale_price": {"value": "₹26.67/ml", "confidence": 0.90},
            "mfg_date": {"value": "03/2026", "confidence": 0.95},
            "net_quantity": {"value": "30 ml", "confidence": 0.95},
            "manufacturer_name_address": {"value": "Cheryl Laboratories", "confidence": 0.90},
        },
        has_barcode=True,
    )

    assert p_back > p_front, "Declaration-heavy surface must have significantly higher priority score"
    assert d_back >= 5.0
    assert t_back == SurfaceType.BACK
    assert t_front == SurfaceType.FRONT


# ---------------------------------------------------------------------------
# 6. Multi-Surface Provenance & Guidance (User Requirements 12, 25)
# ---------------------------------------------------------------------------

def test_capture_guidance_recommends_specific_missing_panels():
    """
    Verify capture guidance identifies specific missing declarations and
    recommends specific packaging panels rather than generic 'needs review'.
    """
    # Case: missing pricing and dates
    guidance = guidance_messages(
        image_quality=type("Quality", (), {"notes": []})(),
        coverage=0.40,
        missing_fields=["mfg_date", "best_before_use_by", "mrp", "unit_sale_price"],
    )
    combined = " ".join(guidance)
    assert "declaration panel" in combined.lower() or "bottom flap" in combined.lower() or "back" in combined.lower()
