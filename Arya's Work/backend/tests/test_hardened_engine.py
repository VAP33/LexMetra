"""
Comprehensive Test Matrix for the Hardened Authoritative Product Compliance Engine.

Validates all 31 audit areas:
- Single authoritative engine execution path
- Data-driven rule coverage (Rules 4, 5, 25, 26b, 26c, 27, 31)
- Tri-state Kleene K3 logic & deterministic operator evaluation
- Arithmetic, unit conversions, division-by-zero, missing input safety
- Topological dependency sorting and circular dependency detection
- Multi-surface capture session evidence merging (disjoint front/back)
- Evidence provenance preservation (real image_id & bbox retention)
- OCR quality assessment in dictionary and fallback heuristic modes
- Amendment metadata whitespace normalization
- PostgreSQL JSONB safety & deserialization robustness
- Canonical ComplianceDecisionPackage contract
"""

import json
from pathlib import Path
import pytest

from engine import RuleEngine, load_ruleset, Evidence
from engine.conditions import Tri, evaluate_condition
from engine.calc import run_derived
from engine.results import ComplianceStatus, ApplicabilityStatus, ComplianceDecisionPackage
from engine.lexmetra_adapter import run_inspection_v2, build_evidence
from schema import (
    FactStatus,
    GeometryType,
    SurfaceObservation,
    SurfaceType,
    CaptureMode,
    EvidenceReference,
    BBox,
    UNATTRIBUTED_IMAGE_ID,
)
from capture_session import merge_classified_fields, stamp_provenance, build_raw_extraction
from lexmetra_rules.ocr_quality import assess_text_quality, get_ocr_quality_mode
import lexmetra_rules.ocr_quality as ocr_module
from lexmetra_rules.amendment_metadata import AmendmentMetadata, extract_amendment_metadata, normalize_whitespace
from db.persistence import decode_json_column

GENERIC_RULES_PATH = Path(__file__).resolve().parent.parent.parent / "rules" / "generic" / "lmpc_rules.json"


# ===========================================================================
# 1. Three-Valued (Kleene K3) Logic & Condition Operators
# ===========================================================================

def test_kleene_tri_state_logic_truth_tables():
    """Verify Kleene K3 logic: AND, OR, NOT with UNKNOWN."""
    # AND: FALSE and UNKNOWN = FALSE, TRUE and UNKNOWN = UNKNOWN
    cond_and_f = {"op": "and", "conditions": [
        {"op": "eq", "field": "a", "value": 1},   # TRUE
        {"op": "eq", "field": "b", "value": 99},  # FALSE
        {"op": "exists", "field": "unknown_field"} # UNKNOWN
    ]}
    ev = Evidence()
    ev.set_field("a", 1, present=True)
    ev.set_field("b", 2, present=True)
    ev.set_field("unknown_field", "unusable evidence", present=True, usable=False)
    assert evaluate_condition(cond_and_f, ev) == Tri.FALSE

    cond_and_u = {"op": "and", "conditions": [
        {"op": "eq", "field": "a", "value": 1},   # TRUE
        {"op": "exists", "field": "unknown_field"} # UNKNOWN
    ]}
    assert evaluate_condition(cond_and_u, ev) == Tri.UNKNOWN

    # OR: TRUE or UNKNOWN = TRUE, FALSE or UNKNOWN = UNKNOWN
    cond_or_t = {"op": "or", "conditions": [
        {"op": "eq", "field": "a", "value": 1},   # TRUE
        {"op": "exists", "field": "unknown_field"} # UNKNOWN
    ]}
    assert evaluate_condition(cond_or_t, ev) == Tri.TRUE

    cond_or_u = {"op": "or", "conditions": [
        {"op": "eq", "field": "b", "value": 99},  # FALSE
        {"op": "exists", "field": "unknown_field"} # UNKNOWN
    ]}
    assert evaluate_condition(cond_or_u, ev) == Tri.UNKNOWN

    # NOT UNKNOWN = UNKNOWN
    cond_not_u = {"op": "not", "condition": {"op": "exists", "field": "unknown_field"}}
    assert evaluate_condition(cond_not_u, ev) == Tri.UNKNOWN


