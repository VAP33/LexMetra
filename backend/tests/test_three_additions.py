"""
Unit and Integration tests for the Three Additions:
1. Smart Mobile Capture Readiness
2. Package Integrity Verification (Planar & Curved, Declaration comparison, Reference Types)
3. FSSAI Cross-Verification (Provider interface, FoSCoS fallback, Food applicability)
"""

import base64
import os
from pathlib import Path
import cv2
import numpy as np
import pytest

import fssai_verification
import package_integrity
from fssai_verification import (
    DemoFSSAIProvider,
    OfficialFSSAIAdapter,
    STATE_DEMO_VERIFIED,
    STATE_LICENSE_NOT_FOUND,
    STATE_NOT_APPLICABLE,
    STATE_UNABLE_TO_VERIFY,
    STATE_VERIFIED,
    verify_fssai_compliance,
)
from package_integrity import (
    FIELD_CLASS_STATIC,
    FIELD_CLASS_VARIABLE,
    FIELD_CLASS_VERSION_SENSITIVE,
    FINDING_ACTUAL_DIFFERENCE,
    FINDING_INSUFFICIENT_IMAGE_QUALITY,
    FINDING_LEGITIMATE_VARIATION,
    FINDING_OCR_UNCERTAINTY,
    REF_TYPE_DEMO,
    REF_TYPE_TRUSTED,
    REF_TYPE_UNVERIFIED,
    STATUS_NO_DIFF,
    STATUS_POTENTIAL_ALT,
    STATUS_UNABLE_TO_VERIFY,
    assess_region_quality,
    compare_declarations,
    compare_reference_vs_inspected_package,
    compute_ocr_similarity,
    evaluate_package_integrity,
    normalize_ocr_text,
)


# ===========================================================================
# 1. SMART MOBILE CAPTURE READINESS TESTS
# ===========================================================================

