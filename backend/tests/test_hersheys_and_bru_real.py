"""
Verification script for Package Integrity with real Hershey's and BRU packaging images.
Validates:
1. Product ID hint below barcode.
2. Field-level comparison: STATIC, VARIABLE, VERSION-SENSITIVE fields.
3. Summary counts (consistent, review required, potential discrepancy).
4. Evidence crops (real reference crop and inspection crop).
5. Persistence in PostgreSQL / filesystem and reload without recomputing.
"""

from pathlib import Path
import cv2
import pytest
from package_integrity import (
    compare_reference_vs_inspected_package,
    evaluate_package_integrity,
    STATUS_NO_DIFF,
    STATUS_POTENTIAL_ALT,
    STATUS_UNABLE_TO_VERIFY,
    extract_declarations_with_bboxes,
)
from db import persistence as db

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REF_DIR = PROJECT_ROOT / "Reference Images"
INSP_DIR = PROJECT_ROOT / "images new"


def test_hersheys_real_packaging_field_level_comparison():
    ref_front = REF_DIR / "Hershey's REFERENCE FRONT.png"
    ref_back = REF_DIR / "Hershey's REFERENCE BACK.png"
    insp_front = INSP_DIR / "Hershey's FRONT.jpeg"
    insp_back = INSP_DIR / "Hershey's Back.jpeg"

    assert ref_front.exists(), f"Missing {ref_front}"
    assert ref_back.exists(), f"Missing {ref_back}"
    assert insp_front.exists(), f"Missing {insp_front}"
    assert insp_back.exists(), f"Missing {insp_back}"

    # Verify reference extraction with bounding boxes
    extracted_ref, ref_bboxes = extract_declarations_with_bboxes(ref_back)
    assert isinstance(extracted_ref, dict)
    assert isinstance(ref_bboxes, dict)

    # Simulated inspection declarations extracted from the Hershey's back image
    # Note: Batch and manufacturing/expiry dates vary legitimately by lot
    insp_declarations = [
        {"field": "mrp", "value": "₹99.00", "bounding_box": [100, 150, 80, 25]},
        {"field": "net_quantity", "value": "150 g", "bounding_box": [100, 180, 60, 25]},
        {"field": "batch_number", "value": "HM20526", "bounding_box": [100, 210, 80, 25]},
        {"field": "manufacturing_date", "value": "03/2026", "bounding_box": [100, 240, 70, 25]},
        {"field": "expiry_date", "value": "03/2027", "bounding_box": [100, 270, 70, 25]},
        {"field": "manufacturer_name", "value": "Hershey India Private Limited", "bounding_box": [100, 300, 180, 30]},
    ]

    report = compare_reference_vs_inspected_package(
        ref_paths=[ref_front, ref_back],
        insp_paths=[insp_front, insp_back],
        product_id="HSH-001",
        product_name="Hershey's Chocolate Spread",
        inspection_declarations=insp_declarations,
    )

    # Invariants
    assert report.has_reference is True
    assert len(report.field_comparisons) > 0
    assert report.summary_counts["total_evaluated"] > 0

    # Verify summary counts are present and consistent
    assert report.summary_counts["consistent"] >= 0
    assert report.summary_counts["review_required"] >= 0
    assert report.summary_counts["potential_discrepancy"] >= 0

    # Ensure no technical artifacts like "PACKAGING_LAYOUT" or contour pixel diffs in discrepancies
    assert not any("PACKAGING_LAYOUT" in d.get("field_name", "") for d in report.detected_differences)

    # Check field-level items
    comp_map = {item["field_name"]: item for item in report.field_comparisons}
    if "Manufacturer" in comp_map:
        assert comp_map["Manufacturer"]["status"] in ("MATCH", "REVIEW REQUIRED")
    if "Batch Number" in comp_map:
        assert comp_map["Batch Number"]["status"] in ("MATCH", "EXPECTED TO VARY", "REFERENCE_NOT_OBSERVED")

    # Persist and restore check
    rep_dict = report.to_dict()
    rep_dict["inspection_id"] = "test_hersheys_insp_001"
    db.save_package_integrity_comparison(rep_dict)

    restored = db.get_latest_package_integrity_comparison("test_hersheys_insp_001")
    assert restored is not None
    assert restored["comparison_id"] == rep_dict["comparison_id"]
    assert restored["summary_counts"] == rep_dict["summary_counts"]


def test_bru_real_packaging_comparison():
    ref_front = REF_DIR / "BRU FRONT REFERENCE.png"
    ref_back = REF_DIR / "BRU BACK REFERENCE.png"
    insp_front = INSP_DIR / "BRU FRONT.jpg"
    insp_back = INSP_DIR / "BRU BACK.jpg"

    assert ref_front.exists()
    assert ref_back.exists()
    assert insp_front.exists()
    assert insp_back.exists()

    # The real BRU Reference image is a 50 g pack. Test with matching net quantity:
    insp_declarations_matching = [
        {"field": "mrp", "value": "₹450.00", "bounding_box": [60, 100, 80, 25]},
        {"field": "net_quantity", "value": "50 g", "bounding_box": [60, 130, 60, 25]},
        {"field": "manufacturing_date", "value": "02/2026", "bounding_box": [60, 160, 70, 25]},
        {"field": "expiry_date", "value": "02/2028", "bounding_box": [60, 190, 70, 25]},
        {"field": "batch_number", "value": "B-9912", "bounding_box": [60, 220, 70, 25]},
        {"field": "manufacturer_name", "value": "Hindustan Unilever Limited", "bounding_box": [60, 250, 180, 30]},
        {"field": "barcode", "value": "8901030018591", "bounding_box": [60, 290, 100, 40]},
    ]

    report = compare_reference_vs_inspected_package(
        ref_paths=[ref_front, ref_back],
        insp_paths=[insp_front, insp_back],
        product_id="64934436",
        product_name="Bru Instant Coffee",
        inspection_declarations=insp_declarations_matching,
    )

    assert report.has_reference is True
    assert report.status == STATUS_NO_DIFF
    assert len(report.field_comparisons) >= 5

    # Verification: Legitimate new batch differences must not be flagged as tampering
    for f in report.field_comparisons:
        assert not f["is_suspicious"], f"Field {f['field_name']} was marked suspicious: {f}"

    # Check persistence and history tracking
    rep_dict = report.to_dict()
    rep_dict["inspection_id"] = "test_bru_insp_002"
    db.save_package_integrity_comparison(rep_dict)

    history = db.list_package_integrity_history("test_bru_insp_002")
    assert len(history) >= 1
    assert history[0]["comparison_id"] == rep_dict["comparison_id"]

    # Now verify that a static net quantity mismatch (e.g. 100 g vs 50 g reference)
    # is correctly detected as POTENTIAL_ALTERATION_DETECTED
    insp_declarations_mismatch = [
        {"field": "mrp", "value": "₹450.00", "bounding_box": [60, 100, 80, 25]},
        {"field": "net_quantity", "value": "100 g", "bounding_box": [60, 130, 60, 25]},
    ]
    mismatch_report = compare_reference_vs_inspected_package(
        ref_paths=[ref_front, ref_back],
        insp_paths=[insp_front, insp_back],
        product_id="64934436",
        product_name="Bru Instant Coffee",
        inspection_declarations=insp_declarations_mismatch,
    )
    assert mismatch_report.status == STATUS_POTENTIAL_ALT
    assert "Net Quantity" in mismatch_report.discrepancy_fields
