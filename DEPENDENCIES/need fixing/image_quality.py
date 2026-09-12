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

from typing import List, Optional, Tuple

import cv2
import numpy as np

import preprocess
from schema import EvidenceStatus, ImageQuality

MIN_USABLE_DIMENSION_PX = 300

# A cropped declaration region is legitimately much smaller than a whole
# surface photo, so region assessment uses its own (lower) usability floor.
MIN_USABLE_REGION_DIMENSION_PX = 24

BLUR_LOW_THRESHOLD = 0.15
EXPOSURE_LOW_THRESHOLD = 0.30
GLARE_LOW_THRESHOLD = 0.40
PERSPECTIVE_LOW_THRESHOLD = 0.35


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


def estimate_perspective_score(img_bgr: np.ndarray) -> Optional[float]:
    """
    Estimate how front-facing the dominant flat surface in the frame is.

    Returns a score in [0, 1] where 1.0 means "the dominant quadrilateral looks
    like an undistorted rectangle viewed head-on", or None when no sufficiently
    convincing quadrilateral is found.

    Returning None is meaningful and must be preserved: a cylindrical jar, a
    spherical wrapper, or a crumpled pouch has no planar quadrilateral, so
    "perspective" is genuinely unmeasurable rather than bad. Downstream code
    must treat None as UNKNOWN and must not substitute a default number — a
    fabricated perspective score could otherwise flow into geometry decisions
    and, indirectly, into a legal measurement claim.

    Method: find the largest convex 4-point contour approximation covering a
    plausible share of the frame, then score it on two independent
    rectangularity cues — opposite-side length agreement and corner angles
    close to 90 degrees.
    """
    if img_bgr is None or img_bgr.size == 0:
        return None

    gray = (
        img_bgr
        if img_bgr.ndim == 2
        else cv2.cvtColor(img_bgr[:, :, :3], cv2.COLOR_BGR2GRAY)
    )
    height, width = gray.shape[:2]
    frame_area = float(height * width)
    if frame_area <= 0:
        return None

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, kernel)

    contours, _hierarchy = cv2.findContours(
        edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return None

    best_quad: Optional[np.ndarray] = None
    best_area = 0.0
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
        area = float(cv2.contourArea(contour))
        if area < frame_area * 0.06:
            break
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        if area > best_area:
            best_area = area
            best_quad = approx

    if best_quad is None:
        return None

    corners = preprocess.order_corners(best_quad.reshape(4, 2).astype(np.float32))
    tl, tr, br, bl = corners

    top = float(np.linalg.norm(tr - tl))
    bottom = float(np.linalg.norm(br - bl))
    left = float(np.linalg.norm(bl - tl))
    right = float(np.linalg.norm(br - tr))
    if min(top, bottom, left, right) < 1e-3:
        return None

    side_agreement = min(top, bottom) / max(top, bottom)
    side_agreement *= min(left, right) / max(left, right)

    def _corner_cosine(a: np.ndarray, vertex: np.ndarray, b: np.ndarray) -> float:
        v1 = a - vertex
        v2 = b - vertex
        n1 = float(np.linalg.norm(v1))
        n2 = float(np.linalg.norm(v2))
        if n1 < 1e-6 or n2 < 1e-6:
            return 1.0
        return abs(float(np.dot(v1, v2)) / (n1 * n2))

    cosines = [
        _corner_cosine(bl, tl, tr),
        _corner_cosine(tl, tr, br),
        _corner_cosine(tr, br, bl),
        _corner_cosine(br, bl, tl),
    ]
    # cos == 0 at a perfect right angle; penalise deviation.
    squareness = float(max(0.0, 1.0 - (sum(cosines) / len(cosines)) * 2.0))

    score = float(max(0.0, min(1.0, 0.5 * side_agreement + 0.5 * squareness)))
    return round(score, 3)


def assess_image_quality(
    img_bgr: np.ndarray,
    ocr_line_count: int = 0,
    *,
    include_perspective: bool = True,
) -> ImageQuality:
    """
    Compute ImageQuality for one captured surface image.

    `ocr_line_count` (if known) is used only to set `ocr_quality_score` and
    to add a note when an otherwise-sharp image produced no readable text —
    this is informational for the capture UI, not a legal finding.

    `perspective_score` is populated when a dominant planar quadrilateral can
    be found, and left as None otherwise (curved, spherical, or irregular
    packaging). A low perspective score produces capture guidance only; it
    never contributes to a compliance determination.
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
    perspective = estimate_perspective_score(img_bgr) if include_perspective else None

    if blur < BLUR_LOW_THRESHOLD:
        notes.append("Image appears blurry. Hold steady and refocus, then retake.")
    if exposure < EXPOSURE_LOW_THRESHOLD:
        notes.append("Image is poorly exposed. Improve lighting and avoid backlight.")
    if glare < GLARE_LOW_THRESHOLD:
        notes.append("Strong glare/reflection detected. Tilt the package or change the angle.")
    if perspective is not None and perspective < PERSPECTIVE_LOW_THRESHOLD:
        notes.append(
            "The label appears strongly tilted. Hold the camera parallel to the "
            "label surface and retake."
        )
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
        perspective_score=perspective,
        ocr_quality_score=round(ocr_quality, 3),
        notes=notes,
    )


def assess_region_quality(
    img_bgr: np.ndarray,
    bbox: Tuple[int, int, int, int],
    *,
    region_label: str = "this region",
    ocr_line_count: int = 0,
) -> ImageQuality:
    """
    Assess quality for one cropped region (a declaration area, label, or panel).

    Region-level assessment matters because a photograph can be perfectly good
    overall while the MRP block specifically sits under a specular highlight.
    Whole-image scores hide that; this surfaces it, and the accompanying notes
    are region-specific recapture instructions.

    Delegates measurement to `preprocess.measure_quality()` so that the signals
    driving preprocessing variant selection and the signals shown to the
    inspector are the same numbers, and converts them into the existing
    `ImageQuality` shape.

    Legal-safety note: a LOW_QUALITY or INVALID region means the EVIDENCE is
    inadequate. It never means the declaration is absent, and callers must map
    it to UNCERTAIN / NEEDS_RECAPTURE, never to FAIL.
    """
    if img_bgr is None or img_bgr.size == 0:
        raise ValueError("assess_region_quality() received an empty image.")

    x, y, w, h = (int(v) for v in bbox)
    height, width = img_bgr.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(width, x + w), min(height, y + h)

    if x1 - x0 < MIN_USABLE_REGION_DIMENSION_PX or y1 - y0 < MIN_USABLE_REGION_DIMENSION_PX:
        return ImageQuality(
            status=EvidenceStatus.INVALID,
            notes=[
                f"{region_label} is too small in this image to read reliably "
                f"({max(0, x1 - x0)}x{max(0, y1 - y0)} px). Capture a close-up of this area."
            ],
        )

    crop = img_bgr[y0:y1, x0:x1]
    signals = preprocess.measure_quality(crop)

    notes = preprocess.recapture_guidance(signals, field_label=region_label)
    ocr_quality = float(max(0.0, min(1.0, ocr_line_count / 4.0))) if ocr_line_count else 0.0

    if (
        signals.has_blur_problem
        or signals.has_glare_problem
        or signals.has_exposure_problem
        or signals.is_low_resolution
    ):
        status = EvidenceStatus.LOW_QUALITY
    elif ocr_line_count == 0:
        status = EvidenceStatus.PARTIAL
        notes.append(
            f"No readable text was extracted from {region_label}. "
            "This is an evidence gap, not a finding of non-compliance."
        )
    else:
        status = EvidenceStatus.USABLE

    return ImageQuality(
        status=status,
        blur_score=round(signals.sharpness, 3),
        glare_score=round(signals.glare, 3),
        exposure_score=round(signals.exposure, 3),
        perspective_score=None,
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