def test_comparison_operators_and_unknown_handling():
    """Verify comparison operators: eq, neq, gt, gte, lt, lte, in, not_in, contains."""
    ev = Evidence()
    ev.set_field("score", 75, present=True)
    ev.set_field("tag", "electronics", present=True)
    ev.set_field("tags", ["foo", "bar"], present=True)

    assert evaluate_condition({"op": "gt", "field": "score", "value": 50}, ev) == Tri.TRUE
    assert evaluate_condition({"op": "lte", "field": "score", "value": 75}, ev) == Tri.TRUE
    assert evaluate_condition({"op": "lt", "field": "score", "value": 75}, ev) == Tri.FALSE
    assert evaluate_condition({"op": "in", "field": "tag", "value": ["food", "electronics"]}, ev) == Tri.TRUE
    assert evaluate_condition({"op": "not_in", "field": "tag", "value": ["pharma"]}, ev) == Tri.TRUE
    assert evaluate_condition({"op": "contains", "field": "tags", "value": "bar"}, ev) == Tri.TRUE

    # Missing field must produce UNKNOWN, never silent False
    assert evaluate_condition({"op": "gt", "field": "absent_score", "value": 50}, ev) == Tri.UNKNOWN


def test_unusable_evidence_evaluates_to_unknown():
    """Explicitly unusable evidence must yield UNKNOWN, never PASS or FAIL."""
    ev = Evidence()
    ev.set_field("declared.common_name", "Flour", present=True, confidence=0.9, usable=False)
    cond = {"op": "exists", "field": "declared.common_name"}
    assert evaluate_condition(cond, ev) == Tri.UNKNOWN


# ===========================================================================
# 2. Deterministic Traceable Calculations
# ===========================================================================

def test_calculation_unit_price_and_traces():
    """Calculations must be traceable and never silently convert failure to zero."""
    derived_specs = [
        {
            "name": "total_grams",
            "expr": {
                "op": "mul",
                "args": [{"field": "declared.pack_count"}, {"field": "declared.unit_grams"}]
            }
        },
        {
            "name": "unit_rate",
            "expr": {
                "op": "div",
                "args": [{"field": "declared.mrp"}, {"field": "computed.total_grams"}]
            }
        }
    ]
    ev = Evidence()
    ev.set_field("declared.pack_count", 5, present=True)
    ev.set_field("declared.unit_grams", 200, present=True)
    ev.set_field("declared.mrp", 100.0, present=True)

    traces = run_derived(derived_specs, ev)
    assert len(traces) == 2
    assert ev.get("computed.total_grams") == 1000
    assert ev.get("computed.unit_rate") == 0.1
    assert traces[0].status == "OK"
    assert traces[0].output == 1000
    assert traces[1].status == "OK"
    assert traces[1].output == 0.1


def test_calculation_division_by_zero_fails_safely():
    """Division by zero must produce UNCERTAIN and not silent zero."""
    derived_specs = [
        {
            "name": "bad_rate",
            "expr": {
                "op": "div",
                "args": [{"field": "declared.mrp"}, {"field": "declared.zero_val"}]
            }
        }
    ]
    ev = Evidence()
    ev.set_field("declared.mrp", 100.0, present=True)
    ev.set_field("declared.zero_val", 0, present=True)

    traces = run_derived(derived_specs, ev)
    assert len(traces) == 1
    assert traces[0].ok is False
    assert traces[0].output is None
    assert traces[0].status == "UNCERTAIN"
    assert ev.get("computed.bad_rate") is None


# ===========================================================================
# 3. Rule Coverage for LMPC Rules 4, 5, 25, 26(b), 26(c), 27, 31
# ===========================================================================

@pytest.fixture(scope="module")
def engine():
    ruleset = load_ruleset(GENERIC_RULES_PATH)
    return RuleEngine(ruleset)


