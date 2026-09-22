"""
Region proposal module ported from PaddleOCR CV.
Extracts candidate text/declaration contours and bounding envelopes on a surface image.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple
import cv2
import numpy as np


@dataclass
class RegionProposal:
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    confidence: float
    polygon: List[List[float]]


def propose_text_regions(image_bgr: np.ndarray, max_regions: int = 40) -> List[RegionProposal]:
    """
    Classical MSER / morphological gradient region proposal to find text-like
    clusters and polygons on a surface when deep detector is unavailable or for ROI guidance.
    """
    if image_bgr is None or image_bgr.size == 0:
        return []

    h, w = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # Morphological gradient to highlight high-frequency text boundaries
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)
    _, thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Close horizontally to connect characters in words
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
    connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, close_kernel)

    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    proposals: List[RegionProposal] = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 50 or area > (w * h * 0.8):
            continue

        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw < 10 or bh < 6:
            continue

        # Approximate polygon envelope
        epsilon = 0.02 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        if len(approx) >= 4:
            poly = [[float(pt[0][0]), float(pt[0][1])] for pt in approx]
        else:
            poly = [
                [float(x), float(y)],
                [float(x + bw), float(y)],
                [float(x + bw), float(y + bh)],
                [float(x), float(y + bh)],
            ]

        aspect = float(bw) / float(bh)
        conf = 0.75 if 1.5 <= aspect <= 15.0 else 0.5

        proposals.append(RegionProposal(
            bbox=(x, y, bw, bh),
            confidence=conf,
            polygon=poly,
        ))

    proposals.sort(key=lambda p: (p.bbox[1], p.bbox[0]))
    return proposals[:max_regions]
