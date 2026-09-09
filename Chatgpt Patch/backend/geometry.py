"""
Package geometry / PDP detection / perspective rectification / coordinate
mapping / live-capture readiness.

Scope and honesty (mirrors image_quality.py's disclosure style):
- This is classical computer vision (contours, corner detection, homography),
  not a trained detector. It is a reasonable SIH-prototype baseline, not a
  certified measurement instrument.
- This module NEVER decides legal compliance. It produces evidence
  (PackageGeometry / PDPGeometry / RectificationResult / GeometryReadinessResult)
  for calibration.py and, eventually, the rule engine to consume.
- "Package boundary" and "Principal Display Panel" are kept as distinct
  concepts throughout: a package boundary is whatever contour looks like the
  product; a PDP is the specific panel that carries mandatory declarations,
  which may be smaller than, differently oriented from, or only partially
  overlapping the package boundary.
- Every detector returns a confidence. Nothing here pretends detection is
  exact, and low image quality (see image_quality.py) always caps confidence
  rather than being ignored.

Integration point for Claude 2 (OCR/vision pipeline):
- detect_pdp_geometry() accepts optional OCR text boxes as a text-density
  hint. It does not run OCR itself and does not duplicate
  ocr_extraction.py/image_quality.estimate_pdp_bbox(); it composes with them.

Integration point for Claude 3 (integrator):
- All public functions take/return schema.py models (BBox, PolygonPoint,
  PackageGeometry, PDPGeometry, RectificationResult, GeometryReadinessResult)
  plus a plain numpy BGR image where an image is required. Nothing here
  touches main.py, rule_engine.py or the database.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from schema import (
    BBox,
    EvidenceStatus,
    GeometryReadiness,
    GeometryReadinessResult,
    GeometryType,
    ImageQuality,
    PackageGeometry,
    PackageShapeHint,
    PDPGeometry,
    PDPObservationStatus,
    PolygonPoint,
    PositionCoordinateSystem,
    RectificationResult,
    SurfaceType,
)

# ---------------------------------------------------------------------------
# Tunables (heuristic, documented rather than hidden)
# ---------------------------------------------------------------------------

MIN_CONTOUR_AREA_FRACTION = 0.04     # ignore contours smaller than 4% of frame
RECTANGULAR_APPROX_EPSILON = 0.02    # cv2.approxPolyDP epsilon, as a fraction of perimeter
QUAD_ANGLE_TOLERANCE_DEG = 25.0      # how far from 90 deg a quad corner may be and still count "rectangular"
CYLINDRICAL_ELLIPSE_FIT_MAX_ERROR = 0.12  # normalized residual for "looks like a rounded/elliptical silhouette"
RECOMMENDED_OVERLAP_MIN = 0.20
RECOMMENDED_OVERLAP_MAX = 0.30
PDP_TOO_OBLIQUE_MAX_ANGLE_RATIO = 3.0  # side-length ratio beyond which a quad is "too oblique" to rectify well


# ---------------------------------------------------------------------------
# Small geometry helpers
# ---------------------------------------------------------------------------

def _polygon_to_np(polygon: Sequence[PolygonPoint]) -> np.ndarray:
    return np.array([[p.x, p.y] for p in polygon], dtype=np.float32)


def _np_to_polygon(points: np.ndarray) -> List[PolygonPoint]:
    return [PolygonPoint(x=float(p[0]), y=float(p[1])) for p in points.reshape(-1, 2)]


def _order_quad_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    pts = pts.reshape(4, 2)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)
    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = pts[np.argmin(s)]       # top-left: smallest x+y
    ordered[2] = pts[np.argmax(s)]       # bottom-right: largest x+y
    ordered[1] = pts[np.argmin(diff)]    # top-right: smallest y-x
    ordered[3] = pts[np.argmax(diff)]    # bottom-left: largest y-x
    return ordered


def _quad_interior_angles_deg(quad: np.ndarray) -> List[float]:
    angles = []
    n = len(quad)
    for i in range(n):
        p_prev = quad[(i - 1) % n]
        p_curr = quad[i]
        p_next = quad[(i + 1) % n]
        v1 = p_prev - p_curr
        v2 = p_next - p_curr
        denom = (np.linalg.norm(v1) * np.linalg.norm(v2)) or 1e-6
        cos_angle = float(np.clip(np.dot(v1, v2) / denom, -1.0, 1.0))
        angles.append(math.degrees(math.acos(cos_angle)))
    return angles


def _is_quad_rectangular(quad: np.ndarray, tolerance_deg: float = QUAD_ANGLE_TOLERANCE_DEG) -> bool:
    angles = _quad_interior_angles_deg(quad)
    return all(abs(a - 90.0) <= tolerance_deg for a in angles)


MAX_CONTOUR_AREA_FRACTION = 0.97  # a contour covering ~the whole frame is almost always background noise, not a package
LETTERBOX_STD_THRESHOLD = 8.0     # a row/column this uniform is a candidate letterbox bar
LETTERBOX_DARK_MEAN_MAX = 15.0
LETTERBOX_LIGHT_MEAN_MIN = 245.0
CORNER_PATCH_FRACTION = 0.06      # corner sample size, as a fraction of min(width, height)


def strip_letterbox_bars(gray: np.ndarray) -> Tuple[int, int, int, int]:
    """
    Detect solid black/white letterbox bars (common in phone screenshots and
    non-matching-aspect-ratio captures) and return the content region as
    (x0, y0, x1, y1) in the ORIGINAL image's coordinates.

    A row/column is treated as "bar" only while it is both very uniform
    (std below LETTERBOX_STD_THRESHOLD) AND near-black or near-white; a
    plain-but-mid-toned photography background (e.g. a light grey wall) will
    not trigger this, since its mean sits well away from the 0/255 extremes.
    """
    height, width = gray.shape[:2]

    def _is_bar(line: np.ndarray) -> bool:
        mean = float(line.mean())
        std = float(line.std())
        return std < LETTERBOX_STD_THRESHOLD and (mean < LETTERBOX_DARK_MEAN_MAX or mean > LETTERBOX_LIGHT_MEAN_MIN)

    top = 0
    while top < height // 2 and _is_bar(gray[top, :]):
        top += 1
    bottom = height
    while bottom > height // 2 and _is_bar(gray[bottom - 1, :]):
        bottom -= 1
    left = 0
    while left < width // 2 and _is_bar(gray[:, left]):
        left += 1
    right = width
    while right > width // 2 and _is_bar(gray[:, right - 1]):
        right -= 1

    # Guard against pathological all-uniform images collapsing the region.
    if bottom - top < 10 or right - left < 10:
        return 0, 0, width, height

    return left, top, right, bottom


def _touches_all_sides(bbox_xyxy: Tuple[float, float, float, float], region: Tuple[int, int, int, int], margin: int = 2) -> bool:
    x1, y1, x2, y2 = bbox_xyxy
    rx0, ry0, rx1, ry1 = region
    return (
        x1 <= rx0 + margin and y1 <= ry0 + margin
        and x2 >= rx1 - margin and y2 >= ry1 - margin
    )


def _corner_background_estimate(gray_region: np.ndarray) -> float:
    """
    Estimate background intensity from small patches at the four corners
    only (not the full perimeter). This is deliberately more conservative
    than a full-perimeter median: a product photographed close-up often
    occupies most of the border on at least one or two sides, which would
    bias (or outright invert) a perimeter-wide estimate, but is less likely
    to cover all four corners at once.
    """
    h, w = gray_region.shape[:2]
    patch = max(3, int(round(CORNER_PATCH_FRACTION * min(h, w))))
    corners = [
        gray_region[:patch, :patch],
        gray_region[:patch, -patch:],
        gray_region[-patch:, :patch],
        gray_region[-patch:, -patch:],
    ]
    corner_medians = [float(np.median(c)) for c in corners]
    return float(np.median(corner_medians))


GRABCUT_MAX_DIMENSION = 400   # downscale target for GrabCut; keeps it well under ~0.5s per image
GRABCUT_MARGIN_FRACTION = 0.04  # inset from frame edge used as the "probably background" seed
GRABCUT_ITERATIONS = 5


def _grabcut_foreground_contour(img_bgr: np.ndarray) -> Optional[np.ndarray]:
    """
    Segment the foreground object using GrabCut, seeded with a rectangle
    inset from the frame edges (assumes -- as is typical of close-up
    inspection photography -- that the product is roughly centered and the
    outermost margin is more likely background/context).

    This is used only by detect_package_geometry() (the "FULL_GEOMETRY_ANALYSIS"
    path for a captured still), never by lightweight_geometry_check() (the
    per-frame live-capture path) -- GrabCut is too slow to run per-frame even
    at reduced resolution, and section 20 of the brief explicitly asks for
    that split. Runs on a downscaled copy purely for speed; the returned
    contour is rescaled back to the original image's coordinates.

    Returns None (never raises) if GrabCut fails to converge to a sane
    foreground region, so a demo never crashes on an unusual photo -- the
    caller simply falls back to the other signals.
    """
    height, width = img_bgr.shape[:2]
    if height < 20 or width < 20:
        return None

    scale = min(1.0, GRABCUT_MAX_DIMENSION / max(height, width))
    small = cv2.resize(img_bgr, (max(2, int(width * scale)), max(2, int(height * scale))))
    sh, sw = small.shape[:2]

    margin_x = max(1, int(GRABCUT_MARGIN_FRACTION * sw))
    margin_y = max(1, int(GRABCUT_MARGIN_FRACTION * sh))
    rect_w, rect_h = sw - 2 * margin_x, sh - 2 * margin_y
    if rect_w < 4 or rect_h < 4:
        return None

    mask = np.zeros((sh, sw), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    try:
        # GrabCut's internal GMM initialization has a random component (via
        # OpenCV's k-means); a fixed seed makes detect_package_geometry()
        # deterministic run-to-run for the SAME input image, which matters
        # both for reproducible tests and for not showing a live demo
        # audience a different answer on a re-run of an unchanged photo.
        cv2.setRNGSeed(42)
        cv2.grabCut(
            small, mask, (margin_x, margin_y, rect_w, rect_h),
            bgd_model, fgd_model, GRABCUT_ITERATIONS, cv2.GC_INIT_WITH_RECT,
        )
    except cv2.error:
        return None

    fg_mask = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    small_area = float(sh * sw)
    contours = [c for c in contours if MIN_CONTOUR_AREA_FRACTION <= (cv2.contourArea(c) / small_area) <= MAX_CONTOUR_AREA_FRACTION]
    if not contours:
        return None

    chosen = max(contours, key=cv2.contourArea)
    # Rescale back to original image coordinates.
    return (chosen.astype(np.float64) / scale).astype(np.int32)


def _content_region_candidates(gray_full: np.ndarray) -> Tuple[List[np.ndarray], Tuple[int, int, int, int]]:
    """
    Shared candidate-generation step used by both the lightweight and full
    analysis paths: strips letterbox bars, then runs the two cheap classical
    signals (corner-patch background-difference, Canny edges) on the content
    region. Returns (candidate_contours_in_ORIGINAL_coords, content_region_in_ORIGINAL_coords).
    """
    x0, y0, x1, y1 = strip_letterbox_bars(gray_full)
    gray = gray_full[y0:y1, x0:x1]
    height, width = gray.shape[:2]
    frame_area = float(height * width)

    def _valid(contours):
        return [
            c for c in contours
            if MIN_CONTOUR_AREA_FRACTION <= (cv2.contourArea(c) / frame_area) <= MAX_CONTOUR_AREA_FRACTION
        ]

    candidates: List[np.ndarray] = []

    # --- Signal 1: corner-patch background-difference segmentation ---
    bg_value = _corner_background_estimate(gray)
    diff = cv2.absdiff(gray, np.full_like(gray, int(round(bg_value))))
    diff = cv2.GaussianBlur(diff, (5, 5), 0)
    if diff.max() > 0:
        _, mask = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates.extend(_valid(contours))

    # --- Signal 2: Canny edges + closing ---
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)
    edges = cv2.erode(edges, np.ones((5, 5), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates.extend(_valid(contours))

    # Translate every candidate back into ORIGINAL image coordinates.
    translated = [c.astype(np.int32) + np.array([x0, y0], dtype=np.int32) for c in candidates]
    content_region = (x0, y0, x1, y1)
    return translated, content_region


def _pick_best_contour(
    candidates: List[np.ndarray], region: Tuple[int, int, int, int],
) -> Optional[np.ndarray]:
    """
    Prefer whichever candidate contour does NOT touch all four sides of the
    content region. A contour touching all four sides at once is the classic
    signature of a mis-estimated background (e.g. a close-up product whose
    own color got sampled as "background"), not a trustworthy package
    silhouette; it is only used as a last resort, and callers should treat
    that case with reduced confidence.
    """
    if not candidates:
        return None
    non_full_frame = []
    for c in candidates:
        bx, by, bw, bh = cv2.boundingRect(c)
        if not _touches_all_sides((bx, by, bx + bw, by + bh), region):
            non_full_frame.append(c)
    pool = non_full_frame if non_full_frame else candidates
    return max(pool, key=cv2.contourArea)


def _largest_external_contour(gray_full: np.ndarray) -> Optional[np.ndarray]:
    """
    Cheap, per-frame-suitable contour detector (letterbox-stripping +
    corner-diff + Canny only -- no GrabCut). Used by
    lightweight_geometry_check(). detect_package_geometry() uses
    _full_analysis_contour() instead, which adds a GrabCut signal.
    """
    candidates, region = _content_region_candidates(gray_full)
    return _pick_best_contour(candidates, region)


def _full_analysis_contour(img_bgr: np.ndarray) -> Optional[np.ndarray]:
    """
    Heavier contour detector for a captured still (spec section 20:
    FULL_GEOMETRY_ANALYSIS). Adds a GrabCut candidate on top of the cheap
    signals, which specifically fixes close-up/cluttered-background photos
    where no border/corner ever shows plain background (see
    _grabcut_foreground_contour's docstring). Still bounded to well under a
    second per image so it stays usable in a live demo.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    candidates, region = _content_region_candidates(gray)

    if not candidates:
        grabcut_candidate = _grabcut_foreground_contour(img_bgr)
        if grabcut_candidate is not None:
            candidates.append(grabcut_candidate)

    return _pick_best_contour(candidates, region)


# ---------------------------------------------------------------------------
# 1. Package boundary detection + shape classification
# ---------------------------------------------------------------------------

def classify_package_shape(
    contour: np.ndarray,
    image_shape: Tuple[int, int],
) -> Tuple[GeometryType, PackageShapeHint, float, List[str]]:
    """
    Conservative classical-CV shape classification.

    Returns (legal-geometry-category, descriptive-shape-hint, confidence, evidence-notes).
    Classical CV only, per spec section 12 ("do not overfit this into a
    machine-learning project").
    """
    notes: List[str] = []
    height, width = image_shape[:2]
    frame_area = float(height * width)
    contour_area = float(cv2.contourArea(contour))
    area_fraction = contour_area / frame_area if frame_area else 0.0

    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, RECTANGULAR_APPROX_EPSILON * perimeter, True)

    # Rectangular / box-like: a clean quadrilateral with roughly right angles.
    if len(approx) == 4:
        quad = _order_quad_points(approx.reshape(4, 2).astype(np.float32))
        if _is_quad_rectangular(quad):
            side_lengths = [
                float(np.linalg.norm(quad[i] - quad[(i + 1) % 4])) for i in range(4)
            ]
            aspect = max(side_lengths) / max(1e-6, min(side_lengths))
            confidence = float(np.clip(0.55 + 0.35 * min(1.0, area_fraction * 2), 0.0, 0.9))
            notes.append("4-point polygon approximation with near-right angles.")
            shape_hint = PackageShapeHint.BOX if aspect < 2.2 else PackageShapeHint.RECTANGULAR
            return GeometryType.FLAT, shape_hint, confidence, notes

    # Rounded / elliptical silhouette: candidate cylindrical (bottle/jar/can).
    if len(contour) >= 5:
        ellipse = cv2.fitEllipse(contour)
        (cx, cy), (major, minor), angle = ellipse
        ellipse_mask = np.zeros((height, width), dtype=np.uint8)
        cv2.ellipse(ellipse_mask, ellipse, 255, thickness=-1)
        contour_mask = np.zeros((height, width), dtype=np.uint8)
        cv2.drawContours(contour_mask, [contour], -1, 255, thickness=-1)
        union = np.count_nonzero(cv2.bitwise_or(ellipse_mask, contour_mask))
        intersection = np.count_nonzero(cv2.bitwise_and(ellipse_mask, contour_mask))
        iou = intersection / union if union else 0.0
        residual = 1.0 - iou

        if residual <= CYLINDRICAL_ELLIPSE_FIT_MAX_ERROR:
            elongation = max(major, minor) / max(1e-6, min(major, minor))
            confidence = float(np.clip(0.5 + 0.35 * (1.0 - residual), 0.0, 0.9))
            notes.append(f"Silhouette matches a fitted ellipse (IoU={iou:.2f}).")
            if elongation > 1.6:
                notes.append("Elongated rounded silhouette; treated as a bottle/jar-like body.")
                return (
                    GeometryType.CYLINDRICAL,
                    PackageShapeHint.BOTTLE,
                    confidence,
                    notes,
                )
            notes.append("Near-circular silhouette; treated as a jar/can-like body.")
            return (
                GeometryType.NEAR_CYLINDRICAL,
                PackageShapeHint.JAR,
                confidence,
                notes,
            )

    # Neither a clean quad nor a clean ellipse: pouch/irregular/unknown.
    hull = cv2.convexHull(contour)
    solidity = contour_area / max(1.0, float(cv2.contourArea(hull)))
    if solidity < 0.85:
        notes.append(f"Low solidity ({solidity:.2f}); consistent with a soft pouch/bag.")
        return GeometryType.IRREGULAR, PackageShapeHint.POUCH, 0.4, notes

    notes.append("Contour did not confidently match rectangular or elliptical models.")
    return GeometryType.UNKNOWN, PackageShapeHint.UNKNOWN, 0.25, notes


