"""
Test harness for the new First-Stage Computer Vision / Preprocessing Pipeline.
Implements the full OpenCV pipeline:
1. Package boundary detection
2. Perspective correction
3. Tight package crop
4. Adobe-Scan-like background normalization
5. Glare reduction
6. Uneven illumination correction
7. Text-preserving enhancement
8. Resize / encode
9. Metadata generation
10. Single-image Qwen3.8-27B test via OpenRouter with reasoning: {"effort": "none"}
"""

import os
import sys
import json
import time
import base64
from pathlib import Path

import cv2
import httpx
import numpy as np
from dotenv import load_dotenv

# Reconfigure utf-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).resolve().parent.parent.parent
env_path = project_root / "backend" / ".env"
load_dotenv(dotenv_path=env_path)


def detect_package_boundary(img_bgr: np.ndarray) -> dict:
    """
    OpenCV package boundary detector.
    Returns:
    {
        "detected": bool,
        "corners": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]],
        "confidence": float
    }
    """
    orig_h, orig_w = img_bgr.shape[:2]
    target_dim = 1024
    scale = target_dim / max(orig_h, orig_w)
    sw, sh = int(round(orig_w * scale)), int(round(orig_h * scale))
    small = cv2.resize(img_bgr, (sw, sh), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    # 1. Bilateral filtering to preserve structural package edges while suppressing text texture
    filtered = cv2.bilateralFilter(gray, 9, 75, 75)

    # 2. Compute gradient magnitude
    grad_x = cv2.Sobel(filtered, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(filtered, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(grad_x, grad_y)
    mag = np.uint8(np.clip(mag / max(1e-5, mag.max()) * 255.0, 0, 255))

    # 3. Morphological closing to bridge small gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(mag, cv2.MORPH_CLOSE, kernel)

    # 4. Multi-threshold edge lines
    edges = cv2.Canny(closed, 40, 120)
    min_len = int(sh * 0.04)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=45, minLineLength=min_len, maxLineGap=int(sh * 0.02))

    v_lines = []
    h_lines = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx = x2 - x1
            dy = y2 - y1
            length = float(np.hypot(dx, dy))
            angle = float(np.abs(np.arctan2(dy, dx) * 180.0 / np.pi))
            if 70.0 <= angle <= 110.0:
                v_lines.append((x1, y1, x2, y2, length))
            elif angle <= 20.0 or angle >= 160.0:
                h_lines.append((x1, y1, x2, y2, length))

    # Fallback to contour convex hull if insufficient lines
    if len(v_lines) < 2 or len(h_lines) < 2:
        # Contour-based boundary detection
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        cnts, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        valid_cnts = [c for c in cnts if cv2.contourArea(c) > (sw * sh * 0.15)]
        if valid_cnts:
            best_c = max(valid_cnts, key=cv2.contourArea)
            hull = cv2.convexHull(best_c)
            peri = cv2.arcLength(hull, True)
            for eps_ratio in [0.02, 0.03, 0.04, 0.05, 0.06]:
                approx = cv2.approxPolyDP(hull, eps_ratio * peri, True)
                if len(approx) == 4 and cv2.isContourConvex(approx):
                    pts = approx.reshape(4, 2)
                    orig_pts = (pts / scale).tolist()
                    return {
                        "detected": True,
                        "corners": [[round(p[0], 1), round(p[1], 1)] for p in orig_pts],
                        "confidence": 0.75,
                    }

    # If we have line candidates, find outermost structural package boundaries
    left_cands = [l for l in v_lines if (l[0] + l[2]) / 2.0 < sw * 0.48]
    right_cands = [l for l in v_lines if (l[0] + l[2]) / 2.0 > sw * 0.52]
    top_cands = [l for l in h_lines if (l[1] + l[3]) / 2.0 < sh * 0.40]
    bot_cands = [l for l in h_lines if (l[1] + l[3]) / 2.0 > sh * 0.60]

    if left_cands and right_cands and top_cands and bot_cands:
        # Outermost lines with good length
        max_left_len = max(l[4] for l in left_cands)
        strong_left = [l for l in left_cands if l[4] >= max_left_len * 0.20]
        best_left = min(strong_left, key=lambda l: min(l[0], l[2]))

        max_right_len = max(l[4] for l in right_cands)
        strong_right = [l for l in right_cands if l[4] >= max_right_len * 0.20]
        best_right = max(strong_right, key=lambda l: max(l[0], l[2]))

        max_top_len = max(l[4] for l in top_cands)
        strong_top = [l for l in top_cands if l[4] >= max_top_len * 0.20]
        best_top = min(strong_top, key=lambda l: min(l[1], l[3]))

        max_bot_len = max(l[4] for l in bot_cands)
        strong_bot = [l for l in bot_cands if l[4] >= max_bot_len * 0.20]
        best_bot = max(strong_bot, key=lambda l: max(l[1], l[3]))

        def line_params(l):
            x1, y1, x2, y2 = l[:4]
            A = y2 - y1
            B = x1 - x2
            C = A * x1 + B * y1
            return A, B, C

        def intersect(l1, l2):
            A1, B1, C1 = line_params(l1)
            A2, B2, C2 = line_params(l2)
            det = A1 * B2 - A2 * B1
            if abs(det) < 1e-6:
                return None
            return [float((B2 * C1 - B1 * C2) / det), float((A1 * C2 - A2 * C1) / det)]

        tl = intersect(best_left, best_top)
        tr = intersect(best_right, best_top)
        br = intersect(best_right, best_bot)
        bl = intersect(best_left, best_bot)

        if all(p is not None for p in [tl, tr, br, bl]):
            pts_small = np.array([tl, tr, br, bl], dtype=np.float32)
            quad_area = float(cv2.contourArea(pts_small))
            area_frac = quad_area / float(sw * sh)
            if 0.15 <= area_frac <= 0.95:
                orig_pts = (pts_small / scale).tolist()
                return {
                    "detected": True,
                    "corners": [[round(p[0], 1), round(p[1], 1)] for p in orig_pts],
                    "confidence": 0.88,
                }

    # Safe fallback: estimate package region from central gradient envelope
    # with 5% safety margin
    row_grads = mag.mean(axis=1)
    col_grads = mag.mean(axis=0)
    thresh_row = np.percentile(row_grads, 25)
    thresh_col = np.percentile(col_grads, 25)

    y_indices = np.where(row_grads > thresh_row)[0]
    x_indices = np.where(col_grads > thresh_col)[0]
    if len(y_indices) > 0 and len(x_indices) > 0:
        x0, x1 = int(x_indices[0]), int(x_indices[-1])
        y0, y1 = int(y_indices[0]), int(y_indices[-1])
        # Add safety margin
        pad_x = int((x1 - x0) * 0.05)
        pad_y = int((y1 - y0) * 0.05)
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
            "confidence": 0.65,
        }

    return {"detected": False, "corners": [], "confidence": 0.0}