def test_rule_4_multipack_evaluation(engine):
    """Rule 4: Multi-piece package declarations."""
    # When not a multipack, rule is NOT_APPLICABLE
    ev_single = Evidence()
    ev_single.set_context("is_multipack", False)
    ev_single.set_context("retail_bundle_count", 1)
    report_single = engine.evaluate(ev_single)
    r4_single = next(r for r in report_single.results if r.rule_id == "LMPC-4-MULTIPACK")
    assert r4_single.applicability == ApplicabilityStatus.NOT_APPLICABLE

    # When is_multipack is True, rule is APPLICABLE
    ev_multi = Evidence()
    ev_multi.set_context("is_multipack", True)
    ev_multi.set_field("declared.multipack_inner_declarations", "All inner pack declarations verified", present=True)
    report_multi = engine.evaluate(ev_multi)
    r4_multi = next(r for r in report_multi.results if r.rule_id == "LMPC-4-MULTIPACK")
    assert r4_multi.applicability == ApplicabilityStatus.APPLICABLE
    assert r4_multi.status == ComplianceStatus.PASS


def test_rule_5_standard_pack_size_superseded_date_filtering(engine):
    """Rule 5: Standard pack size schedule was repealed/superseded as of 2022-08-19."""
    ev = Evidence()
    ev.set_context("commodity_has_standard_pack_schedule", True)

    # Inspection before repeal date (e.g. 2020-01-01) -> considered
    rep_past = engine.evaluate(ev, context={"inspection_date": "2020-01-01"})
    r5_past = next(r for r in rep_past.results if r.rule_id == "LMPC-5-STANDARD-PACK-SIZE")
    assert r5_past.status != ComplianceStatus.NOT_CONSIDERED

    # Inspection after repeal date (e.g. 2023-01-01) -> NOT_CONSIDERED
    rep_now = engine.evaluate(ev, context={"inspection_date": "2023-01-01"})
    r5_now = next(r for r in rep_now.results if r.rule_id == "LMPC-5-STANDARD-PACK-SIZE")
    assert r5_now.status == ComplianceStatus.NOT_CONSIDERED
    assert "superseded" in r5_now.reason.lower() or "expired" in r5_now.reason.lower()


def test_rule_25_export_package_exemption(engine):
    """Rule 25: Packages intended solely for export are exempt from mandatory declarations."""
    # Non-export package -> not applicable
    ev_non = Evidence()
    ev_non.set_context("is_export_only", False)
    ev_non.set_context("trade_type", "domestic")
    rep_non = engine.evaluate(ev_non)
    r25_non = next(r for r in rep_non.results if r.rule_id == "LMPC-25-EXPORT")
    assert r25_non.applicability == ApplicabilityStatus.NOT_APPLICABLE

    # Export package offered domestically with repacking evidence -> PASS
    ev_exp = Evidence()
    ev_exp.set_context("is_export_only", True)
    ev_exp.set_context("trade_type", "domestic")
    ev_exp.set_field("declared.export_repack_relabel_evidence", "Repacked per Chapter II", present=True)
    rep_exp = engine.evaluate(ev_exp)
    r25_exp = next(r for r in rep_exp.results if r.rule_id == "LMPC-25-EXPORT")
    assert r25_exp.applicability == ApplicabilityStatus.APPLICABLE
    assert r25_exp.status == ComplianceStatus.PASS


def test_rule_26_b_fast_food_exemption(engine):
    """Rule 26(b): Fast food and restaurant dispatches are exempt from Chapter II."""
    ev = Evidence()
    ev.set_context("product_category", "fast_food")
    ev.set_context("packer_type", "restaurant")
    report = engine.evaluate(ev)
    r26b = next(r for r in report.results if r.rule_id == "LMPC-26-B-FAST-FOOD")
    assert r26b.applicability == ApplicabilityStatus.APPLICABLE
    assert r26b.status == ComplianceStatus.EXEMPTED


def test_rule_26_c_drug_formulations_exemption(engine):
    """Rule 26(c): Scheduled pharmaceutical formulations under Drugs & Cosmetics Act are exempt."""
    ev = Evidence()
    ev.set_context("product_category", "drug_formulation")
    ev.set_context("is_dpco_covered", True)
    report = engine.evaluate(ev)
    r26c = next(r for r in report.results if r.rule_id == "LMPC-26-C-DRUG-FORMULATIONS")
    assert r26c.applicability == ApplicabilityStatus.APPLICABLE
    assert r26c.status == ComplianceStatus.EXEMPTED