def detect_package_geometry(
    img_bgr: np.ndarray,
    source_image: str,
    image_quality: Optional[ImageQuality] = None,
) -> PackageGeometry:
    """
    Estimate the package boundary (not the PDP) for one captured image.

    Confidence is capped by image_quality when supplied (section 16): heavy
    blur/glare/extreme exposure problems can never be "overridden" by a
    geometrically clean-looking contour.
    """
    height, width = img_bgr.shape[:2]

    contour = _full_analysis_contour(img_bgr)
    if contour is None:
        return PackageGeometry(
            source_image=source_image,
            shape=GeometryType.UNKNOWN,
            shape_hint=PackageShapeHint.UNKNOWN,
            shape_confidence=0.0,
            notes=["No package-like contour was found in this image."],
        )

    x, y, w, h = cv2.boundingRect(contour)
    touches_left = x <= 1
    touches_top = y <= 1
    touches_right = (x + w) >= (width - 1)
    touches_bottom = (y + h) >= (height - 1)
    touches_border = touches_left or touches_top or touches_right or touches_bottom
    sides_touched = sum([touches_left, touches_top, touches_right, touches_bottom])

    shape, shape_hint, confidence, notes = classify_package_shape(contour, (height, width))

    if sides_touched >= 3:
        # Touching (almost) every edge at once is the classic signature of a
        # background-estimation failure on a close-up photo (the "background"
        # sampled turned out to be the product itself), not a genuine
        # edge-to-edge package. Treat the shape guess as low-confidence
        # rather than reporting it as a normal partial-out-of-frame case.
        notes.append(
            "Detected contour touches nearly every image edge at once; this usually indicates "
            "background/foreground ambiguity on a close-up photo rather than a package that is "
            "genuinely cut off. Shape classification confidence has been reduced accordingly."
        )
        confidence = min(confidence, 0.3)
    elif touches_border:
        notes.append("Detected contour touches the image border; the package may be partially out of frame.")
        confidence = min(confidence, 0.6)

    confidence = _apply_quality_cap(confidence, image_quality, notes)

    contour_area_fraction = float(cv2.contourArea(contour) / max(1.0, float(width * height)))

    try:
        bbox = BBox(x=float(x), y=float(y), width=float(max(1, w)), height=float(max(1, h)))
    except Exception:
        bbox = None

    epsilon = 0.01 * cv2.arcLength(contour, True)
    simplified = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
    polygon = _np_to_polygon(simplified) if len(simplified) >= 3 else None

    return PackageGeometry(
        source_image=source_image,
        shape=shape,
        shape_hint=shape_hint,
        shape_confidence=round(confidence, 3),
        bbox=bbox,
        polygon=polygon,
        contour_area_fraction=round(min(1.0, contour_area_fraction), 4),
        touches_image_border=touches_border,
        notes=notes,
    )


