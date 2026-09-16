"""
LexMetra First-Stage Computer Vision & Package Normalization Pipeline.

Produces a clean, Adobe Scan-like, document-style package image that is:
- tightly cropped to the package with an evidence-safe outward margin
- perspective corrected (front-facing rectangle)
- background normalized toward white/neutral
- glare reduced where safely possible
- uneven illumination reduced
- small printed text made clearer
- color information preserved
- suitable for Qwen3.8-27B visual analysis

EVIDENCE-SAFE CROPPING CONTRACT:
The detected physical boundary is NOT used as the exact crop boundary.
DETECTED PHYSICAL BOUNDARY -> OUTWARD SAFETY MARGIN -> EVIDENCE-SAFE BOUNDARY -> CROP / HOMOGRAPHY
The crop strictly prefers inclusion over tightness so that zero package declarations,
barcodes, batch numbers, or dates are clipped.

Coordinate Integrity:
Maintains mathematical CoordinateTransform (homography) to map coordinates
from the final normalized image back to the original camera photograph.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from geometry import CoordinateSpace, CoordinateTransform

logger = logging.getLogger(__name__)


@dataclass
class PreprocessingPipelineResult:
    """Complete bundle of generated stages, transforms, and audit metadata."""
    original_bgr: np.ndarray
    boundary_detected_bgr: np.ndarray
    perspective_bgr: np.ndarray
    cropped_bgr: np.ndarray
    background_normalized_bgr: np.ndarray
    glare_reduced_bgr: np.ndarray
    illumination_corrected_bgr: np.ndarray
    text_enhanced_bgr: np.ndarray
    final_bgr: np.ndarray
    metadata: Dict[str, Any]
    forward_transform: CoordinateTransform
    inverse_transform: CoordinateTransform
    physical_corners: List[List[float]] = field(default_factory=list)
    evidence_safe_corners: List[List[float]] = field(default_factory=list)


def order_corners(points: np.ndarray) -> np.ndarray:
    """
    Order 4 points as: Top-Left, Top-Right, Bottom-Right, Bottom-Left.
    Uses sum (x+y) and difference (y-x) with aspect-ratio validation.
    """
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    ordered = np.zeros((4, 2), dtype=np.float32)

    s = pts.sum(axis=1)
    ordered[0] = pts[np.argmin(s)]  # Top-left has smallest x + y
    ordered[2] = pts[np.argmax(s)]  # Bottom-right has largest x + y

    diff = np.diff(pts, axis=1).ravel()
    ordered[1] = pts[np.argmin(diff)]  # Top-right has smallest y - x
    ordered[3] = pts[np.argmax(diff)]  # Bottom-left has largest y - x

    return ordered


def expand_boundary_corners(
    corners: Sequence[Sequence[float]],
    img_shape: Tuple[int, int],
    margin_pct: float = 0.06,
) -> List[List[float]]:
    """
    Expand detected physical boundary corners outward from the package centroid
    by a safety margin percentage (default 6%).
    Clamped to image boundary limits [0, w-1] and [0, h-1].
    Prefers inclusion over tightness to guarantee zero evidence clipping.
    """
    pts = np.asarray(corners, dtype=np.float32).reshape(4, 2)
    h, w = img_shape[:2]
    centroid = pts.mean(axis=0)

    expanded = []
    for pt in pts:
        vec = pt - centroid
        new_pt = pt + margin_pct * vec
        clamped_x = float(np.clip(new_pt[0], 0, w - 1))
        clamped_y = float(np.clip(new_pt[1], 0, h - 1))
        expanded.append([round(clamped_x, 1), round(clamped_y, 1)])
    return expanded


def detect_package_boundary(img_bgr: np.ndarray) -> Dict[str, Any]:
    """
    OpenCV Package Boundary Detector.
    Identifies the physical package quadrilateral before outward expansion.

    Returns:
    {
        "detected": bool,
        "corners": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]],  # in original coordinates
        "confidence": float,
        "method": str
    }
    """
    orig_h, orig_w = img_bgr.shape[:2]
    target_dim = 1024
    scale = target_dim / float(max(orig_h, orig_w))
    sw, sh = int(round(orig_w * scale)), int(round(orig_h * scale))
    small = cv2.resize(img_bgr, (sw, sh), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    # 1. Bilateral filter: preserves major structural edges while smoothing small text
    filtered = cv2.bilateralFilter(gray, 9, 75, 75)

    # 2. Gradient magnitude & active bounds
    grad_x = cv2.Sobel(filtered, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(filtered, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.hypot(grad_x, grad_y)

    r_act = grad_mag.mean(axis=1)
    c_act = grad_mag.mean(axis=0)
    thresh_r = np.percentile(r_act, 25)
    thresh_c = np.percentile(c_act, 25)
    valid_r = np.where(r_act > thresh_r)[0]
    valid_c = np.where(c_act > thresh_c)[0]

    min_active_y = int(valid_r[0]) if len(valid_r) > 0 else 0
    max_active_y = int(valid_r[-1]) if len(valid_r) > 0 else sh - 1
    min_active_x = int(valid_c[0]) if len(valid_c) > 0 else 0
    max_active_x = int(valid_c[-1]) if len(valid_c) > 0 else sw - 1

    # 3. Compute Canny edges and Hough lines
    edges = cv2.Canny(filtered, 40, 120)
    min_len = int(sh * 0.035)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=40, minLineLength=min_len, maxLineGap=int(sh * 0.02))

    v_segs_left = []
    v_segs_right = []
    h_segs_top = []
    h_segs_bot = []

    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx = x2 - x1
            dy = y2 - y1
            length = float(np.hypot(dx, dy))
            angle = float(np.abs(np.arctan2(dy, dx) * 180.0 / np.pi))
            mid_x = (x1 + x2) / 2.0
            mid_y = (y1 + y2) / 2.0

            # Vertical lines (75 to 105 deg)
            if 75.0 <= angle <= 105.0 and length >= sh * 0.03:
                if mid_x < sw * 0.48:
                    v_segs_left.append((x1, y1, x2, y2, mid_x, length))
                elif mid_x > sw * 0.52:
                    v_segs_right.append((x1, y1, x2, y2, mid_x, length))
            # Horizontal lines (0 to 20 or 160 to 180 deg)
            elif (angle <= 20.0 or angle >= 160.0) and length >= sw * 0.05:
                if mid_y < sh * 0.45:
                    h_segs_top.append((x1, y1, x2, y2, mid_y, length))
                elif mid_y > sh * 0.55:
                    h_segs_bot.append((x1, y1, x2, y2, mid_y, length))

    # Strategy A: Hough line clustering with active extent bounds
    if v_segs_left and v_segs_right and h_segs_top and h_segs_bot:
        min_lx = min(s[4] for s in v_segs_left)
        outer_left = [s for s in v_segs_left if s[4] <= min_lx + sw * 0.12]

        max_rx = max(s[4] for s in v_segs_right)
        outer_right = [s for s in v_segs_right if s[4] >= max_rx - sw * 0.12]

        min_ty = min(s[4] for s in h_segs_top)
        outer_top = [s for s in h_segs_top if s[4] <= min_ty + sh * 0.12]

        max_by = max(s[4] for s in h_segs_bot)
        # Ensure bottom bound does not cut active package rows
        max_by = max(max_by, max_active_y * 0.95)
        outer_bot = [s for s in h_segs_bot if s[4] >= max_by - sh * 0.12]

        def get_line_pts(segs):
            pts = []
            for s in segs:
                pts.append([s[0], s[1]])
                pts.append([s[2], s[3]])
            return np.array(pts, dtype=np.float32)

        def fit_v(pts):
            line = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01)
            vx, vy, x0, y0 = float(line[0][0]), float(line[1][0]), float(line[2][0]), float(line[3][0])
            if vy < 0:
                vx, vy = -vx, -vy
            return lambda y: x0 + (y - y0) * (vx / vy) if abs(vy) > 1e-4 else x0

        def fit_h(pts):
            line = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01)
            vx, vy, x0, y0 = float(line[0][0]), float(line[1][0]), float(line[2][0]), float(line[3][0])
            if vx < 0:
                vx, vy = -vx, -vy
            return lambda x: y0 + (x - x0) * (vy / vx) if abs(vx) > 1e-4 else y0

        try:
            fn_l = fit_v(get_line_pts(outer_left))
            fn_r = fit_v(get_line_pts(outer_right))
            fn_t = fit_h(get_line_pts(outer_top))
            fn_b = fit_h(get_line_pts(outer_bot)) if outer_bot else (lambda x: float(max_by))

            y_t = min_ty
            x_tl = fn_l(y_t)
            y_tl = fn_t(x_tl)
            x_tl = fn_l(y_tl)

            x_tr = fn_r(y_t)
            y_tr = fn_t(x_tr)
            x_tr = fn_r(y_tr)

            y_b = max_by
            x_br = fn_r(y_b)
            y_br = fn_b(x_br)
            x_br = fn_r(y_br)

            x_bl = fn_l(y_b)
            y_bl = fn_b(x_bl)
            x_bl = fn_l(y_bl)

            cand_pts = np.array([[x_tl, y_tl], [x_tr, y_tr], [x_br, y_br], [x_bl, y_bl]], dtype=np.float32)
            ordered_cand = order_corners(cand_pts)

            area = float(cv2.contourArea(ordered_cand))
            area_frac = area / float(sw * sh)

            if 0.12 <= area_frac <= 0.95 and cv2.isContourConvex(np.int32(ordered_cand)):
                orig_corners = (ordered_cand / scale).tolist()
                return {
                    "detected": True,
                    "corners": [[round(p[0], 1), round(p[1], 1)] for p in orig_corners],
                    "confidence": 0.92,
                    "method": "HOUGH_EDGE_INTERSECTION",
                }
        except Exception as e:
            logger.debug("Hough intersection fallback: %s", e)

    # Strategy B: Contour convex hull polygon approximation
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cnts, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    large_cnts = [c for c in cnts if cv2.contourArea(c) > (sw * sh * 0.15)]
    if large_cnts:
        best_c = max(large_cnts, key=cv2.contourArea)
        hull = cv2.convexHull(best_c)
        peri = cv2.arcLength(hull, True)
        for eps_ratio in [0.02, 0.03, 0.04, 0.05, 0.06]:
            approx = cv2.approxPolyDP(hull, eps_ratio * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                ordered = order_corners(approx.reshape(4, 2))
                area_frac = cv2.contourArea(ordered) / float(sw * sh)
                if 0.12 <= area_frac <= 0.95:
                    orig_corners = (ordered / scale).tolist()
                    return {
                        "detected": True,
                        "corners": [[round(p[0], 1), round(p[1], 1)] for p in orig_corners],
                        "confidence": 0.78,
                        "method": "CONTOUR_HULL_POLY",
                    }

    # Strategy C: Active gradient envelope (reliable fallback for curved packages)
    if len(valid_r) > 10 and len(valid_c) > 10:
        x0, x1 = min_active_x, max_active_x
        y0, y1 = min_active_y, max_active_y
        pad_x = int((x1 - x0) * 0.02)
        pad_y = int((y1 - y0) * 0.02)
        x0 = max(0, x0 - pad_x)
        y0 = max(0, y0 - pad_y)
        x1 = min(sw - 1, x1 + pad_x)
        y1 = min(sh - 1, y1 + pad_y)
        corners = [
            [round(x0 / scale, 1), round(y0 / scale, 1)],
            [round(x1 / scale, 1), round(y0 / scale, 1)],
            [round(x1 / scale, 1), round(y1 / scale, 1)],
            [round(x0 / scale, 1), round(y1 / scale, 1)],
        ]
        return {
            "detected": True,
            "corners": corners,
            "confidence": 0.70,
            "method": "GRADIENT_ENVELOPE",
        }

    return {"detected": False, "corners": [], "confidence": 0.0, "method": "NONE"}


def draw_boundary_debug(
    img_bgr: np.ndarray,
    physical_corners: Sequence[Sequence[float]],
    evidence_safe_corners: Sequence[Sequence[float]],
) -> np.ndarray:
    """
    Stage 02 Dual-Boundary Debug Visualization.
    Clearly shows:
    - Detected physical boundary (Orange, thickness=4, labeled PHYS:1..PHYS:4)
    - Evidence-safe expanded boundary (Green, thickness=6, labeled SAFE:1..SAFE:4)
    With a clear on-image legend banner.
    """
    debug_img = img_bgr.copy()
    h, w = debug_img.shape[:2]

    # Draw Legend Banner at top
    banner_h = max(60, int(h * 0.04))
    overlay = debug_img.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), (30, 30, 30), -1)
    debug_img = cv2.addWeighted(overlay, 0.75, debug_img, 0.25, 0)

    font_scale = max(0.6, w / 1600.0)
    cv2.putText(
        debug_img,
        "[ORANGE] DETECTED PHYSICAL BOUNDARY  |  [GREEN] EVIDENCE-SAFE EXPANDED BOUNDARY",
        (int(w * 0.03), int(banner_h * 0.65)),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (255, 255, 255),
        2,
        lineType=cv2.LINE_AA,
    )

    # 1. Draw Physical Boundary (Orange)
    if physical_corners and len(physical_corners) == 4:
        phys_pts = np.array(physical_corners, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(debug_img, [phys_pts], isClosed=True, color=(0, 140, 255), thickness=4, lineType=cv2.LINE_AA)
        for i, pt in enumerate(physical_corners):
            px, py = int(round(pt[0])), int(round(pt[1]))
            cv2.circle(debug_img, (px, py), 12, (0, 140, 255), -1, lineType=cv2.LINE_AA)
            cv2.putText(
                debug_img,
                f"PHYS:{i+1}",
                (px + 15, py - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale * 0.9,
                (0, 140, 255),
                2,
                lineType=cv2.LINE_AA,
            )

    # 2. Draw Evidence-Safe Expanded Boundary (Bright Green)
    if evidence_safe_corners and len(evidence_safe_corners) == 4:
        safe_pts = np.array(evidence_safe_corners, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(debug_img, [safe_pts], isClosed=True, color=(0, 255, 0), thickness=6, lineType=cv2.LINE_AA)
        for i, pt in enumerate(evidence_safe_corners):
            px, py = int(round(pt[0])), int(round(pt[1]))
            cv2.circle(debug_img, (px, py), 16, (0, 255, 0), -1, lineType=cv2.LINE_AA)
            cv2.circle(debug_img, (px, py), 18, (255, 255, 255), 2, lineType=cv2.LINE_AA)
            cv2.putText(
                debug_img,
                f"SAFE:{i+1}",
                (px + 20, py + 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale * 0.9,
                (0, 255, 0),
                2,
                lineType=cv2.LINE_AA,
            )

    return debug_img


def rectify_perspective(
    img_bgr: np.ndarray,
    corners: Sequence[Sequence[float]],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Warp quadrilateral to front-facing rectangle using homography.
    Returns: (rectified_bgr, forward_homography_matrix, inverse_homography_matrix)
    """
    ordered = order_corners(np.asarray(corners, dtype=np.float32))
    tl, tr, br, bl = ordered

    width_top = float(np.linalg.norm(tr - tl))
    width_bot = float(np.linalg.norm(br - bl))
    height_left = float(np.linalg.norm(bl - tl))
    height_right = float(np.linalg.norm(br - tr))

    out_w = max(16, int(round(max(width_top, width_bot))))
    out_h = max(16, int(round(max(height_left, height_right))))

    destination = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype=np.float32,
    )

    fwd_m = cv2.getPerspectiveTransform(ordered, destination)
    inv_m = cv2.getPerspectiveTransform(destination, ordered)

    rectified = cv2.warpPerspective(
        img_bgr,
        fwd_m,
        (out_w, out_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rectified, fwd_m, inv_m


def normalize_background(img_bgr: np.ndarray, safety_margin_pct: float = 0.015) -> np.ndarray:
    """
    Adobe-Scan-like background normalization:
    - Neutralizes background / shadows outside the package to near-white (250, 250, 250).
    - Preserves package interior colors, labels, logos, and declarations completely intact.
    """
    h, w = img_bgr.shape[:2]
    pad_x = int(w * safety_margin_pct)
    pad_y = int(h * safety_margin_pct)

    mask = np.ones((h, w), dtype=np.float32)
    if pad_x > 0 and pad_y > 0:
        cv2.rectangle(mask, (0, 0), (w - 1, h - 1), 0.0, thickness=min(pad_x, pad_y))
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=float(max(pad_x, pad_y)))

    mask_3c = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
    neutral_bg = np.full_like(img_bgr, 250, dtype=np.uint8)

    normalized = np.clip(
        img_bgr.astype(np.float32) * mask_3c + neutral_bg.astype(np.float32) * (1.0 - mask_3c),
        0,
        255,
    ).astype(np.uint8)
    return normalized


def reduce_glare(img_bgr: np.ndarray) -> Tuple[np.ndarray, bool]:
    """
    Conservative glare detection and reduction.
    Distinguishes specular highlights from legitimate printed white text.
    Returns: (glare_reduced_bgr, glare_detected)
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)

    l_chan = lab[:, :, 0]
    s_chan = hsv[:, :, 1]

    glare_candidates = (l_chan >= 248) & (s_chan <= 25)
    glare_mask = (glare_candidates * 255).astype(np.uint8)

    # Filter out text strokes: text strokes have small area and high stroke gradient
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    true_glare = cv2.morphologyEx(glare_mask, cv2.MORPH_OPEN, kernel)

    glare_fraction = float(np.mean(true_glare > 0))
    if glare_fraction < 0.0005:
        return img_bgr.copy(), False

    dilated_glare = cv2.dilate(true_glare, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    reduced = cv2.inpaint(img_bgr, dilated_glare, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
    return reduced, True


def correct_illumination(img_bgr: np.ndarray, sigma: float = 35.0) -> np.ndarray:
    """
    Luminance-aware uneven illumination correction in LAB color space.
    Flattens shadows and lighting gradients without destroying package color or structure.
    """
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    illum_bg = cv2.GaussianBlur(l, (0, 0), sigmaX=sigma).astype(np.float32)
    illum_bg[illum_bg < 1.0] = 1.0

    mean_l = float(np.mean(l))
    l_flat = np.clip((l.astype(np.float32) / illum_bg) * mean_l, 0, 255)

    l_corr = np.clip(0.85 * l_flat + 0.15 * l.astype(np.float32), 0, 255).astype(np.uint8)
    merged_lab = cv2.merge([l_corr, a, b])
    return cv2.cvtColor(merged_lab, cv2.COLOR_LAB2BGR)


def enhance_text_declarations(img_bgr: np.ndarray) -> np.ndarray:
    """
    Controlled text-preserving enhancement:
    - Mild CLAHE on lightness to make faint dot-matrix digits distinct.
    - Mild unsharp masking for stroke crispness without halo artifacts.
    - Preserves natural package color.
    """
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8))
    l_clahe = clahe.apply(l)

    blurred_l = cv2.GaussianBlur(l_clahe, (0, 0), sigmaX=1.0)
    l_sharp = np.clip(cv2.addWeighted(l_clahe, 1.25, blurred_l, -0.25, 0), 0, 255).astype(np.uint8)

    merged = cv2.merge([l_sharp, a, b])
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def resize_and_encode_final(
    img_bgr: np.ndarray,
    max_dim: int = 1024,
    jpeg_quality: int = 85,
) -> Tuple[np.ndarray, float, float]:
    """
    Resize to target dimension (e.g. ~1024 px max) and compute scale factors.
    Returns: (final_img_bgr, scale_x, scale_y)
    """
    h, w = img_bgr.shape[:2]
    largest = max(h, w)
    if largest > max_dim:
        scale = max_dim / float(largest)
        new_w = max(16, int(round(w * scale)))
        new_h = max(16, int(round(h * scale)))
        resized = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return resized, new_w / float(w), new_h / float(h)
    return img_bgr.copy(), 1.0, 1.0


def run_preprocessing_pipeline(
    img_bgr: np.ndarray,
    source_name: str = "capture",
    product: str = "PACKAGE",
    face: str = "Face 1",
    debug_dir: Optional[Path] = None,
    margin_pct: float = 0.06,
) -> PreprocessingPipelineResult:
    """
    Complete end-to-end first-stage computer vision preprocessing pipeline.
    Implements Evidence-Safe Boundary Expansion (Section 3 & 5).
    """
    t0 = time.perf_counter()
    orig_h, orig_w = img_bgr.shape[:2]
    orig_bytes = len(cv2.imencode(".jpg", img_bgr)[1])

    # Stage 1: Original
    s01_original = img_bgr.copy()

    # Stage 2: Boundary Detection
    bound_res = detect_package_boundary(s01_original)
    detected = bound_res.get("detected", False)
    conf = bound_res.get("confidence", 0.0)
    method = bound_res.get("method", "NONE")
    phys_corners = bound_res.get("corners", [])

    # EVIDENCE-SAFE BOUNDARY EXPANSION (Section 3)
    safe_corners: List[List[float]] = []
    if detected and len(phys_corners) == 4:
        safe_corners = expand_boundary_corners(phys_corners, (orig_h, orig_w), margin_pct=margin_pct)
        evidence_safe_used = True
    else:
        evidence_safe_used = False

    # Stage 02: Dual-Boundary Debug Image (Section 5)
    s02_boundary = draw_boundary_debug(s01_original, phys_corners, safe_corners)

    # Stage 3: Perspective Correction & Stage 4: Crop
    fwd_homography = np.eye(3, dtype=np.float64)
    fallback_used = False
    failure_reason = None

    corners_to_use = safe_corners if (safe_corners and len(safe_corners) == 4) else phys_corners

    if detected and conf >= 0.50 and len(corners_to_use) == 4:
        s03_perspective, fwd_h_mat, inv_h_mat = rectify_perspective(s01_original, corners_to_use)
        fwd_homography = fwd_h_mat
        perspective_corrected = True
        s04_crop = s03_perspective.copy()
    else:
        perspective_corrected = False
        fallback_used = True
        failure_reason = "Boundary confidence low or corners invalid; using full original frame crop."
        s03_perspective = s01_original.copy()
        s04_crop = s01_original.copy()

    # Stage 5: Adobe-Scan-like background normalization
    s05_bg_norm = normalize_background(s04_crop)

    # Stage 6: Glare Reduction
    s06_glare, glare_detected = reduce_glare(s05_bg_norm)

    # Stage 7: Uneven Illumination Correction
    s07_illum = correct_illumination(s06_glare)

    # Stage 8: Text-Preserving Enhancement
    s08_enhanced = enhance_text_declarations(s07_illum)

    # Stage 9: Final Resize & Encode
    s09_final, sx, sy = resize_and_encode_final(s08_enhanced, max_dim=1024, jpeg_quality=85)
    final_h, final_w = s09_final.shape[:2]
    final_bytes = len(cv2.imencode(".jpg", s09_final, [cv2.IMWRITE_JPEG_QUALITY, 85])[1])

    # Composite Homography Coordinate Transformation (Original -> Final)
    scale_mat = np.array([
        [sx, 0.0, 0.0],
        [0.0, sy, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)

    comp_fwd = scale_mat @ fwd_homography
    comp_inv = np.linalg.inv(comp_fwd)

    fwd_transform = CoordinateTransform(
        source_space=CoordinateSpace.ORIGINAL_PIXEL,
        target_space=CoordinateSpace.CANONICAL_PIXEL,
        matrix=comp_fwd.tolist(),
        matrix_direction="FORWARD",
        source_dims=(orig_w, orig_h),
        target_dims=(final_w, final_h),
    )
    inv_transform = fwd_transform.invert()

    total_cv_time_ms = round((time.perf_counter() - t0) * 1000, 1)

    # Exact Schema as specified in Section 8
    metadata = {
        "product": product,
        "face": face,
        "original_dimensions": [orig_w, orig_h],
        "original_file_size_bytes": orig_bytes,

        "boundary_detected": bool(detected),
        "boundary_method": method,
        "physical_boundary_confidence": round(float(conf), 3),

        "evidence_safe_boundary_used": bool(evidence_safe_used),
        "boundary_margin_percent": round(margin_pct * 100.0, 1) if evidence_safe_used else 0.0,

        "perspective_corrected": bool(perspective_corrected),
        "background_normalized": True,
        "glare_detected": bool(glare_detected),
        "glare_reduced": bool(glare_detected),
        "illumination_corrected": True,
        "text_enhanced": True,

        "final_dimensions": [final_w, final_h],
        "final_file_size_bytes": final_bytes,

        "fallback_used": bool(fallback_used),
        "failure_reason": failure_reason,

        "preprocessing_latency_ms": total_cv_time_ms,
        "physical_corners": phys_corners,
        "evidence_safe_corners": safe_corners,
    }

    # Save debug stages if debug directory is requested
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_dir / "01_original.jpg"), s01_original)
        cv2.imwrite(str(debug_dir / "02_boundary_detected.jpg"), s02_boundary)
        cv2.imwrite(str(debug_dir / "03_perspective.jpg"), s03_perspective)
        cv2.imwrite(str(debug_dir / "04_crop.jpg"), s04_crop)
        cv2.imwrite(str(debug_dir / "05_background_normalized.jpg"), s05_bg_norm)
        cv2.imwrite(str(debug_dir / "06_glare_reduced.jpg"), s06_glare)
        cv2.imwrite(str(debug_dir / "07_illumination_corrected.jpg"), s07_illum)
        cv2.imwrite(str(debug_dir / "08_text_enhanced.jpg"), s08_enhanced)
        cv2.imwrite(
            str(debug_dir / "09_final.jpg"),
            s09_final,
            [cv2.IMWRITE_JPEG_QUALITY, 85],
        )
        with open(debug_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

    return PreprocessingPipelineResult(
        original_bgr=s01_original,
        boundary_detected_bgr=s02_boundary,
        perspective_bgr=s03_perspective,
        cropped_bgr=s04_crop,
        background_normalized_bgr=s05_bg_norm,
        glare_reduced_bgr=s06_glare,
        illumination_corrected_bgr=s07_illum,
        text_enhanced_bgr=s08_enhanced,
        final_bgr=s09_final,
        metadata=metadata,
        forward_transform=fwd_transform,
        inverse_transform=inv_transform,
        physical_corners=phys_corners,
        evidence_safe_corners=safe_corners,
    )


def preprocess_three_faces_parallel(
    faces_input: Sequence[Tuple[str, np.ndarray, str, Optional[Path]]],
    product: str = "PACKAGE",
    margin_pct: float = 0.06,
    max_workers: int = 3,
) -> Dict[str, PreprocessingPipelineResult]:
    """
    Parallel 3-Face Preprocessing Pipeline using ThreadPoolExecutor(max_workers=3).
    
    Processes package faces concurrently while strictly preserving:
    1. Face identity stability (Face 1 -> Face 1, Face 2 -> Face 2, Face 3 -> Face 3)
    2. Deterministic output dictionary key ordering
    3. Isolated debug output directories and metadata files
    4. Individual homography CoordinateTransform per face
    5. No cross-worker data race or file collision
    """
    t_start = time.perf_counter()
    face_order = [item[0] for item in faces_input]

    def _worker(item: Tuple[str, np.ndarray, str, Optional[Path]]) -> Tuple[str, PreprocessingPipelineResult]:
        face_name, img_bgr, src_name, dbg_dir = item
        res = run_preprocessing_pipeline(
            img_bgr=img_bgr,
            source_name=src_name,
            product=product,
            face=face_name,
            debug_dir=dbg_dir,
            margin_pct=margin_pct,
        )
        return face_name, res

    workers = min(max_workers, max(1, len(faces_input)))
    worker_results: Dict[str, PreprocessingPipelineResult] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(_worker, item): item[0] for item in faces_input}
        for future in concurrent.futures.as_completed(future_map):
            face_name, res = future.result()
            worker_results[face_name] = res

    # Strictly assemble in original face order
    results: Dict[str, PreprocessingPipelineResult] = {}
    for face_name in face_order:
        results[face_name] = worker_results[face_name]

    total_parallel_ms = round((time.perf_counter() - t_start) * 1000, 1)
    logger.info("Parallel preprocessing finished: %d faces in %.1f ms", len(faces_input), total_parallel_ms)
    return results