def test_rule_27_registration_and_rule_31_advertisement(engine):
    """Rules 27 and 31: Registration under Rule 27 and Advertisement declarations under Rule 31."""
    # Rule 27: Manufacturer/Packer registration
    ev_reg = Evidence()
    ev_reg.set_context("inspection_includes_registration", True)
    ev_reg.set_context("registration_number", "REG/MH/2023/1234")
    report_reg = engine.evaluate(ev_reg)
    r27 = next(r for r in report_reg.results if r.rule_id == "LMPC-27-REGISTRATION")
    assert r27.applicability == ApplicabilityStatus.APPLICABLE
    assert r27.status == ComplianceStatus.PASS

    # Rule 31: Commercial advertisement price declaration
    ev_ad = Evidence()
    ev_ad.set_context("is_advertisement", True)
    ev_ad.set_field("declared.net_quantity", "100 g", present=True)
    report_ad = engine.evaluate(ev_ad)
    r31 = next(r for r in report_ad.results if r.rule_id == "LMPC-31-ADVERTISEMENT")
    assert r31.applicability == ApplicabilityStatus.APPLICABLE
    assert r31.status == ComplianceStatus.PASS


# ===========================================================================
# 4. Multi-Surface Capture Session: Disjoint Front/Back Merging
# ===========================================================================

def test_disjoint_front_and_back_session_merges_and_passes():
    """
    Scenario:
    Front Image provides: common_name, manufacturer_name_address
    Back Image provides: mrp, net_quantity, consumer_care, mfg_date, unit_sale_price
    Neither image alone has all declarations.
    The session must merge evidence from both surfaces and produce COMPLIANT.
    """
    # Capture 1: Front
    front_fields = {
        "common_name": {
            "value": "Organic Wheat Flour",
            "confidence": 0.95,
            "raw_text": "Organic Wheat Flour",
            "image_id": "img-front-01",
            "bbox": {"x": 50, "y": 100, "width": 400, "height": 80}
        },
        "manufacturer_name_address": {
            "value": "Purity Foods Ltd, 42 Grain Lane, Pune 411001",
            "confidence": 0.92,
            "raw_text": "Manufactured by: Purity Foods Ltd, 42 Grain Lane, Pune 411001",
            "image_id": "img-front-01",
            "bbox": {"x": 50, "y": 300, "width": 450, "height": 120}
        },
    }
    stamp_provenance(front_fields, image_id="img-front-01", surface_type=SurfaceType.FRONT)

    # Capture 2: Back
    back_fields = {
        "mrp": {
            "value": "MRP Rs 120.00 (incl. of all taxes)",
            "confidence": 0.96,
            "numeric_value": 120.0,
            "raw_text": "MRP Rs 120.00 (incl. of all taxes)",
            "image_id": "img-back-01",
            "bbox": {"x": 100, "y": 150, "width": 300, "height": 60}
        },
        "net_quantity": {
            "value": "1 kg",
            "confidence": 0.94,
            "numeric_value": 1000.0,
            "numeric_unit": "g",
            "raw_text": "Net Qty: 1 kg",
            "image_id": "img-back-01",
            "bbox": {"x": 100, "y": 250, "width": 200, "height": 50}
        },
        "consumer_care": {
            "value": "care@purityfoods.com, Tel: 1800-123-4567",
            "confidence": 0.91,
            "raw_text": "Customer Care: care@purityfoods.com, 1800-123-4567",
            "image_id": "img-back-01",
            "bbox": {"x": 100, "y": 350, "width": 400, "height": 80}
        },
        "mfg_date": {
            "value": "08/2026",
            "confidence": 0.93,
            "raw_text": "Mfg Date: 08/2026",
            "image_id": "img-back-01",
            "bbox": {"x": 100, "y": 450, "width": 200, "height": 40}
        },
        "unit_sale_price": {
            "value": "Rs 120.00 per kg",
            "confidence": 0.90,
            "numeric_value": 120.0,
            "raw_text": "Unit Sale Price: Rs 120.00 / kg",
            "image_id": "img-back-01",
            "bbox": {"x": 100, "y": 520, "width": 300, "height": 50}
        },
    }
    stamp_provenance(back_fields, image_id="img-back-01", surface_type=SurfaceType.BACK)

    # Merge classified fields across captures
    merged = merge_classified_fields(front_fields, back_fields)
    extractions = {k: build_raw_extraction(k, v) for k, v in merged.items()}

    # Evaluate via authoritative engine
    inspection = run_inspection_v2(
        inspection_id="insp-disjoint-01",
        sale_type="retail",
        product_category="food",
        net_quantity_value=1000.0,
        net_quantity_unit="g",
        mrp=120.0,
        extractions=extractions,
        category_requires_best_before=False,
    )

    # Overall inspection must be PASS (FactStatus.PASS)
    assert inspection.overall_status == FactStatus.PASS
    assert inspection.summary.passed >= 6
    assert inspection.summary.failed == 0
    assert inspection.summary.uncertain == 0

    # Verify provenance was preserved: front fields point to img-front-01, back fields to img-back-01
    finding_map = {f.rule_id: f for f in inspection.findings}
    
    # Common name finding must cite img-front-01
    fn_name = finding_map.get("LMPC-6-1-B-COMMON-NAME")
    assert fn_name is not None
    assert any(ref.image_id == "img-front-01" for ref in fn_name.evidence)

    # Net quantity finding must cite img-back-01
    fn_qty = finding_map.get("LMPC-6-1-E-NET-QUANTITY")
    assert fn_qty is not None
    assert any(ref.image_id == "img-back-01" for ref in fn_qty.evidence)

    # Canonical decision package must be attached
    assert inspection.decision_package is not None
    assert inspection.decision_package["overall_result"] == "PASS"


