"""
Objective image-quality assessment for one captured surface.

Scope and honesty:
- These are classical CV heuristics (Laplacian sharpness, histogram exposure,
  highlight-clipping glare), not a trained perceptual-quality model.
- All *_score fields follow a "higher is better" polarity:
    blur_score      -> higher = sharper
    exposure_score  -> higher = better exposed (not too dark/bright)
    glare_score     -> higher = less glare / fewer blown highlights
- This module never makes a legal decision. It only helps the capture
  workflow tell an inspector "retake this photo" versus "usable evidence".
"""

from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np

from schema import EvidenceStatus, ImageQuality

MIN_USABLE_DIMENSION_PX = 300

BLUR_LOW_THRESHOLD = 0.15
EXPOSURE_LOW_THRESHOLD = 0.30
GLARE_LOW_THRESHOLD = 0.40


def _blur_score(gray: np.ndarray) -> float:
    """Laplacian-variance sharpness estimate, normalized to roughly [0, 1]."""
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    # 500 is an empirically reasonable "clearly sharp" ceiling for
    # phone-camera package photos at typical inspection distance; this is a
    # heuristic scale, not a calibrated metric.
    return float(max(0.0, min(1.0, variance / 500.0)))


def _exposure_score(gray: np.ndarray) -> float:
    """1.0 when mean brightness is near mid-tone; falls off toward 0/255."""
    mean_val = float(gray.mean())
    distance_from_midtone = abs(mean_val - 128.0)
    return float(max(0.0, min(1.0, 1.0 - (distance_from_midtone / 128.0))))


def _glare_score(gray: np.ndarray) -> float:
    """1.0 when there are no blown-out highlights; drops as glare grows."""
    overexposed_fraction = float(np.mean(gray >= 250))
    # A small fraction of bright pixels is normal (reflective packaging);
    # penalize more aggressively past that.
    return float(max(0.0, min(1.0, 1.0 - overexposed_fraction * 6.0)))


def assess_image_quality(
    img_bgr: np.ndarray,
    ocr_line_count: int = 0,
) -> ImageQuality:
    """
    Compute ImageQuality for one captured surface image.

    `ocr_line_count` (if known) is used only to set `ocr_quality_score` and
    to add a note when an otherwise-sharp image produced no readable text —
    this is informational for the capture UI, not a legal finding.
    """
    notes: List[str] = []
    height, width = img_bgr.shape[:2]

    if width < MIN_USABLE_DIMENSION_PX or height < MIN_USABLE_DIMENSION_PX:
        return ImageQuality(
            status=EvidenceStatus.INVALID,
            notes=["Image resolution is too low for reliable inspection. Move closer or use a higher-resolution capture."],
        )

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    blur = _blur_score(gray)
    exposure = _exposure_score(gray)
    glare = _glare_score(gray)
    ocr_quality = float(max(0.0, min(1.0, ocr_line_count / 8.0))) if ocr_line_count else 0.0

    if blur < BLUR_LOW_THRESHOLD:
        notes.append("Image appears blurry. Hold steady and refocus, then retake.")
    if exposure < EXPOSURE_LOW_THRESHOLD:
        notes.append("Image is poorly exposed. Improve lighting and avoid backlight.")
    if glare < GLARE_LOW_THRESHOLD:
        notes.append("Strong glare/reflection detected. Tilt the package or change the angle.")
    if ocr_line_count == 0 and blur >= BLUR_LOW_THRESHOLD:
        notes.append("No readable text was found on this surface. Confirm the label is in frame.")

    if blur < BLUR_LOW_THRESHOLD or exposure < EXPOSURE_LOW_THRESHOLD or glare < GLARE_LOW_THRESHOLD:
        status = EvidenceStatus.LOW_QUALITY
    elif ocr_line_count == 0:
        status = EvidenceStatus.PARTIAL
    else:
        status = EvidenceStatus.USABLE

    return ImageQuality(
        status=status,
        blur_score=round(blur, 3),
        glare_score=round(glare, 3),
        exposure_score=round(exposure, 3),
        ocr_quality_score=round(ocr_quality, 3),
        notes=notes,
    )


def estimate_pdp_bbox(
    ocr_boxes: List[Tuple[int, int, int, int]],
    image_width: int,
    image_height: int,
) -> Tuple[float, float, float, float] | None:
    """
    Rough Principal Display Panel estimate: the bounding rectangle around all
    OCR text detections, padded by a small margin.

    This is a heuristic ESTIMATE for capture guidance / display only. It is
    never used as a VERIFIED measurement and never feeds the font-height
    legal check directly — that check requires an explicit, separately
    calibrated `pdp_area_cm2` (see unit_price.py / rule_engine.py).
    """
    if not ocr_boxes:
        return None

    xs1 = [b[0] for b in ocr_boxes]
    ys1 = [b[1] for b in ocr_boxes]
    xs2 = [b[0] + b[2] for b in ocr_boxes]
    ys2 = [b[1] + b[3] for b in ocr_boxes]

    x1, y1, x2, y2 = min(xs1), min(ys1), max(xs2), max(ys2)

    pad_x = max(4, int(0.04 * image_width))
    pad_y = max(4, int(0.04 * image_height))

    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(image_width, x2 + pad_x)
    y2 = min(image_height, y2 + pad_y)

    width = max(1.0, float(x2 - x1))
    height = max(1.0, float(y2 - y1))
    return (float(x1), float(y1), width, height)