def test_capture_readiness_clear_frame():
    """Verify capture readiness evaluation on a sharp synthetic package image."""
    from main import assess_capture_readiness, CaptureReadinessInput

    # Create a sharp image with a centered package rectangle
    img = np.ones((400, 300, 3), dtype=np.uint8) * 200
    cv2.rectangle(img, (50, 40), (250, 360), (40, 80, 160), -1)
    cv2.putText(img, "LEXMETRA SAMPLE", (60, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    _, buf = cv2.imencode(".jpg", img)
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")

    res = assess_capture_readiness(CaptureReadinessInput(image_base64=b64))
    assert "is_ready" in res
    assert "guidance" in res
    assert "corners" in res
    assert len(res["corners"]) == 4


def test_capture_readiness_blurry_frame():
    """Verify blur is detected and guidance says 'Hold steady'."""
    from main import assess_capture_readiness, CaptureReadinessInput

    # Heavily blurred image has low Laplacian variance
    img = np.ones((300, 300, 3), dtype=np.uint8) * 128
    blurred = cv2.GaussianBlur(img, (25, 25), 10)
    _, buf = cv2.imencode(".jpg", blurred)
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")

    res = assess_capture_readiness(CaptureReadinessInput(image_base64=b64))
    assert res["is_ready"] is False
    assert "Hold steady" in res["guidance"]


def test_capture_readiness_glare_frame():
    """Verify glare is detected and guidance asks to reduce glare."""
    from main import assess_capture_readiness, CaptureReadinessInput

    # Saturated white glare over half the image
    img = np.ones((300, 300, 3), dtype=np.uint8) * 100
    img[:200, :200] = 255
    _, buf = cv2.imencode(".jpg", img)
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")

    res = assess_capture_readiness(CaptureReadinessInput(image_base64=b64))
    assert res["is_ready"] is False
    assert "glare" in res["guidance"].lower()


# ===========================================================================
# 2. PACKAGE INTEGRITY VERIFICATION TESTS
# ===========================================================================

def test_package_integrity_status_invariants():
    """Status must strictly be one of NO_SIGNIFICANT_DIFFERENCE_DETECTED, POTENTIAL_ALTERATION_DETECTED, UNABLE_TO_VERIFY."""
    allowed_statuses = {
        STATUS_NO_DIFF,
        STATUS_POTENTIAL_ALT,
        STATUS_UNABLE_TO_VERIFY,
    }

    # Missing image returns UNABLE_TO_VERIFY
    res_none = evaluate_package_integrity(None, product_id="unknown_sku")
    assert res_none.status in allowed_statuses
    assert res_none.status == STATUS_UNABLE_TO_VERIFY


def test_declaration_comparison_mrp_mismatch():
    """Test that clean MRP difference is classified as VERSION_SENSITIVE (not tampering)."""
    ref_decls = {
        "mrp": "₹420.00",
        "net_quantity": "100 g",
        "manufacturing_date": "12/2025",
        "manufacturer_name": "Hindustan Unilever Limited",
    }

    insp_decls = [
        {"field": "mrp", "value": "₹450.00", "bounding_box": [50, 120, 80, 30]},
        {"field": "net_quantity", "value": "100 g", "bounding_box": [50, 160, 60, 25]},
    ]

    dummy_img = np.ones((300, 300, 3), dtype=np.uint8) * 180
    diffs = compare_declarations(ref_decls, insp_decls, dummy_img)

    assert len(diffs) >= 1
    mrp_diff = next((d for d in diffs if d["field_name"] == "MRP"), None)
    assert mrp_diff is not None
    assert mrp_diff["reference_value"] == "₹420.00"
    assert mrp_diff["inspection_value"] == "₹450.00"
    assert mrp_diff["field_classification"] == FIELD_CLASS_VERSION_SENSITIVE
    assert mrp_diff["is_suspicious"] is False
    assert "packaging price update" in mrp_diff["difference_type"].lower()
    assert mrp_diff["confidence"] >= 0.90
    assert mrp_diff["severity"] == "MEDIUM"
    assert mrp_diff["evidence_crop_base64"] is not None


def test_bru_primary_test_case_legitimate_new_batch():
    """
    PRIMARY TEST CASE:
    Verify that a legitimate new batch of BRU Instant Coffee with:
    - New Batch: B-9912 (vs reference B-8472)
    - New Dates: MFD 02/2026, Expiry 02/2028 (vs reference 12/2025, 12/2027)
    - Updated Price: ₹450.00 (vs reference ₹420.00)
    - Identical static fields: Net Qty (100 g), Manufacturer (HUL), Barcode (8901030018591), FSSAI (10012022000258)
    is NOT falsely classified as tampered, and evaluates to NO_SIGNIFICANT_DIFFERENCE_DETECTED.
    """
    ref_decls = {
        "mrp": "₹420.00",
        "net_quantity": "100 g",
        "manufacturing_date": "12/2025",
        "expiry_date": "12/2027",
        "batch_number": "B-8472",
        "manufacturer_name": "Hindustan Unilever Limited",
        "consumer_care": "1800-10-22-221, lever.care@unilever.com",
        "fssai_license_number": "10012022000258",
        "barcode": "8901030018591",
    }

    # Inspected package represents a genuine new factory batch
    insp_decls = [
        {"field": "mrp", "value": "₹450.00", "bounding_box": [50, 100, 80, 25]},
        {"field": "net_quantity", "value": "100 g", "bounding_box": [50, 130, 60, 25]},
        {"field": "manufacturing_date", "value": "02/2026", "bounding_box": [50, 160, 70, 25]},
        {"field": "expiry_date", "value": "02/2028", "bounding_box": [50, 190, 70, 25]},
        {"field": "batch_number", "value": "B-9912", "bounding_box": [50, 220, 70, 25]},
        {"field": "manufacturer_name", "value": "Hindustan Unilever Limited", "bounding_box": [50, 250, 180, 30]},
        {"field": "barcode", "value": "8901030018591", "bounding_box": [50, 290, 100, 40]},
        {"field": "fssai_license_number", "value": "10012022000258", "bounding_box": [50, 340, 110, 25]},
    ]

    dummy_img = np.ones((400, 400, 3), dtype=np.uint8) * 200
    diffs = compare_declarations(ref_decls, insp_decls, dummy_img)

    # All detected differences must be legitimate production updates
    assert len(diffs) > 0
    for d in diffs:
        assert d["is_suspicious"] is False, f"Difference on {d['field_name']} was falsely marked suspicious: {d}"
        assert d["field_classification"] in (FIELD_CLASS_VARIABLE, FIELD_CLASS_VERSION_SENSITIVE)

    # Simulated full package comparison with matching geometry
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f_ref, \
         tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f_insp:
        cv2.imwrite(f_ref.name, dummy_img)
        cv2.imwrite(f_insp.name, dummy_img)
        ref_path = Path(f_ref.name)
        insp_path = Path(f_insp.name)

    try:
        report = compare_reference_vs_inspected_package(
            ref_path=ref_path,
            insp_path=insp_path,
            ref_type=REF_TYPE_TRUSTED,
            ref_metadata={"declarations": ref_decls, "is_curved": False},
            product_id="64934436",
            product_name="Bru Instant Coffee Jar 100g",
            inspection_declarations=insp_decls,
        )

        # Primary invariant: Must evaluate to NO_SIGNIFICANT_DIFFERENCE_DETECTED
        assert report.status == STATUS_NO_DIFF
        assert "legitimate" in report.explanation.lower() or "verified" in report.explanation.lower()
        assert not any(d.get("is_suspicious") for d in report.detected_differences)
    finally:
        if ref_path.exists():
            ref_path.unlink()
        if insp_path.exists():
            insp_path.unlink()


def test_impossible_date_chronology_flagged_as_tampering():
    """Verify that impossible date sequence (MFD later than Expiry) triggers POTENTIAL_ALTERATION_DETECTED."""
    ref_decls = {
        "manufacturing_date": "12/2025",
        "expiry_date": "12/2027",
    }

    # Inspected has impossible dates: MFD 02/2028, Expiry 02/2025
    insp_decls = [
        {"field": "manufacturing_date", "value": "02/2028", "bounding_box": [50, 100, 70, 25]},
        {"field": "expiry_date", "value": "02/2025", "bounding_box": [50, 130, 70, 25]},
    ]

    dummy_img = np.ones((300, 300, 3), dtype=np.uint8) * 180
    diffs = compare_declarations(ref_decls, insp_decls, dummy_img)

    suspicious = [d for d in diffs if d.get("is_suspicious")]
    assert len(suspicious) >= 1
    date_diff = next(d for d in suspicious if "Impossible date" in d["difference_type"])
    assert date_diff["severity"] == "HIGH"
    assert date_diff["field_classification"] == FIELD_CLASS_VARIABLE


def test_static_field_mismatch_flagged_as_tampering():
    """Verify that alteration to STATIC fields (barcode, manufacturer) triggers POTENTIAL_ALTERATION_DETECTED."""
    ref_decls = {
        "barcode": "8901030018591",
        "manufacturer_name": "Hindustan Unilever Limited",
        "net_quantity": "100 g",
    }

    # Inspected has altered counterfeit barcode and manufacturer
    insp_decls = [
        {"field": "barcode", "value": "8909999999999", "bounding_box": [50, 100, 100, 40]},
        {"field": "manufacturer_name", "value": "Counterfeit Packagers Pvt Ltd", "bounding_box": [50, 150, 150, 30]},
        {"field": "net_quantity", "value": "100 g", "bounding_box": [50, 190, 60, 25]},
    ]

    dummy_img = np.ones((300, 300, 3), dtype=np.uint8) * 180
    diffs = compare_declarations(ref_decls, insp_decls, dummy_img)

    suspicious = [d for d in diffs if d.get("is_suspicious")]
    assert len(suspicious) == 2
    for s in suspicious:
        assert s["field_classification"] == FIELD_CLASS_STATIC
        assert s["severity"] == "HIGH"


def test_ocr_character_substitutions_and_spacing_robustness():
    """
    Verify that common OCR optical errors:
    - Character substitutions (0 vs O, 1 vs I/l, 5 vs S)
    - Abbreviation differences (Ltd vs Limited, Pvt vs Private)
    - Spacing & punctuation differences
    do NOT result in false tampering, and are categorized as FINDING_OCR_UNCERTAINTY.
    """
    # 1. Direct similarity check
    _, sim_barcode, reason_bc = compute_ocr_similarity("8901030018591", "8901O3OO18591")
    assert sim_barcode >= 0.90
    assert "OCR character substitutions" in reason_bc

    _, sim_mfg, reason_mfg = compute_ocr_similarity(
        "Hindustan Unilever Limited", "Hlndustan Unilever Ltd."
    )
    assert sim_mfg >= 0.82

    # 2. Declaration comparison check
    ref_decls = {
        "barcode": "8901030018591",
        "manufacturer_name": "Hindustan Unilever Limited",
        "consumer_care": "1800-10-22-221, lever.care@unilever.com",
    }
    insp_decls = [
        {"field": "barcode", "value": "8901O3OO18591", "confidence": 0.89, "bounding_box": [50, 50, 100, 30]},
        {"field": "manufacturer_name", "value": "Hlndustan Unilever Ltd", "confidence": 0.86, "bounding_box": [50, 100, 180, 30]},
        {"field": "consumer_care", "value": "1800 10 22 221 lever care@unilever com", "confidence": 0.90, "bounding_box": [50, 140, 200, 25]},
    ]

    dummy_img = np.ones((300, 300, 3), dtype=np.uint8) * 200
    diffs = compare_declarations(ref_decls, insp_decls, dummy_img)

    for d in diffs:
        assert d["is_suspicious"] is False, f"Falsely marked suspicious: {d}"
        assert d["finding_category"] == FINDING_OCR_UNCERTAINTY
        assert d["severity"] == "LOW"
        assert d["ocr_confidence"] >= 0.85
        assert d["evidence_crop_base64"] is not None


def test_insufficient_image_quality_prevents_false_tampering():
    """
    Verify that low image quality (severe blur, glare) or low OCR confidence:
    - Sets finding_category to FINDING_INSUFFICIENT_IMAGE_QUALITY
    - Never results in POTENTIAL_ALTERATION_DETECTED
    - Resolves status to UNABLE_TO_VERIFY (with inspector guidance)
    """
    ref_decls = {
        "barcode": "8901030018591",
        "manufacturer_name": "Hindustan Unilever Limited",
    }

    # Low OCR confidence due to blur/glare on printed text
    insp_decls = [
        {"field": "barcode", "value": "890???????", "confidence": 0.45, "bounding_box": [40, 40, 90, 30]},
        {"field": "manufacturer_name", "value": "H??? ??", "confidence": 0.40, "bounding_box": [40, 80, 120, 25]},
    ]

    dummy_img = np.ones((300, 300, 3), dtype=np.uint8) * 180
    diffs = compare_declarations(ref_decls, insp_decls, dummy_img)

    quality_diffs = [d for d in diffs if d.get("finding_category") == FINDING_INSUFFICIENT_IMAGE_QUALITY]
    assert len(quality_diffs) >= 1
    for q in quality_diffs:
        assert q["is_suspicious"] is False

    # Full package evaluation check
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f_ref, \
         tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f_insp:
        cv2.imwrite(f_ref.name, dummy_img)
        cv2.imwrite(f_insp.name, dummy_img)
        ref_path = Path(f_ref.name)
        insp_path = Path(f_insp.name)

    try:
        report = compare_reference_vs_inspected_package(
            ref_path=ref_path,
            insp_path=insp_path,
            ref_type=REF_TYPE_TRUSTED,
            ref_metadata={"declarations": ref_decls},
            product_id="test_sku",
            inspection_declarations=insp_decls,
        )
        # Invariant: Never turn poor image/OCR quality into a tampering conclusion
        assert report.status != STATUS_POTENTIAL_ALT
        assert report.status == STATUS_UNABLE_TO_VERIFY
        assert "insufficient image quality" in report.explanation.lower()
    finally:
        if ref_path.exists():
            ref_path.unlink()
        if insp_path.exists():
            insp_path.unlink()


def test_minor_ocr_discrepancy_results_in_no_false_tampering():
    """
    Verify that a minor OCR typo alone evaluates to NO_SIGNIFICANT_DIFFERENCE_DETECTED
    with advisory note, preserving crops for manual verification.
    """
    ref_decls = {
        "manufacturer_name": "Hindustan Unilever Limited",
        "net_quantity": "100 g",
    }
    # Minor single-character OCR substitution in manufacturer
    insp_decls = [
        {"field": "manufacturer_name", "value": "Hlndustan Unilever Limited", "confidence": 0.92, "bounding_box": [50, 50, 160, 30]},
        {"field": "net_quantity", "value": "100 g", "confidence": 0.95, "bounding_box": [50, 90, 60, 20]},
    ]

    dummy_img = np.ones((300, 300, 3), dtype=np.uint8) * 200
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f_ref, \
         tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f_insp:
        cv2.imwrite(f_ref.name, dummy_img)
        cv2.imwrite(f_insp.name, dummy_img)
        ref_path = Path(f_ref.name)
        insp_path = Path(f_insp.name)

    try:
        report = compare_reference_vs_inspected_package(
            ref_path=ref_path,
            insp_path=insp_path,
            ref_type=REF_TYPE_TRUSTED,
            ref_metadata={"declarations": ref_decls},
            product_id="test_sku",
            inspection_declarations=insp_decls,
        )
        assert report.status == STATUS_NO_DIFF
        assert not any(d.get("is_suspicious") for d in report.detected_differences)
        assert any(d.get("finding_category") == FINDING_OCR_UNCERTAINTY for d in report.detected_differences)
        # Evidence crop is preserved
        diff_item = next(d for d in report.detected_differences if d.get("finding_category") == FINDING_OCR_UNCERTAINTY)
        assert diff_item.get("evidence_crop_base64") is not None
    finally:
        if ref_path.exists():
            ref_path.unlink()
        if insp_path.exists():
            insp_path.unlink()


def test_multi_signal_or_high_confidence_mismatch_flags_tampering():
    """
    Verify that genuine counterfeits with high-confidence static mismatch
    or multiple independent discrepancies trigger POTENTIAL_ALTERATION_DETECTED.
    """
    ref_decls = {
        "barcode": "8901030018591",
        "manufacturer_name": "Hindustan Unilever Limited",
        "net_quantity": "100 g",
    }
    insp_decls = [
        {"field": "barcode", "value": "8909999999999", "confidence": 0.95, "bounding_box": [50, 50, 100, 35]},
        {"field": "manufacturer_name", "value": "Bogus Foods Pvt Ltd", "confidence": 0.92, "bounding_box": [50, 100, 150, 30]},
        {"field": "net_quantity", "value": "50 g", "confidence": 0.96, "bounding_box": [50, 140, 60, 20]},
    ]

    dummy_img = np.ones((300, 300, 3), dtype=np.uint8) * 200
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f_ref, \
         tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f_insp:
        cv2.imwrite(f_ref.name, dummy_img)
        cv2.imwrite(f_insp.name, dummy_img)
        ref_path = Path(f_ref.name)
        insp_path = Path(f_insp.name)

    try:
        report = compare_reference_vs_inspected_package(
            ref_path=ref_path,
            insp_path=insp_path,
            ref_type=REF_TYPE_TRUSTED,
            ref_metadata={"declarations": ref_decls},
            product_id="test_sku",
            inspection_declarations=insp_decls,
        )
        assert report.status == STATUS_POTENTIAL_ALT
        assert "potential packaging alteration detected" in report.explanation.lower()
        suspicious = [d for d in report.detected_differences if d.get("is_suspicious")]
        assert len(suspicious) >= 2
        for s in suspicious:
            assert s.get("finding_category") == FINDING_ACTUAL_DIFFERENCE
            assert s.get("evidence_crop_base64") is not None
    finally:
        if ref_path.exists():
            ref_path.unlink()
        if insp_path.exists():
            insp_path.unlink()


def test_package_integrity_no_readymade_by_default():
    """Verify that by default, no readymade images are used and integrity requires an explicit reference."""
    res = evaluate_package_integrity(None, product_id="64934436", product_name="Bru Instant Coffee")
    assert res.has_reference is False
    assert res.status == STATUS_UNABLE_TO_VERIFY
    assert "No Reference Packaging Standard provided" in res.explanation


def test_package_integrity_demo_products():
    """Verify deterministic integrity evaluation when demo fixtures are explicitly enabled."""
    # 1. Bru
    bru_res = evaluate_package_integrity(None, product_id="64934436", product_name="Bru Instant Coffee", allow_demo_fixtures=True)
    assert bru_res.has_reference is True
    assert bru_res.reference_type == REF_TYPE_DEMO

    # 2. Vaseline (curved packaging profile)
    vas_res = evaluate_package_integrity(None, product_name="Vaseline Healthy Bright Body Lotion", allow_demo_fixtures=True)
    assert vas_res.has_reference is True
    assert vas_res.reference_type == REF_TYPE_DEMO

    # 3. Good Knight
    gk_res = evaluate_package_integrity(None, product_name="Good Knight Active+", allow_demo_fixtures=True)
    assert gk_res.has_reference is True
    assert gk_res.reference_type == REF_TYPE_DEMO


def test_multi_face_reference_upload_and_cross_face_alignment():
    """
    Verify that multiple reference faces (e.g. Front and Back) can be evaluated against
    multiple inspected surfaces, computing cross-face alignment and merging declarations.
    """
    import tempfile
    dummy_ref_front = np.ones((300, 300, 3), dtype=np.uint8) * 180
    cv2.putText(dummy_ref_front, "BRU FRONT", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    dummy_ref_back = np.ones((300, 300, 3), dtype=np.uint8) * 220
    cv2.putText(dummy_ref_back, "BRU BACK", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    dummy_insp_1 = np.ones((300, 300, 3), dtype=np.uint8) * 180
    cv2.putText(dummy_insp_1, "BRU FRONT", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    dummy_insp_2 = np.ones((300, 300, 3), dtype=np.uint8) * 220
    cv2.putText(dummy_insp_2, "BRU BACK", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f_rf, \
         tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f_rb, \
         tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f_i1, \
         tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f_i2:
        cv2.imwrite(f_rf.name, dummy_ref_front)
        cv2.imwrite(f_rb.name, dummy_ref_back)
        cv2.imwrite(f_i1.name, dummy_insp_1)
        cv2.imwrite(f_i2.name, dummy_insp_2)
        rf_path = Path(f_rf.name)
        rb_path = Path(f_rb.name)
        i1_path = Path(f_i1.name)
        i2_path = Path(f_i2.name)

    try:
        report = compare_reference_vs_inspected_package(
            ref_path=[rf_path, rb_path],
            insp_path=[i1_path, i2_path],
            ref_type=REF_TYPE_UNVERIFIED,
            ref_metadata={"declarations": {"product_identity": "Bru Instant Coffee"}},
            product_id="64934436",
            product_name="Bru Instant Coffee",
        )

        assert report.has_reference is True
        assert len(report.reference_image_urls) == 2
        assert len(report.face_matches) == 2
        assert report.face_matches[0]["reference_face_index"] == 1
        assert report.face_matches[1]["reference_face_index"] == 2
        assert report.face_matches[0]["inspected_face_index"] is not None
        assert report.confidence_score > 0.0
    finally:
        for p in [rf_path, rb_path, i1_path, i2_path]:
            if p.exists():
                p.unlink()


def test_evaluate_package_integrity_custom_multiple_references():
    """Verify evaluate_package_integrity correctly accepts and processes custom_reference_paths list."""
    import tempfile
    dummy_img = np.ones((200, 200, 3), dtype=np.uint8) * 200
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1, \
         tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2, \
         tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fi:
        cv2.imwrite(f1.name, dummy_img)
        cv2.imwrite(f2.name, dummy_img)
        cv2.imwrite(fi.name, dummy_img)
        p1 = f1.name
        p2 = f2.name
        pi = fi.name

    try:
        res = evaluate_package_integrity(
            inspected_image_paths=[pi],
            custom_reference_paths=[p1, p2],
            custom_reference_type=REF_TYPE_TRUSTED,
            product_name="Multi Face Sample",
        )
        assert res.has_reference is True
        assert res.reference_type == REF_TYPE_TRUSTED
        assert len(res.reference_image_urls) == 2
        assert len(res.face_matches) == 2
    finally:
        for p in [p1, p2, pi]:
            if os.path.exists(p):
                os.remove(p)


# ===========================================================================
# 3. FSSAI CROSS-VERIFICATION TESTS
# ===========================================================================

def test_fssai_food_product_verification():
    """Verify FSSAI is active for food product (Bru) and returns DEMO_VERIFIED with license details."""
    raw_fields = {
        "product_name": "Bru Instant Coffee",
        "fssai_license_number": "10012022000258",
        "manufacturer_name": "Hindustan Unilever Limited",
    }

    res = verify_fssai_compliance("food", raw_fields)
    assert res.is_food is True
    assert res.status == STATE_DEMO_VERIFIED
    assert res.license_number == "10012022000258"
    assert res.registry_licensee == "Hindustan Unilever Limited"
    assert res.is_demo_data is True
    assert "DEMO DATA" in res.explanation


def test_fssai_non_food_not_applicable():
    """Verify FSSAI returns NOT_APPLICABLE for non-food products (Vaseline, Good Knight)."""
    # Vaseline (cosmetic lotion)
    vas_res = verify_fssai_compliance("cosmetic", {"product_name": "Vaseline Lotion"})
    assert vas_res.is_food is False
    assert vas_res.status == STATE_NOT_APPLICABLE

    # Good Knight (household insecticide)
    gk_res = verify_fssai_compliance("repellent", {"product_name": "Good Knight Active+"})
    assert gk_res.is_food is False
    assert gk_res.status == STATE_NOT_APPLICABLE


def test_fssai_license_not_found():
    """Verify food product missing mandatory FSSAI number returns LICENSE_NOT_FOUND."""
    res = verify_fssai_compliance("food", {"product_name": "Unbranded Snack"})
    assert res.is_food is True
    assert res.status == STATE_LICENSE_NOT_FOUND


def test_fssai_official_adapter_unavailable_fallback():
    """
    Official adapter without credentials must NOT invent API endpoints,
    must report UNABLE_TO_VERIFY ('UNABLE TO VERIFY EXTERNALLY') and provide official portal URL.
    """
    adapter = OfficialFSSAIAdapter(api_key=None)
    res = adapter.verify_license("10012022000258", declared_manufacturer="Hindustan Unilever")

    assert res.status == STATE_UNABLE_TO_VERIFY
    assert "UNABLE TO VERIFY EXTERNALLY" in res.explanation
    assert res.official_verification_url == "https://foscos.fssai.gov.in/"
    assert res.details.get("manual_verification_required") is True
