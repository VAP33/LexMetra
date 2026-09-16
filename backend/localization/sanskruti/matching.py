"""
Polygon and bounding-box candidate matching, geometric projection,
and verification scoring ported from Sanskruti CV.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

from localization.models import (
    BoundingBoxCanonical,
    LocalizationStatus,
    LocalizedEvidence,
)
from localization.sanskruti.paddle_detector import DetectedPolygon


def compute_iou(box_a: Tuple[float, float, float, float], box_b: Tuple[float, float, float, float]) -> float:
    """
    Compute Intersection-over-Union between two XYWH boxes.
    """
    xa, ya, wa, ha = box_a
    xb, yb, wb, hb = box_b

    x1 = max(xa, xb)
    y1 = max(ya, yb)
    x2 = min(xa + wa, xb + wb)
    y2 = min(ya + ha, yb + hb)

    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h

    area_a = wa * ha
    area_b = wb * hb
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def center_distance_normalized(
    box_a: Tuple[float, float, float, float],
    box_b: Tuple[float, float, float, float],
    img_w: int,
    img_h: int,
) -> float:
    """
    Normalized Euclidean distance between centers of box_a and box_b.
    Returns 0.0 (identical centers) to 1.0 (opposite corners).
    """
    ca_x = box_a[0] + box_a[2] / 2.0
    ca_y = box_a[1] + box_a[3] / 2.0
    cb_x = box_b[0] + box_b[2] / 2.0
    cb_y = box_b[1] + box_b[3] / 2.0

    diag = math.hypot(img_w, img_h)
    if diag <= 0:
        return 1.0
    dist = math.hypot(ca_x - cb_x, ca_y - cb_y)
    return min(1.0, dist / diag)


def score_candidate(
    qwen_xywh: Tuple[float, float, float, float],
    cand_xywh: Tuple[float, float, float, float],
    img_w: int,
    img_h: int,
    cand_text: Optional[str] = None,
    qwen_text: Optional[str] = None,
) -> float:
    """
    Candidate scoring combining overlap (IoU), center proximity, and size compatibility.
    """
    iou = compute_iou(qwen_xywh, cand_xywh)
    center_dist = center_distance_normalized(qwen_xywh, cand_xywh, img_w, img_h)
    proximity_score = max(0.0, 1.0 - (center_dist * 2.5))

    # Area ratio compatibility
    area_q = max(1.0, qwen_xywh[2] * qwen_xywh[3])
    area_c = max(1.0, cand_xywh[2] * cand_xywh[3])
    area_ratio = min(area_q, area_c) / max(area_q, area_c)

    score = (0.50 * iou) + (0.35 * proximity_score) + (0.15 * area_ratio)

    # Optional tie-breaker: mild boost if recognized text matches partial qwen tokens
    if cand_text and qwen_text:
        cand_lower = cand_text.lower().replace(" ", "")
        qwen_lower = qwen_text.lower().replace(" ", "")
        if cand_lower and (cand_lower in qwen_lower or qwen_lower in cand_lower):
            score = min(1.0, score + 0.10)

    return score


def project_polygon(polygon: List[List[float]], transform_matrix: Any) -> List[List[float]]:
    """
    Project 2D polygon points using 3x3 homography / affine transform matrix.
    """
    if not polygon or transform_matrix is None:
        return polygon

    try:
        M = np.array(transform_matrix, dtype=np.float32)
        if M.shape not in ((3, 3), (2, 3)):
            return polygon

        pts = np.array(polygon, dtype=np.float32).reshape(-1, 1, 2)
        if M.shape == (3, 3):
            projected = cv2.perspectiveTransform(pts, M)
        else:
            projected = cv2.transform(pts, M)

        return [[round(float(p[0][0]), 2), round(float(p[0][1]), 2)] for p in projected]
    except Exception:
        return polygon


def polygon_to_xywh(polygon: List[List[float]], img_w: int, img_h: int) -> Dict[str, Any]:
    """
    Compute tight enclosing bounding box from polygon and clip to image boundaries.
    """
    if not polygon:
        return {
            "space": "CANONICAL_PIXEL",
            "format": "XYWH",
            "x": 0.0,
            "y": 0.0,
            "width": 0.0,
            "height": 0.0,
            "image_width": img_w,
            "image_height": img_h,
        }

    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]

    x_min = max(0.0, min(xs))
    y_min = max(0.0, min(ys))
    x_max = min(float(img_w), max(xs))
    y_max = min(float(img_h), max(ys))

    bw = max(0.0, x_max - x_min)
    bh = max(0.0, y_max - y_min)

    return {
        "space": "CANONICAL_PIXEL",
        "format": "XYWH",
        "x": round(x_min, 2),
        "y": round(y_min, 2),
        "width": round(bw, 2),
        "height": round(bh, 2),
        "image_width": img_w,
        "image_height": img_h,
    }
