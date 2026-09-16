"""
Automated unit & performance tests for the Fast CV & Multi-Image Batch Pipeline.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import cv2
import numpy as np

from cv_pipeline import CVPipeline, run_cv_pipeline, run_batch_pipeline, fuse_multi_surface_package
from paddle_ocr_service import get_paddle_ocr

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
IMAGES_DIR = PROJECT_ROOT / "dataset" / "images"


def test_ocr_service_speed_and_accuracy():
    """Verify OCR service extracts all Legal Metrology declarations accurately."""
    ocr = get_paddle_ocr()
    sample_img = IMAGES_DIR / "prod001_compliant.png"
    assert sample_img.exists(), f"Sample image missing at {sample_img}"

    img = cv2.imread(str(sample_img))
    t0 = time.time()
    readings = ocr.read_text(img)
    duration = time.time() - t0

    assert len(readings) >= 5, f"Expected at least 5 OCR lines, got {len(readings)}"
    assert duration < 5.0, f"OCR too slow: {duration:.2f}s"

    all_text = " ".join(r.text for r in readings)
    assert "263" in all_text or "MRP" in all_text or "Juice" in all_text


def test_cv_pipeline_single_run():
    """Verify 10-stage CV pipeline produces COMPLIANT and VIOLATION verdicts accurately."""
    compliant_img = IMAGES_DIR / "prod001_compliant.png"
    violation_img = IMAGES_DIR / "prod001_violation_missing_mfg_date.png"

    res_comp = run_cv_pipeline(compliant_img, product_category="beverage")
    assert res_comp.success
    assert res_comp.compliance_verdict == "COMPLIANT"
    assert res_comp.structured_data.mrp is not None
    assert res_comp.structured_data.net_quantity is not None
    assert res_comp.visual_overlay_bgr is not None

    res_viol = run_cv_pipeline(violation_img, product_category="beverage")
    assert res_viol.success
    assert res_viol.compliance_verdict == "VIOLATION"
    mfg_fact = next((f for f in res_viol.compliance_facts if f["field"] == "mfg_date"), None)
    assert mfg_fact is not None
    assert mfg_fact["status"] == "FAIL"


def test_batch_pipeline_multi_products():
    """Verify concurrent batch inspection of multiple different product packages."""
    sample_files = [
        "prod001_compliant.png",
        "prod001_violation_missing_mfg_date.png",
        "prod002_compliant.png",
        "prod003_compliant.png",
        "prod004_compliant.png",
    ]

    items = []
    for f in sample_files:
        p = IMAGES_DIR / f
        if p.exists():
            items.append((f, p.read_bytes()))

    assert len(items) >= 3

    t0 = time.time()
    batch_res = run_batch_pipeline(items, mode="batch_products", max_workers=4)
    total_time = time.time() - t0

    assert batch_res["status"] == "success"
    assert batch_res["total_scanned"] == len(items)
    assert len(batch_res["results"]) == len(items)
    assert batch_res["summary"]["compliant_count"] >= 1
    assert total_time < (len(items) * 3.0)


def test_multi_surface_package_fusion():
    """Verify multi-surface fusion merges declarations across surfaces."""
    sample_files = [
        "prod001_compliant.png",
        "prod002_compliant.png",
    ]

    items = []
    for f in sample_files:
        p = IMAGES_DIR / f
        if p.exists():
            items.append((f, p.read_bytes()))

    batch_res = run_batch_pipeline(items, mode="multi_surface", max_workers=2)
    assert batch_res["status"] == "success"
    assert batch_res["mode"] == "multi_surface_fusion"
    assert batch_res["evidence_coverage_percent"] > 50.0
    assert len(batch_res["surface_breakdown"]) == len(items)