def _apply_quality_cap(
    confidence: float,
    image_quality: Optional[ImageQuality],
    notes: List[str],
) -> float:
    """Never let geometry confidence exceed what image quality supports (section 16)."""
    if image_quality is None:
        return confidence

    if image_quality.status == EvidenceStatus.INVALID:
        notes.append("Image quality is INVALID; geometry confidence forced to 0.")
        return 0.0

    cap = 1.0
    if image_quality.status == EvidenceStatus.LOW_QUALITY:
        cap = 0.35
        notes.append("Image quality is LOW_QUALITY; geometry confidence capped.")
    elif image_quality.status == EvidenceStatus.PARTIAL:
        cap = 0.6

    if image_quality.blur_score is not None and image_quality.blur_score < 0.15:
        cap = min(cap, 0.3)
        notes.append("Severe blur detected; geometry confidence capped.")
    if image_quality.glare_score is not None and image_quality.glare_score < 0.4:
        cap = min(cap, 0.45)
        notes.append("Significant glare detected; geometry confidence capped.")
    if image_quality.perspective_score is not None and image_quality.perspective_score < 0.35:
        cap = min(cap, 0.5)
        notes.append("Extreme perspective flagged by image-quality pipeline; geometry confidence capped.")

    return min(confidence, cap)


