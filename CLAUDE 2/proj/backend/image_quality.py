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

from typing import Dict, List, Optional, Tuple

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


def _crop(img_bgr: np.ndarray, bbox_xywh: Tuple[float, float, float, float]) -> np.ndarray | None:
    """Safely crop img_bgr to an integer pixel bbox, clamped to image bounds."""
    h, w = img_bgr.shape[:2]
    x, y, bw, bh = bbox_xywh
    x1 = max(0, int(x))
    y1 = max(0, int(y))
    x2 = min(w, int(x + bw))
    y2 = min(h, int(y + bh))
    if x2 <= x1 or y2 <= y1:
        return None
    return img_bgr[y1:y2, x1:x2]


def assess_region_quality(
    img_bgr: np.ndarray,
    bbox_xywh: Tuple[float, float, float, float],
    field_name: Optional[str] = None,
) -> ImageQuality:
    """
    Region-aware quality assessment: the SAME metrics as assess_image_quality,
    computed only over one declaration's bounding box.

    This is the direct fix for the master-spec failure mode: "an image can be
    globally acceptable but have glare directly over MRP". A whole-image
    blur/glare/exposure score cannot see that, because a small bad patch is
    averaged away by a mostly-fine photo. This function is deliberately a thin
    wrapper around the same three heuristics, not a new model, so its scores
    remain directly comparable to the whole-image ones.

    Returns EvidenceStatus.INVALID (with a note, not an exception) if the
    region cannot be cropped (e.g. bbox fell outside the image after a
    coordinate mismatch) - callers must treat that as "could not assess",
    never as "field failed inspection".
    """
    crop = _crop(img_bgr, bbox_xywh)
    if crop is None or crop.shape[0] < 8 or crop.shape[1] < 8:
        return ImageQuality(
            status=EvidenceStatus.INVALID,
            notes=["Region too small or out of frame to assess quality."],
        )

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    blur = _blur_score(gray)
    exposure = _exposure_score(gray)
    glare = _glare_score(gray)

    label = f" over {field_name}" if field_name else ""
    notes: List[str] = []
    if glare < GLARE_LOW_THRESHOLD:
        notes.append(f"Glare/reflection detected{label}. Tilt the package or camera slightly and capture again.")
    if blur < BLUR_LOW_THRESHOLD:
        notes.append(f"Text{label} is blurry. Hold steady, refocus, and recapture this region.")
    if exposure < EXPOSURE_LOW_THRESHOLD:
        notes.append(f"Lighting is poor{label}. Improve lighting and avoid backlight, then recapture.")

    if blur < BLUR_LOW_THRESHOLD or exposure < EXPOSURE_LOW_THRESHOLD or glare < GLARE_LOW_THRESHOLD:
        status = EvidenceStatus.LOW_QUALITY
    else:
        status = EvidenceStatus.USABLE

    return ImageQuality(
        status=status,
        blur_score=round(blur, 3),
        glare_score=round(glare, 3),
        exposure_score=round(exposure, 3),
        notes=notes,
    )


def assess_field_quality_map(
    img_bgr: np.ndarray,
    field_bboxes: Dict[str, Tuple[float, float, float, float]],
) -> Dict[str, ImageQuality]:
    """
    Run assess_region_quality for every field whose bbox is known in this
    image. A field missing from field_bboxes simply means this image made no
    claim about that field's location - callers must not read that as a
    quality failure.
    """
    return {
        field: assess_region_quality(img_bgr, bbox, field_name=field)
        for field, bbox in field_bboxes.items()
    }


def build_recapture_guidance(
    global_quality: ImageQuality,
    field_quality_map: Optional[Dict[str, ImageQuality]] = None,
    missing_fields: Optional[List[str]] = None,
    field_capture_hints: Optional[Dict[str, str]] = None,
) -> List[str]:
    """
    Turn quality signals into the specific, actionable guidance the master
    spec asks for ("glare over MRP, tilt and recapture") instead of a generic
    "image quality poor". Field-region notes are surfaced first because they
    are the most actionable ("this field is bad" beats "this photo is bad"),
    then whole-image notes, then coverage/missing-field hints.

    This function only assembles text; it does not decide PASS/FAIL/UNCERTAIN.
    """
    guidance: List[str] = []
    seen: set[str] = set()

    def _add(msg: str) -> None:
        if msg and msg not in seen:
            seen.add(msg)
            guidance.append(msg)

    for field, q in (field_quality_map or {}).items():
        for note in q.notes:
            _add(note)

    for note in global_quality.notes:
        _add(note)

    for field in (missing_fields or []):
        hint = (field_capture_hints or {}).get(field)
        _add(hint or f"Capture a clearer view of: {field}.")

    if not guidance:
        _add("Capture quality looks sufficient for this surface.")

    return guidance


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