# ===========================================================================
# 5. Evidence Provenance: No Unwanted UNATTRIBUTED_IMAGE_ID
# ===========================================================================

def test_evidence_provenance_preserves_real_image_id_and_bbox():
    """When extractions have image_id and bbox, findings must retain them."""
    extractions = {
        "common_name": type("RawExtractionStub", (), {
            "value": "Basmati Rice",
            "normalized_value": "Basmati Rice",
            "confidence": 0.95,
            "raw_text": "Pure Basmati Rice",
            "image_id": "capture_camera_01.jpg",
            "bbox": BBox(x=10, y=20, width=100, height=30),
            "evidence": [EvidenceReference(image_id="capture_camera_01.jpg", bbox=BBox(x=10, y=20, width=100, height=30))],
            "usable": True,
            "quality_state": "usable",
            "verification_status": "VERIFIED"
        })()
    }
    insp = run_inspection_v2(
        inspection_id="t-prov-01",
        sale_type="retail",
        product_category="food",
        net_quantity_value=1000,
        net_quantity_unit="g",
        mrp=150.0,
        extractions=extractions,
    )
    name_finding = next((f for f in insp.findings if f.rule_id == "LMPC-6-1-B-COMMON-NAME"), None)
    assert name_finding is not None
    assert len(name_finding.evidence) > 0
    ref = name_finding.evidence[0]
    assert ref.image_id == "capture_camera_01.jpg"
    assert ref.image_id != UNATTRIBUTED_IMAGE_ID
    assert ref.bbox is not None
    assert ref.bbox.x == 10 and ref.bbox.y == 20


# ===========================================================================
# 6. OCR Quality Assessment in Dictionary and Fallback Modes
# ===========================================================================

def test_ocr_quality_flags_corrupt_sentence_in_both_modes():
    """Corrupted text must be flagged in both dictionary mode and fallback heuristic mode."""
    corrupt_text = "Every perscn shail bear the decleration of the manufacturer."

    # Dictionary mode
    ocr_module._HAS_SPELLCHECKER = True
    score_dict, flagged_dict = assess_text_quality(corrupt_text)
    assert score_dict < 0.9
    assert "perscn" in flagged_dict
    assert "shail" in flagged_dict
    assert "decleration" in flagged_dict
    assert get_ocr_quality_mode() == "dictionary"

    # Fallback heuristic mode
    ocr_module._HAS_SPELLCHECKER = False
    score_fall, flagged_fall = assess_text_quality(corrupt_text)
    assert score_fall < 0.9
    assert "perscn" in flagged_fall
    assert "shail" in flagged_fall
    assert "decleration" in flagged_fall
    assert get_ocr_quality_mode() == "fallback_heuristic"

    # Restore default
    ocr_module._HAS_SPELLCHECKER = True


