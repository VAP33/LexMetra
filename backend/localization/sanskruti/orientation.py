"""
Per-region text orientation and rectification utilities ported from Sanskruti CV.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Tuple
import cv2
import numpy as np


class Orientation(int, Enum):
    DEG_0 = 0
    DEG_90 = 90
    DEG_180 = 180
    DEG_270 = 270

    @property
    def label(self) -> str:
        return f"{int(self.value)}deg"


def rotate_crop(image: np.ndarray, orientation: Orientation) -> np.ndarray:
    """
    Losslessly rotate a cropped image patch by 0, 90, 180, or 270 degrees clockwise.
    """
    if orientation == Orientation.DEG_0 or orientation == 0:
        return image.copy()
    elif orientation == Orientation.DEG_90 or orientation == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif orientation == Orientation.DEG_180 or orientation == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    elif orientation == Orientation.DEG_270 or orientation == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return image.copy()


def estimate_text_axis(crop_gray: np.ndarray) -> str:
    """
    Estimate if text ink lines are primarily HORIZONTAL or VERTICAL.
    Returns "HORIZONTAL", "VERTICAL", or "AMBIGUOUS".
    """
    if crop_gray is None or crop_gray.size == 0:
        return "AMBIGUOUS"

    h, w = crop_gray.shape[:2]
    if h < 10 or w < 10:
        return "AMBIGUOUS"

    # Edge profile analysis
    grad_x = cv2.Sobel(crop_gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(crop_gray, cv2.CV_32F, 0, 1, ksize=3)

    energy_x = float(np.mean(np.abs(grad_x)))
    energy_y = float(np.mean(np.abs(grad_y)))

    if energy_x + energy_y < 1e-5:
        return "AMBIGUOUS"

    # In horizontal lines of text, vertical gradient across baseline/x-height is typically higher
    ratio = energy_y / (energy_x + 1e-5)
    if ratio > 1.25:
        return "HORIZONTAL"
    elif ratio < 0.8:
        return "VERTICAL"
    return "AMBIGUOUS"