# ---------------------------------------------------------------------------
# 2. PDP detection
# ---------------------------------------------------------------------------

def detect_pdp_geometry(
    img_bgr: np.ndarray,
    source_image: str,
    package_geometry: Optional[PackageGeometry] = None,
    ocr_boxes: Optional[Sequence[Tuple[int, int, int, int]]] = None,
    image_quality: Optional[ImageQuality] = None,
) -> PDPGeometry:
    """
    Estimate the PDP region, kept explicitly distinct from the package
    boundary.

    Strategy (conservative, classical-CV):
    - If OCR text boxes are supplied, the PDP candidate is the padded
      bounding region around them (this is the same idea as
      image_quality.estimate_pdp_bbox, reused here so geometry and OCR never
      disagree about what "the text region" means) intersected with the
      package boundary when available.
    - If no OCR boxes are available, fall back to the package boundary
      itself as a low-confidence PDP proxy (front-facing single-surface
      captures), explicitly flagged as `derived_from_package_boundary_only`.
    - If neither is available, PDP is NOT_OBSERVED. This is never reported
      as "missing" -- only as "not yet seen".
    """
    height, width = img_bgr.shape[:2]
    notes: List[str] = []

    package_bbox_np = None
    if package_geometry is not None and package_geometry.bbox is not None:
        b = package_geometry.bbox
        package_bbox_np = (b.x, b.y, b.right(), b.bottom())

    if ocr_boxes:
        xs1 = [b[0] for b in ocr_boxes]
        ys1 = [b[1] for b in ocr_boxes]
        xs2 = [b[0] + b[2] for b in ocr_boxes]
        ys2 = [b[1] + b[3] for b in ocr_boxes]
        x1, y1, x2, y2 = min(xs1), min(ys1), max(xs2), max(ys2)
        pad_x = max(4, int(0.04 * width))
        pad_y = max(4, int(0.04 * height))
        x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
        x2, y2 = min(width, x2 + pad_x), min(height, y2 + pad_y)

        if package_bbox_np is not None:
            px1, py1, px2, py2 = package_bbox_np
            x1, y1 = max(x1, px1), max(y1, py1)
            x2, y2 = min(x2, px2), min(y2, py2)
            notes.append("PDP candidate intersected with the detected package boundary.")

        w = max(1.0, float(x2 - x1))
        h = max(1.0, float(y2 - y1))
        confidence = 0.55 if package_bbox_np is None else 0.65
        notes.append("PDP candidate derived from OCR text-region clustering.")

        confidence = _apply_quality_cap(confidence, image_quality, notes)

        polygon = [
            PolygonPoint(x=float(x1), y=float(y1)),
            PolygonPoint(x=float(x2), y=float(y1)),
            PolygonPoint(x=float(x2), y=float(y2)),
            PolygonPoint(x=float(x1), y=float(y2)),
        ]

        return PDPGeometry(
            source_image=source_image,
            observation_status=PDPObservationStatus.OBSERVED,
            confidence=round(confidence, 3),
            bbox=BBox(x=float(x1), y=float(y1), width=w, height=h),
            polygon=polygon,
            is_planar=(package_geometry.shape == GeometryType.FLAT) if package_geometry else True,
            surface_hint=SurfaceType.UNKNOWN,
            derived_from_package_boundary_only=False,
            notes=notes,
        )

    if package_geometry is not None and package_geometry.bbox is not None and package_geometry.shape_confidence > 0:
        notes.append(
            "No OCR text regions supplied; using the package boundary itself as a "
            "low-confidence PDP proxy. This is an estimate, not a verified PDP."
        )
        confidence = min(0.4, package_geometry.shape_confidence)
        confidence = _apply_quality_cap(confidence, image_quality, notes)
        return PDPGeometry(
            source_image=source_image,
            observation_status=PDPObservationStatus.PARTIAL,
            confidence=round(confidence, 3),
            bbox=package_geometry.bbox,
            polygon=package_geometry.polygon,
            is_planar=(package_geometry.shape == GeometryType.FLAT),
            surface_hint=SurfaceType.UNKNOWN,
            derived_from_package_boundary_only=True,
            notes=notes,
        )

    return PDPGeometry(
        source_image=source_image,
        observation_status=PDPObservationStatus.NOT_OBSERVED,
        confidence=0.0,
        notes=["No PDP evidence available yet for this image (not the same as 'missing')."],
    )


