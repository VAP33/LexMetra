"""
Comprehensive Unit & Integration Test Suite for 10-Stage Computer Vision Pipeline.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

# Ensure backend is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from cv_pipeline import CVPipeline, RegionCrop, StructuredDeclarations, run_cv_pipeline
from paddle_ocr_service import PaddleOCRService
from yolo_detector import YOLODetector, YOLORegion, apply_nms, compute_iou

DATASET_IMAGES_DIR = BACKEND_DIR.parent / "dataset" / "images"


@pytest.fixture
def sample_image_bgr() -> np.ndarray:
    """Generate a clean synthetic test package image in BGR."""
    img = np.full((700, 500, 3), 245, dtype=np.uint8)
    # Header band
    cv2.rectangle(img, (0, 0), (500, 160), (173, 158, 94), -1)
    cv2.putText(img, "SURAJ FOODS", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    cv2.putText(img, "Fruit Juice", (30, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # Declarations
    cv2.putText(img, "Manufacturer: Suraj Industries Pvt Ltd, India", (30, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1)
    cv2.putText(img, "Net Quantity: 500 ml", (30, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2)
    cv2.putText(img, "Mfg Date: 04/2026", (30, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1)
    cv2.putText(img, "MRP: Rs. 199.00 (incl. of all taxes)", (30, 340), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2)
    cv2.putText(img, "Consumer Care: 1800-328-3286 | care@suraj.in", (30, 380), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1)

    return img


@pytest.fixture
def cv_pipeline_instance() -> CVPipeline:
    return CVPipeline()


# ---------------------------------------------------------------------------
# Stage 1: Image Input Tests
# ---------------------------------------------------------------------------

def test_stage1_load_image_from_numpy(cv_pipeline_instance: CVPipeline, sample_image_bgr: np.ndarray):
    loaded = cv_pipeline_instance.stage1_load_image(sample_image_bgr)
    assert isinstance(loaded, np.ndarray)
    assert loaded.shape == sample_image_bgr.shape


def test_stage1_load_image_from_pil(cv_pipeline_instance: CVPipeline, sample_image_bgr: np.ndarray):
    pil_img = Image.fromarray(cv2.cvtColor(sample_image_bgr, cv2.COLOR_BGR2RGB))
    loaded = cv_pipeline_instance.stage1_load_image(pil_img)
    assert isinstance(loaded, np.ndarray)
    assert loaded.shape == sample_image_bgr.shape


def test_stage1_load_image_from_bytes(cv_pipeline_instance: CVPipeline, sample_image_bgr: np.ndarray):
    _, buf = cv2.imencode(".png", sample_image_bgr)
    raw_bytes = buf.tobytes()
    loaded = cv_pipeline_instance.stage1_load_image(raw_bytes)
    assert isinstance(loaded, np.ndarray)
    assert loaded.shape == sample_image_bgr.shape


def test_stage1_load_image_invalid(cv_pipeline_instance: CVPipeline):
    with pytest.raises(FileNotFoundError):
        cv_pipeline_instance.stage1_load_image("non_existent_path_xyz.jpg")


# ---------------------------------------------------------------------------
# Stage 2: OpenCV Preprocessing Tests
# ---------------------------------------------------------------------------

def test_stage2_preprocess_for_detection(cv_pipeline_instance: CVPipeline, sample_image_bgr: np.ndarray):
    prep, scale = cv_pipeline_instance.stage2_preprocess_for_detection(sample_image_bgr, target_size=400)
    assert isinstance(prep, np.ndarray)
    assert max(prep.shape[:2]) <= 400
    assert 0.0 < scale <= 1.0
    # Must preserve 3 color channels
    assert prep.shape[2] == 3


# ---------------------------------------------------------------------------
# Stage 3 & 4: YOLO Detection and Bounding Box Tests
# ---------------------------------------------------------------------------

def test_stage3_detect_regions(cv_pipeline_instance: CVPipeline, sample_image_bgr: np.ndarray):
    regions = cv_pipeline_instance.stage3_detect_regions(sample_image_bgr)
    assert len(regions) > 0
    for r in regions:
        assert isinstance(r, YOLORegion)
        assert r.confidence > 0.0
        assert r.width > 0
        assert r.height > 0
        assert r.class_name in YOLODetector().classes or r.class_name == "declaration_panel"


def test_stage4_process_bounding_boxes(cv_pipeline_instance: CVPipeline, sample_image_bgr: np.ndarray):
    h, w = sample_image_bgr.shape[:2]
    raw_regions = [
        YOLORegion(class_name="mrp", class_id=0, confidence=0.92, bbox=(20, 100, 150, 130)),
        YOLORegion(class_name="net_quantity", class_id=1, confidence=0.88, bbox=(20, 140, 120, 170)),
    ]
    processed = cv_pipeline_instance.stage4_process_bounding_boxes(raw_regions, scale=0.5, orig_w=w, orig_h=h)
    assert len(processed) == 2
    # Because scale was 0.5, original coordinates should roughly double
    assert processed[0].x1 <= 40
    assert processed[0].x2 >= 300


def test_iou_and_nms():
    box1 = (10, 10, 50, 50)
    box2 = (10, 10, 50, 50)
    assert compute_iou(box1, box2) == pytest.approx(1.0)

    box3 = (100, 100, 150, 150)
    assert compute_iou(box1, box3) == pytest.approx(0.0)

    r1 = YOLORegion(class_name="mrp", class_id=0, confidence=0.95, bbox=(10, 10, 50, 50))
    r2 = YOLORegion(class_name="mrp", class_id=0, confidence=0.80, bbox=(12, 12, 48, 48))
    kept = apply_nms([r1, r2], iou_threshold=0.5)
    assert len(kept) == 1
    assert kept[0].confidence == 0.95


# ---------------------------------------------------------------------------
# Stage 5 & 6: Region Cropping and OpenCV Preprocessing AGAIN
# ---------------------------------------------------------------------------

def test_stage5_crop_regions(cv_pipeline_instance: CVPipeline, sample_image_bgr: np.ndarray):
    regions = [
        YOLORegion(class_name="mrp", class_id=0, confidence=0.9, bbox=(30, 320, 300, 360))
    ]
    crops = cv_pipeline_instance.stage5_crop_regions(sample_image_bgr, regions)
    assert len(crops) == 1
    assert crops[0].class_name == "mrp"
    assert crops[0].raw_crop.shape[0] == 40
    assert crops[0].raw_crop.shape[1] == 270


def test_stage6_preprocess_for_ocr(cv_pipeline_instance: CVPipeline):
    # Small test crop
    crop = np.full((25, 120, 3), 240, dtype=np.uint8)
    cv2.putText(crop, "MRP 199", (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

    enhanced = cv_pipeline_instance.stage6_preprocess_for_ocr(crop)
    # Target height should be upscaled to at least 90 px
    assert enhanced.shape[0] >= 90
    assert enhanced.shape[1] >= crop.shape[1]
    # Check contrast range
    assert enhanced.dtype == np.uint8
    assert enhanced.min() < 100
    assert enhanced.max() > 200


# ---------------------------------------------------------------------------
# Stage 8: Structured Data Parsing Tests
# ---------------------------------------------------------------------------

def test_stage8_extract_structured_data(cv_pipeline_instance: CVPipeline):
    crops = [
        RegionCrop(
            region_id="crop_0",
            class_name="mrp",
            confidence=0.92,
            original_bbox=(30, 320, 280, 350),
            raw_crop=np.zeros((10, 10, 3), dtype=np.uint8),
            enhanced_crop=np.zeros((10, 10, 3), dtype=np.uint8),
            ocr_text="MRP: Rs. 263.42 (incl. all taxes)",
            ocr_confidence=0.94,
        ),
        RegionCrop(
            region_id="crop_1",
            class_name="net_quantity",
            confidence=0.89,
            original_bbox=(30, 260, 200, 280),
            raw_crop=np.zeros((10, 10, 3), dtype=np.uint8),
            enhanced_crop=np.zeros((10, 10, 3), dtype=np.uint8),
            ocr_text="Net Quantity: 100 ml",
            ocr_confidence=0.91,
        ),
        RegionCrop(
            region_id="crop_2",
            class_name="mfg_date",
            confidence=0.85,
            original_bbox=(30, 290, 180, 310),
            raw_crop=np.zeros((10, 10, 3), dtype=np.uint8),
            enhanced_crop=np.zeros((10, 10, 3), dtype=np.uint8),
            ocr_text="Mfg Date: 04/2026",
            ocr_confidence=0.88,
        ),
        RegionCrop(
            region_id="crop_3",
            class_name="manufacturer",
            confidence=0.90,
            original_bbox=(30, 200, 380, 220),
            raw_crop=np.zeros((10, 10, 3), dtype=np.uint8),
            enhanced_crop=np.zeros((10, 10, 3), dtype=np.uint8),
            ocr_text="Suraj Industries Pvt Ltd, India",
            ocr_confidence=0.92,
        ),
        RegionCrop(
            region_id="crop_4",
            class_name="consumer_care",
            confidence=0.87,
            original_bbox=(30, 380, 400, 400),
            raw_crop=np.zeros((10, 10, 3), dtype=np.uint8),
            enhanced_crop=np.zeros((10, 10, 3), dtype=np.uint8),
            ocr_text="1800-328-3286 | care@suraj.in",
            ocr_confidence=0.89,
        ),
    ]

    decls = cv_pipeline_instance.stage8_extract_structured_data(crops)
    assert decls.mrp == "₹263.42"
    assert decls.net_quantity == "100 ml"
    assert decls.mfg_date == "04/2026"
    assert "Suraj Industries" in decls.manufacturer
    assert "1800-328-3286" in decls.consumer_care


# ---------------------------------------------------------------------------
# Stage 9: Rule Compliance Check Tests
# ---------------------------------------------------------------------------

def test_stage9_check_compliance_compliant(cv_pipeline_instance: CVPipeline):
    decls = StructuredDeclarations(
        mrp="₹199",
        net_quantity="500 ml",
        mfg_date="04/2026",
        manufacturer="ABC Foods Pvt Ltd",
        consumer_care="1800-123-456",
        unit_price="₹0.40/ml",
    )
    verdict, facts = cv_pipeline_instance.stage9_check_compliance(decls)
    assert verdict == "COMPLIANT"
    assert all(f["status"] == "PASS" for f in facts)


def test_stage9_check_compliance_violation(cv_pipeline_instance: CVPipeline):
    # Missing MRP and Consumer Care
    decls = StructuredDeclarations(
        mrp=None,
        net_quantity="500 ml",
        mfg_date="04/2026",
        manufacturer="ABC Foods Pvt Ltd",
        consumer_care=None,
    )
    verdict, facts = cv_pipeline_instance.stage9_check_compliance(decls)
    assert verdict == "VIOLATION"
    mrp_fact = next(f for f in facts if f["field"] == "mrp")
    assert mrp_fact["status"] == "FAIL"
    care_fact = next(f for f in facts if f["field"] == "consumer_care")
    assert care_fact["status"] == "FAIL"


# ---------------------------------------------------------------------------
# Stage 10: Visual Overlay Rendering Test
# ---------------------------------------------------------------------------

def test_stage10_render_compliance_overlay(cv_pipeline_instance: CVPipeline, sample_image_bgr: np.ndarray):
    crops = [
        RegionCrop(
            region_id="crop_0",
            class_name="mrp",
            confidence=0.9,
            original_bbox=(30, 320, 280, 350),
            raw_crop=np.zeros((10, 10, 3), dtype=np.uint8),
            enhanced_crop=np.zeros((10, 10, 3), dtype=np.uint8),
        )
    ]
    facts = [{"field": "mrp", "status": "PASS"}]
    overlay = cv_pipeline_instance.stage10_render_compliance_overlay(
        sample_image_bgr, crops, facts, overall_verdict="COMPLIANT"
    )
    assert isinstance(overlay, np.ndarray)
    # Output should include top banner, so height is larger than original
    assert overlay.shape[0] > sample_image_bgr.shape[0]
    assert overlay.shape[1] == sample_image_bgr.shape[1]


# ---------------------------------------------------------------------------
# End-to-End Pipeline Tests on Real/Synthetic Dataset Images
# ---------------------------------------------------------------------------

def test_e2e_pipeline_execution(cv_pipeline_instance: CVPipeline, sample_image_bgr: np.ndarray):
    result = cv_pipeline_instance.run_pipeline(sample_image_bgr, product_category="beverage")
    assert result.success is True
    assert result.stage == "COMPLETED"
    assert len(result.detected_regions) > 0
    assert len(result.crops) > 0
    assert result.visual_overlay_bgr is not None
    assert result.get_overlay_base64() is not None
    assert len(result.execution_notes) >= 8


def test_e2e_dataset_image():
    prod1 = DATASET_IMAGES_DIR / "prod001_compliant.png"
    if not prod1.exists():
        pytest.skip(f"Dataset image {prod1} not found")

    result = run_cv_pipeline(prod1, product_category="beverage")
    assert result.success is True
    assert result.stage == "COMPLETED"
    assert len(result.crops) > 0
    assert result.compliance_verdict in ("COMPLIANT", "VIOLATION", "UNCERTAIN")
