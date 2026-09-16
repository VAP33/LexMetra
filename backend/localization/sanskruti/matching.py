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


def normalize_text_tokens(text: str) -> List[str]:
    import re
    if not text:
        return []
    # Replace punctuation with space and split into alphanumeric tokens
    clean = re.sub(r"[^\w\.\,\/]", " ", str(text).lower())
    return [t.strip() for t in clean.split() if t.strip()]


def score_candidate(
    qwen_xywh: Tuple[float, float, float, float],
    cand_xywh: Tuple[float, float, float, float],
    img_w: int,
    img_h: int,
    cand_text: Optional[str] = None,
    qwen_text: Optional[str] = None,
    field_name: Optional[str] = None,
    qwen_value: Optional[str] = None,
) -> float:
    """
    Candidate scoring combining overlap (IoU), center proximity, size compatibility,
    and field-specific semantic token equality (Task 4 & Task 5).
    """
    import re

    iou = compute_iou(qwen_xywh, cand_xywh)
    center_dist = center_distance_normalized(qwen_xywh, cand_xywh, img_w, img_h)
    proximity_score = max(0.0, 1.0 - (center_dist * 2.5))

    # Area ratio compatibility
    area_q = max(1.0, qwen_xywh[2] * qwen_xywh[3])
    area_c = max(1.0, cand_xywh[2] * cand_xywh[3])
    area_ratio = min(area_q, area_c) / max(area_q, area_c)

    # Base spatial score
    score = (0.40 * iou) + (0.40 * proximity_score) + (0.20 * area_ratio)

    # Token & Numeric Matching Requirements (Task 4)
    target_str = (str(qwen_value or "") + " " + str(qwen_text or "")).strip().lower()
    cand_str = str(cand_text or "").strip().lower()

    if cand_str and target_str:
        cand_tokens = set(normalize_text_tokens(cand_str))
        target_tokens = set(normalize_text_tokens(target_str))

        # Check token intersection
        common_tokens = cand_tokens.intersection(target_tokens)
        if common_tokens:
            token_overlap = len(common_tokens) / max(1, min(len(cand_tokens), len(target_tokens)))
            score = min(1.0, score + 0.25 * token_overlap)

        # Field-specific numeric token equality
        is_numeric_field = any(k in (field_name or "").lower() for k in ("mrp", "price", "net_quantity", "quantity", "unit_sale_price", "usp", "mfg_date", "expiry", "use_before", "batch"))
        if is_numeric_field:
            cand_nums = re.findall(r"\d+[\.,]?\d*", cand_str)
            target_nums = re.findall(r"\d+[\.,]?\d*", target_str)
            if target_nums:
                cand_clean_nums = {n.replace(",", "") for n in cand_nums}
                target_clean_nums = {n.replace(",", "") for n in target_nums}
                if cand_clean_nums.intersection(target_clean_nums):
                    score = min(1.0, score + 0.30)
                else:
                    # Penalize numeric fields that have numbers that disagree
                    if cand_nums:
                        score *= 0.70

    return score


def group_adjacent_matched_polygons(
    matched_polys: List[DetectedPolygon],
    img_w: int,
    img_h: int,
    max_area_fraction: float = 0.35,
) -> Tuple[List[List[float]], Tuple[float, float, float, float]]:
    """
    Groups adjacent line polygons for multi-line fields (e.g. manufacturer address)
    conforming strictly to Task 4 & Task 5 Multi-line Grouping Rules:
    - Vertical gap within 2.0x median line height
    - Resulting union does not exceed max_area_fraction of the image
    """
    if not matched_polys:
        return [], (0.0, 0.0, 0.0, 0.0)

    if len(matched_polys) == 1:
        p = matched_polys[0]
        return p.polygon, (float(p.bbox_xywh[0]), float(p.bbox_xywh[1]), float(p.bbox_xywh[2]), float(p.bbox_xywh[3]))

    # Sort in reading order: top to bottom, then left to right
    sorted_polys = sorted(matched_polys, key=lambda p: (p.bbox_xywh[1], p.bbox_xywh[0]))
    heights = [p.bbox_xywh[3] for p in sorted_polys]
    median_h = float(np.median(heights)) if heights else 20.0
    max_gap = max(15.0, median_h * 2.2)

    grouped_pts: List[List[float]] = []
    prev_box = None

    for p in sorted_polys:
        bx, by, bw, bh = p.bbox_xywh
        if prev_box is not None:
            prev_y_bottom = prev_box[1] + prev_box[3]
            gap = by - prev_y_bottom
            if gap > max_gap:
                # Distant line: do NOT absorb
                continue
        grouped_pts.extend(p.polygon)
        prev_box = (bx, by, bw, bh)

    if not grouped_pts:
        p = sorted_polys[0]
        return p.polygon, (float(p.bbox_xywh[0]), float(p.bbox_xywh[1]), float(p.bbox_xywh[2]), float(p.bbox_xywh[3]))

    xs = [pt[0] for pt in grouped_pts]
    ys = [pt[1] for pt in grouped_pts]
    x_min = max(0.0, min(xs))
    y_min = max(0.0, min(ys))
    x_max = min(float(img_w), max(xs))
    y_max = min(float(img_h), max(ys))
    bw = max(0.0, x_max - x_min)
    bh = max(0.0, y_max - y_min)

    # Geometric safeguard: maximum region area fraction
    total_area = float(img_w * img_h)
    region_area = float(bw * bh)
    if total_area > 0 and (region_area / total_area) > max_area_fraction:
        # Fall back to single top polygon if grouped area is unreasonably large
        p = sorted_polys[0]
        return p.polygon, (float(p.bbox_xywh[0]), float(p.bbox_xywh[1]), float(p.bbox_xywh[2]), float(p.bbox_xywh[3]))

    union_poly = [
        [round(x_min, 2), round(y_min, 2)],
        [round(x_max, 2), round(y_min, 2)],
        [round(x_max, 2), round(y_max, 2)],
        [round(x_min, 2), round(y_max, 2)],
    ]
    return union_poly, (round(x_min, 2), round(y_min, 2), round(bw, 2), round(bh, 2))


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