# ---------------------------------------------------------------------------
# 3. Perspective correction / rectification
# ---------------------------------------------------------------------------

def validate_quadrilateral(polygon: Sequence[PolygonPoint]) -> Tuple[bool, List[str]]:
    """Sanity-check a 4-point polygon before attempting a perspective transform."""
    notes: List[str] = []
    if len(polygon) != 4:
        return False, ["Rectification requires exactly 4 corner points."]

    pts = _order_quad_points(_polygon_to_np(polygon))
    side_lengths = [float(np.linalg.norm(pts[i] - pts[(i + 1) % 4])) for i in range(4)]
    if min(side_lengths) < 4:
        return False, ["Quadrilateral is degenerate (near-zero side length)."]

    aspect_extreme = max(side_lengths) / max(1e-6, min(side_lengths))
    if aspect_extreme > PDP_TOO_OBLIQUE_MAX_ANGLE_RATIO * 3:
        notes.append("Quadrilateral side-length ratio is extreme; perspective may be too oblique to rectify reliably.")

    angles = _quad_interior_angles_deg(pts)
    if any(a < 15 or a > 165 for a in angles):
        return False, notes + ["Quadrilateral has a near-degenerate (too acute/reflex) corner angle."]

    return True, notes


def rectify_pdp(
    img_bgr: np.ndarray,
    source_image: str,
    polygon: Sequence[PolygonPoint],
    output_width: Optional[int] = None,
    output_height: Optional[int] = None,
) -> Tuple[Optional[np.ndarray], Optional[RectificationResult]]:
    """
    Perspective-rectify a planar PDP candidate quadrilateral.

    Returns (rectified_image_or_None, RectificationResult_or_None). Returns
    (None, None) when the quadrilateral is not suitable for rectification
    (see validate_quadrilateral) -- callers should treat this as
    MEASUREMENT_UNCERTAIN geometry rather than fabricating a transform.

    The source image is never modified in place; the rectified image is a
    new array, and RectificationResult retains the homography + source
    polygon so any coordinate can be mapped back (see map_region_coordinates).
    """
    ok, notes = validate_quadrilateral(polygon)
    if not ok:
        return None, None

    src_pts = _order_quad_points(_polygon_to_np(polygon))

    side_top = np.linalg.norm(src_pts[0] - src_pts[1])
    side_bottom = np.linalg.norm(src_pts[3] - src_pts[2])
    side_left = np.linalg.norm(src_pts[0] - src_pts[3])
    side_right = np.linalg.norm(src_pts[1] - src_pts[2])

    out_w = output_width or int(round(max(side_top, side_bottom)))
    out_h = output_height or int(round(max(side_left, side_right)))
    out_w = max(2, out_w)
    out_h = max(2, out_h)

    dst_pts = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype=np.float32,
    )

    homography = cv2.getPerspectiveTransform(src_pts, dst_pts)
    rectified = cv2.warpPerspective(img_bgr, homography, (out_w, out_h))

    # Reprojection error: map dst corners back with the inverse homography
    # and compare against the original source corners.
    inv_h = np.linalg.inv(homography)
    reprojected = cv2.perspectiveTransform(dst_pts.reshape(-1, 1, 2), inv_h).reshape(-1, 2)
    reproj_error = float(np.mean(np.linalg.norm(reprojected - src_pts, axis=1)))

    result = RectificationResult(
        source_image=source_image,
        source_polygon=_np_to_polygon(src_pts),
        homography=[float(v) for v in homography.flatten()],
        rectified_width_px=out_w,
        rectified_height_px=out_h,
        reprojection_error_px=round(reproj_error, 3),
        notes=notes,
    )
    return rectified, result


