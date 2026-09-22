"""
Unit tests for backend/localization/service.py and ported Sanskruti components.
Verifies contract preservation, XYWH coordinate spaces, candidate matching,
polygon projection, and graceful UNLOCALIZED / LOCALIZER_UNAVAILABLE degradation.
"""

import numpy as np
import pytest

from localization.models import (
    BoundingBoxCanonical,
    LocalizationStatus,
    LocalizationSurface,
    LocalizedEvidence,
)
from localization.service import LocalizationService, _parse_bbox_to_xywh
from localization.sanskruti.matching import (
    compute_iou,
    score_candidate,
    project_polygon,
    polygon_to_xywh,
)
from localization.sanskruti.paddle_detector import DetectedPolygon


def test_parse_bbox_to_xywh():
    # XYXY conversion
    bbox_xyxy = {"format": "XYXY", "x1": 50, "y1": 100, "x2": 150, "y2": 200}
    res = _parse_bbox_to_xywh(bbox_xyxy, 1000, 1000)
    assert res == (50.0, 100.0, 100.0, 100.0)

    # XYWH direct
    bbox_xywh = {"format": "XYWH", "x": 10, "y": 20, "width": 30, "height": 40}
    res2 = _parse_bbox_to_xywh(bbox_xywh, 1000, 1000)
    assert res2 == (10.0, 20.0, 30.0, 40.0)

    # Normalized coordinates
    bbox_norm = {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
    res3 = _parse_bbox_to_xywh(bbox_norm, 1000, 1000)
    assert res3 == (100.0, 200.0, 300.0, 400.0)


def test_compute_iou_and_scoring():
    box_a = (100.0, 100.0, 50.0, 50.0)
    box_b = (100.0, 100.0, 50.0, 50.0)
    assert compute_iou(box_a, box_b) == 1.0

    box_c = (200.0, 200.0, 50.0, 50.0)
    assert compute_iou(box_a, box_c) == 0.0

    score = score_candidate(box_a, box_b, 1000, 1000, cand_text="MRP 100", qwen_text="MRP Rs 100.00")
    assert score >= 0.90


def test_polygon_to_xywh_and_clipping():
    poly = [[10.0, 20.0], [50.0, 20.0], [50.0, 80.0], [10.0, 80.0]]
    bbox = polygon_to_xywh(poly, 100, 100)
    assert bbox["x"] == 10.0
    assert bbox["y"] == 20.0
    assert bbox["width"] == 40.0
    assert bbox["height"] == 60.0
    assert bbox["format"] == "XYWH"
    assert bbox["space"] == "CANONICAL_PIXEL"


def test_project_polygon_homography():
    poly = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
    # 2x scaling transform
    M = [[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 1.0]]
    projected = project_polygon(poly, M)
    assert projected == [[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0]]


def test_localization_service_unlocalized_when_no_match():
    service = LocalizationService()
    # Mock surface
    surface = LocalizationSurface(
        face_id="face_1",
        image_id="face_1_canonical",
        canonical_image=np.full((300, 300, 3), 255, dtype=np.uint8),
        canonical_width=300,
        canonical_height=300,
        original_width=600,
        original_height=600,
        forward_transform=None,
        inverse_transform=[[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 1.0]],
    )

    # Qwen extracted field at (10, 10, 50, 20)
    extractions = {
        "mrp": {
            "value": 150.0,
            "raw_text": "MRP 150",
            "bbox": {"x": 10, "y": 10, "width": 50, "height": 20},
            "surface_id": "face_1",
        }
    }

    # If localizer finds no polygon candidates, status must be UNLOCALIZED
    results = service.localize_extractions("insp-01", extractions, {"face_1": surface})
    assert len(results) == 1
    loc = results[0]
    assert loc.field == "mrp"
    assert loc.localization_status in (LocalizationStatus.UNLOCALIZED, LocalizationStatus.LOCALIZER_UNAVAILABLE)
    # Coarse box must still be preserved
    assert loc.coarse_bbox_canonical is not None
    assert loc.coarse_bbox_canonical["x"] == 10.0