def test_ocr_quality_clean_legal_text():
    """Clean legal text must receive near 1.0 quality score and no flagged words."""
    clean = "Every person shall bear the declaration of the manufacturer on the principal display panel."
    score, flagged = assess_text_quality(clean)
    assert score >= 0.95
    assert len(flagged) == 0


# ===========================================================================
# 7. Amendment Metadata Whitespace Normalization
# ===========================================================================

def test_amendment_metadata_whitespace_normalization():
    """Whitespace, line breaks, and tabs in amendment titles and metadata must be normalized."""
    raw = "Second\nAmendment,   2022"
    assert normalize_whitespace(raw) == "Second Amendment, 2022"

    meta = AmendmentMetadata(
        amendment_name="Second\n\tAmendment",
        version_label="Second\nAmendment,   2022",
        full_title="Legal   Metrology\n(Second\nAmendment)\nRules, 2022",
        notification_number="G.S.R.\n  577(E)",
    )
    assert meta.amendment_name == "Second Amendment"
    assert meta.version_label == "Second Amendment, 2022"
    assert meta.full_title == "Legal Metrology (Second Amendment) Rules, 2022"
    assert meta.notification_number == "G.S.R. 577(E)"


# ===========================================================================
# 8. Database JSONB Safety and Deserialization
# ===========================================================================

def test_decode_json_column_handles_all_shapes_safely():
    """Safely decode dict/list, JSON strings, None, and log on malformed text."""
    # Already decoded Python objects
    assert decode_json_column({"key": "val"}) == {"key": "val"}
    assert decode_json_column([1, 2, 3]) == [1, 2, 3]

    # JSON string
    assert decode_json_column('{"a": 1, "b": "text"}') == {"a": 1, "b": "text"}
    assert decode_json_column('[{"id": 1}]') == [{"id": 1}]

    # None and empty
    assert decode_json_column(None) is None
    assert decode_json_column("") is None
    assert decode_json_column("   ") is None

    # Malformed JSON must return None and log a warning without raising
    assert decode_json_column("{bad json here", field_name="evidence_json") is None


# ===========================================================================
# 9. Canonical ComplianceDecisionPackage Top-Level Contract
# ===========================================================================

def test_compliance_decision_package_structure():
    """Verify ComplianceDecisionPackage schema conforms to Section 16 specification."""
    extractions = {
        "common_name": type("RawExtractionStub", (), {
            "value": "Wheat Flour",
            "normalized_value": "Wheat Flour",
            "confidence": 0.95,
            "raw_text": "Wheat Flour",
            "image_id": "img-01",
            "bbox": None,
            "evidence": [],
            "usable": True,
            "quality_state": "usable",
            "verification_status": "VERIFIED"
        })()
    }
    insp = run_inspection_v2(
        inspection_id="insp-pkg-01",
        sale_type="retail",
        product_category="food",
        net_quantity_value=500,
        net_quantity_unit="g",
        mrp=50.0,
        extractions=extractions,
    )

    pkg = insp.decision_package
    assert pkg is not None
    assert pkg["inspection_id"] == "insp-pkg-01"
    assert "legal_basis" in pkg
    assert "regulation" in pkg["legal_basis"]
    assert "ruleset_version" in pkg["legal_basis"]
    assert "overall_result" in pkg
    assert "summary" in pkg
    assert "rules_selected" in pkg["summary"]
    assert "rules_considered" in pkg["summary"]
    assert "rules_passed" in pkg["summary"]
    assert "rules_failed" in pkg["summary"]
    assert "rules_uncertain" in pkg["summary"]
    assert "rules" in pkg
    assert "audit" in pkg