def map_point_through_homography(
    x: float, y: float, homography: Sequence[float], invert: bool = False,
) -> Tuple[float, float]:
    """Map one (x, y) point through a flattened 3x3 homography (or its inverse)."""
    h = np.array(homography, dtype=np.float64).reshape(3, 3)
    if invert:
        h = np.linalg.inv(h)
    pt = np.array([x, y, 1.0], dtype=np.float64)
    mapped = h @ pt
    if abs(mapped[2]) < 1e-9:
        return float("nan"), float("nan")
    return float(mapped[0] / mapped[2]), float(mapped[1] / mapped[2])


def map_region_coordinates(
    bbox: BBox,
    homography: Sequence[float],
    invert: bool = False,
) -> BBox:
    """
    Map a BBox (e.g. an OCR text region in the original image) into rectified
    coordinates (or back, with invert=True), using a RectificationResult's
    homography.

    This is what lets an OCR region -> PDP-relative -> rectified coordinate
    chain (spec section 9) work without the geometry and OCR modules
    duplicating each other's logic.
    """
    corners = [
        (bbox.x, bbox.y),
        (bbox.right(), bbox.y),
        (bbox.right(), bbox.bottom()),
        (bbox.x, bbox.bottom()),
    ]
    mapped = [map_point_through_homography(x, y, homography, invert=invert) for x, y in corners]
    xs = [p[0] for p in mapped]
    ys = [p[1] for p in mapped]
    x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
    return BBox(x=max(0.0, x1), y=max(0.0, y1), width=max(1e-3, x2 - x1), height=max(1e-3, y2 - y1))


