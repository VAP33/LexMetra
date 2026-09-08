"""
Package boundary estimation - deliberately DISTINCT from PDP estimation
(image_quality.estimate_pdp_bbox).

Package boundary = "where is the physical object in this frame" (classical
contour/edge based - the whole item, background excluded).
PDP           = "where is the text-bearing declaration panel" (already
                 implemented in image_quality.py, driven by OCR line bboxes).

Conflating these was flagged explicitly as a risk (master spec: "package
boundary != PDP"). This module produces the FIRST one only. It is classical
CV (edge density + largest-contour heuristic), not a trained segmentation
model - a pragmatic MVP boundary, not a precise mask.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


@dataclass
class PackageBoundary:
    bbox: Tuple[int, int, int, int]  # x, y, w, h in image pixels
    confidence: float                 # 0..1, heuristic - see docstring
    frame_fill_ratio: float           # bbox area / image area, used for framing guidance


def estimate_package_boundary(img_bgr: np.ndarray) -> Optional[PackageBoundary]:
    """
    Classical-CV package boundary: Canny edges -> dilate -> largest external
    contour. Deliberately simple; returns None (not a wrong guess) when no
    contour large/confident enough is found - callers must treat that as
    "could not localize the package", not "no package present".
    """
    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    edges = cv2.dilate(edges, np.ones((9, 9), np.uint8), iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    image_area = h * w
    best = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(best)

    # Too small: likely noise, not a package filling a meaningful part of frame.
    if area < 0.03 * image_area:
        return None

    x, y, bw, bh = cv2.boundingRect(best)
    fill_ratio = (bw * bh) / image_area

    # Confidence heuristic: larger, more centrally-located, less edge-touching
    # contours are more likely to be a genuine held-up package rather than
    # background shelving/clutter caught by Canny.
    touches_border = x <= 2 or y <= 2 or (x + bw) >= w - 2 or (y + bh) >= h - 2
    confidence = min(1.0, area / image_area * 1.8)
    if touches_border:
        confidence *= 0.7

    return PackageBoundary(
        bbox=(x, y, bw, bh),
        confidence=round(min(1.0, confidence), 3),
        frame_fill_ratio=round(fill_ratio, 3),
    )


def framing_guidance(boundary: Optional[PackageBoundary], img_shape: Tuple[int, int]) -> Optional[str]:
    """Pure text guidance from framing geometry alone - no OCR involved."""
    if boundary is None:
        return "No package detected in frame. Center the package and hold steady."
    if boundary.frame_fill_ratio < 0.12:
        return "Package is too small in frame. Move closer."
    if boundary.frame_fill_ratio > 0.92:
        return "Package fills the whole frame. Move back slightly to capture edges."
    h, w = img_shape[:2]
    x, y, bw, bh = boundary.bbox
    cx, cy = x + bw / 2, y + bh / 2
    if abs(cx - w / 2) > 0.25 * w or abs(cy - h / 2) > 0.25 * h:
        return "Package is off-center. Center it in the frame."
    return None