def normalize_bbox(bbox: BBox, image_width: int, image_height: int) -> BBox:
    """Convert an IMAGE_PIXELS bbox to NORMALIZED_0_1 coordinates."""
    return BBox(
        x=bbox.x / image_width,
        y=bbox.y / image_height,
        width=bbox.width / image_width,
        height=bbox.height / image_height,
    )


def denormalize_bbox(bbox: BBox, image_width: int, image_height: int) -> BBox:
    """Convert a NORMALIZED_0_1 bbox back to IMAGE_PIXELS coordinates."""
    return BBox(
        x=bbox.x * image_width,
        y=bbox.y * image_height,
        width=bbox.width * image_width,
        height=bbox.height * image_height,
    )


# ---------------------------------------------------------------------------
# 4. Live-capture geometry readiness (lightweight)
# ---------------------------------------------------------------------------

def lightweight_geometry_check(
    img_bgr: np.ndarray,
    image_quality: Optional[ImageQuality] = None,
    calibration_available: bool = False,
) -> GeometryReadinessResult:
    """
    Cheap, live-camera-friendly geometry check (spec section 20:
    LIGHTWEIGHT_GEOMETRY vs FULL_GEOMETRY_ANALYSIS).

    Runs the same contour detector as detect_package_geometry() but skips
    ellipse-fitting/solidity/shape classification, keeping this suitable for
    per-frame use. Intended to back the live-capture status enum; NOT a
    substitute for detect_package_geometry()+detect_pdp_geometry() on the
    still that actually gets saved as evidence.

    IMPORTANT: GeometryReadiness.READY_FOR_CAPTURE means "geometry looks
    capturable", never "legally compliant".
    """
    height, width = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    contour = _largest_external_contour(gray)

    if contour is None:
        return GeometryReadinessResult(
            status=GeometryReadiness.PACKAGE_NOT_DETECTED,
            confidence=0.0,
            reasons=["No package-like contour detected in frame."],
        )

    x, y, w, h = cv2.boundingRect(contour)
    touches_left = x <= 1
    touches_top = y <= 1
    touches_right = (x + w) >= (width - 1)
    touches_bottom = (y + h) >= (height - 1)
    touches_border = touches_left or touches_top or touches_right or touches_bottom
    sides_touched = sum([touches_left, touches_top, touches_right, touches_bottom])
    frame_area = float(width * height)
    area_fraction = float(cv2.contourArea(contour) / frame_area) if frame_area else 0.0

    reasons: List[str] = []

    if sides_touched >= 3:
        reasons.append(
            "Frame is ambiguous (contour touches nearly every edge); move the package so its "
            "full silhouette is clearly separated from the background."
        )
        return GeometryReadinessResult(
            status=GeometryReadiness.INSUFFICIENT_SURFACE_VISIBLE,
            confidence=0.3,
            reasons=reasons,
        )

    if touches_border:
        reasons.append("Package appears to extend beyond the frame edge.")
        return GeometryReadinessResult(
            status=GeometryReadiness.PACKAGE_PARTIALLY_OUT_OF_FRAME,
            confidence=0.5,
            reasons=reasons,
        )

    if area_fraction < 0.10:
        reasons.append("Package occupies a small fraction of the frame; move closer.")
        return GeometryReadinessResult(
            status=GeometryReadiness.INSUFFICIENT_SURFACE_VISIBLE,
            confidence=0.4,
            reasons=reasons,
        )

    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, RECTANGULAR_APPROX_EPSILON * perimeter, True)
    if len(approx) == 4:
        quad = _order_quad_points(approx.reshape(4, 2).astype(np.float32))
        side_lengths = [float(np.linalg.norm(quad[i] - quad[(i + 1) % 4])) for i in range(4)]
        oblique_ratio = max(side_lengths) / max(1e-6, min(side_lengths))
        top_bottom_ratio = side_lengths[0] / max(1e-6, side_lengths[2])
        if top_bottom_ratio > PDP_TOO_OBLIQUE_MAX_ANGLE_RATIO or top_bottom_ratio < (1 / PDP_TOO_OBLIQUE_MAX_ANGLE_RATIO):
            reasons.append("Surface is viewed at a steep angle; capture more head-on.")
            return GeometryReadinessResult(
                status=GeometryReadiness.PDP_TOO_OBLIQUE,
                confidence=0.5,
                reasons=reasons,
            )

    quality_ok = image_quality is None or image_quality.status in (
        EvidenceStatus.USABLE, EvidenceStatus.PARTIAL,
    )
    if not quality_ok:
        reasons.append("Image quality issue detected (blur/glare/exposure).")
        return GeometryReadinessResult(
            status=GeometryReadiness.GOOD_GEOMETRY,
            confidence=0.5,
            reasons=reasons + ["Geometry looks acceptable but image quality is currently insufficient to capture."],
        )

    if not calibration_available:
        reasons.append("Geometry is good, but no calibration reference has been established yet for physical measurement.")
        return GeometryReadinessResult(
            status=GeometryReadiness.CALIBRATION_REQUIRED,
            confidence=0.75,
            reasons=reasons,
        )

    reasons.append("Package geometry, framing and calibration all look sufficient for evidence capture.")
    return GeometryReadinessResult(
        status=GeometryReadiness.READY_FOR_CAPTURE,
        confidence=0.85,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# 5. Multi-image geometry / overlap
# ---------------------------------------------------------------------------

def bbox_overlap_fraction(a: BBox, b: BBox) -> float:
    """
    IoU-style overlap between two bboxes in the SAME coordinate system.
    Used as a lightweight capture-quality recommendation (section 11), never
    a legal requirement.
    """
    ax1, ay1, ax2, ay2 = a.x, a.y, a.right(), a.bottom()
    bx1, by1, bx2, by2 = b.x, b.y, b.right(), b.bottom()

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    intersection = iw * ih

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return float(intersection / union) if union > 0 else 0.0


def overlap_recommendation(overlap_fraction: float) -> str:
    """Human-readable capture-quality hint, never a hard legal gate."""
    if overlap_fraction < RECOMMENDED_OVERLAP_MIN:
        return (
            f"Overlap with the previous capture is only {overlap_fraction:.0%}; "
            f"aim for roughly {RECOMMENDED_OVERLAP_MIN:.0%}-{RECOMMENDED_OVERLAP_MAX:.0%} "
            "so declarations split across surfaces are not double-counted or missed."
        )
    if overlap_fraction > 0.9:
        return "This capture almost entirely duplicates the previous one; consider moving to a new surface."
    return "Overlap looks reasonable for stitching evidence across captures."


def align_multi_image_surfaces(
    img_a_bgr: np.ndarray,
    img_b_bgr: np.ndarray,
    max_features: int = 500,
    good_match_fraction: float = 0.35,
) -> Optional[List[float]]:
    """
    Attempt to align two images of (assumed) the same physical surface using
    ORB features + RANSAC homography estimation. This is a lightweight,
    classical-CV alignment for combining split PDP evidence (e.g. a
    Pringles-style cylindrical label photographed across two rotations) --
    it is deliberately NOT a full structure-from-motion pipeline.

    Returns a flattened 3x3 homography mapping image A pixel coordinates ->
    image B pixel coordinates, or None if alignment confidence is too low to
    trust (insufficient or inconsistent feature matches). Callers must treat
    a None result as "cannot align; do not fuse coordinates across these two
    images" rather than guessing.
    """
    orb = cv2.ORB_create(nfeatures=max_features)
    gray_a = cv2.cvtColor(img_a_bgr, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(img_b_bgr, cv2.COLOR_BGR2GRAY)

    kp_a, des_a = orb.detectAndCompute(gray_a, None)
    kp_b, des_b = orb.detectAndCompute(gray_b, None)
    if des_a is None or des_b is None or len(kp_a) < 8 or len(kp_b) < 8:
        return None

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = matcher.match(des_a, des_b)
    if len(matches) < 8:
        return None

    matches = sorted(matches, key=lambda m: m.distance)
    n_good = max(8, int(len(matches) * good_match_fraction))
    good = matches[:n_good]

    pts_a = np.float32([kp_a[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    pts_b = np.float32([kp_b[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    homography, inlier_mask = cv2.findHomography(pts_a, pts_b, cv2.RANSAC, 5.0)
    if homography is None or inlier_mask is None:
        return None

    inlier_fraction = float(np.mean(inlier_mask))
    if inlier_fraction < 0.4 or int(np.sum(inlier_mask)) < 8:
        # Too few consistent matches to trust the alignment.
        return None

    return [float(v) for v in homography.flatten()]
