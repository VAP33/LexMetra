"""
Sticker / alteration detection baseline.

This module is intentionally a classical-CV REVIEW FLAG, not a legal decision
and not a calibrated probability model.

Purpose:
- identify image regions that may be affixed stickers, overprints, or altered
  declaration panels;
- return conservative candidate regions for human review;
- never convert a sticker suspicion into PASS/FAIL by itself.

Design constraints:
- zero training data required;
- robust to small images and ordinary camera noise;
- avoids treating every rectangular graphic as a sticker;
- caps the number of returned candidates;
- exposes heuristic confidence only as a ranking score, never as a probability.

Upgrade path:
When paired original/altered images are available, replace the internal
candidate scoring with a trained detector/classifier while preserving
detect_sticker_regions() and SuspectRegion for downstream compatibility.
"""

from dataclasses import dataclass, field
from typing import List, Tuple

import cv2
import numpy as np


BBox = Tuple[int, int, int, int]


@dataclass
class SuspectRegion:
    bbox: BBox
    reason: str
    confidence: float
    signals: dict = field(default_factory=dict)


def _iou(a: BBox, b: BBox) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b

    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)

    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    intersection = iw * ih

    union = aw * ah + bw * bh - intersection
    return float(intersection / union) if union > 0 else 0.0


def _clip_bbox(bbox: BBox, width: int, height: int) -> BBox:
    x, y, w, h = bbox
    x = max(0, min(int(x), width - 1))
    y = max(0, min(int(y), height - 1))
    x2 = max(x + 1, min(int(x + w), width))
    y2 = max(y + 1, min(int(y + h), height))
    return x, y, x2 - x, y2 - y


def _edge_discontinuity_score(
    gray: np.ndarray,
    bbox: BBox,
    margin: int = 6,
) -> float:
    """
    Compare the candidate interior with a thin surrounding ring.

    The score is a raw intensity-statistics difference, not a probability.
    """
    x, y, w, h = bbox
    height, width = gray.shape[:2]

    if w < 3 or h < 3:
        return 0.0

    x0 = max(0, x - margin)
    y0 = max(0, y - margin)
    x1 = min(width, x + w + margin)
    y1 = min(height, y + h + margin)

    outer = gray[y0:y1, x0:x1]
    inside = gray[y:y + h, x:x + w]

    if inside.size == 0 or outer.size == 0:
        return 0.0

    mask = np.ones(outer.shape, dtype=bool)
    iy0 = y - y0
    ix0 = x - x0
    mask[iy0:iy0 + h, ix0:ix0 + w] = False

    ring = outer[mask]
    if ring.size < 8:
        return 0.0

    # Mean alone is too sensitive to illumination. Combine robust mean and
    # standard-deviation differences, then normalize to a compact range.
    mean_diff = abs(float(np.mean(inside)) - float(np.mean(ring))) / 255.0
    std_diff = abs(float(np.std(inside)) - float(np.std(ring))) / 128.0

    return float(np.clip(0.7 * mean_diff + 0.3 * std_diff, 0.0, 1.0))


def _border_edge_strength(
    gray: np.ndarray,
    bbox: BBox,
    border: int = 3,
) -> float:
    """Estimate whether a thin border around the region contains strong edges."""
    x, y, w, h = bbox
    if w < 2 * border + 2 or h < 2 * border + 2:
        return 0.0

    crop = gray[y:y + h, x:x + w]
    if crop.size == 0:
        return 0.0

    edges = cv2.Canny(crop, 50, 150)

    b = min(border, max(1, min(w, h) // 8))
    border_mask = np.zeros(edges.shape, dtype=np.uint8)
    border_mask[:b, :] = 1
    border_mask[-b:, :] = 1
    border_mask[:, :b] = 1
    border_mask[:, -b:] = 1

    border_pixels = edges[border_mask > 0]
    interior_pixels = edges[border_mask == 0]

    if border_pixels.size == 0:
        return 0.0

    border_density = float(np.mean(border_pixels > 0))

    # Compare against the interior so textured artwork is less likely to be
    # mistaken for a crisp sticker boundary.
    interior_density = (
        float(np.mean(interior_pixels > 0))
        if interior_pixels.size
        else border_density
    )

    relative = border_density - interior_density
    return float(np.clip(relative * 4.0, 0.0, 1.0))


def _texture_difference(
    gray: np.ndarray,
    bbox: BBox,
    margin: int = 8,
) -> float:
    """Compare local gradient/texture statistics inside vs. around a candidate."""
    x, y, w, h = bbox
    height, width = gray.shape[:2]

    x0 = max(0, x - margin)
    y0 = max(0, y - margin)
    x1 = min(width, x + w + margin)
    y1 = min(height, y + h + margin)

    outer = gray[y0:y1, x0:x1]
    inside = gray[y:y + h, x:x + w]

    if inside.size < 16 or outer.size < 16:
        return 0.0

    gx_i = cv2.Sobel(inside, cv2.CV_32F, 1, 0, ksize=3)
    gy_i = cv2.Sobel(inside, cv2.CV_32F, 0, 1, ksize=3)
    grad_i = cv2.magnitude(gx_i, gy_i)

    gx_o = cv2.Sobel(outer, cv2.CV_32F, 1, 0, ksize=3)
    gy_o = cv2.Sobel(outer, cv2.CV_32F, 0, 1, ksize=3)
    grad_o = cv2.magnitude(gx_o, gy_o)

    inside_mean = float(np.mean(grad_i))
    outer_mean = float(np.mean(grad_o))

    denom = max(inside_mean + outer_mean, 1e-6)
    return float(np.clip(abs(inside_mean - outer_mean) / denom, 0.0, 1.0))


def _sharpness_ratio(gray: np.ndarray, bbox: BBox, margin: int = 10) -> float:
    """
    Return candidate sharpness / surrounding sharpness.

    This is deliberately capped because tiny noisy regions can otherwise
    produce enormous ratios.
    """
    x, y, w, h = bbox
    height, width = gray.shape[:2]

    region = gray[y:y + h, x:x + w]
    if region.size < 16:
        return 1.0

    x0 = max(0, x - margin)
    y0 = max(0, y - margin)
    x1 = min(width, x + w + margin)
    y1 = min(height, y + h + margin)

    context = gray[y0:y1, x0:x1]
    if context.size < 16:
        return 1.0

    region_var = float(cv2.Laplacian(region, cv2.CV_64F).var())
    context_var = float(cv2.Laplacian(context, cv2.CV_64F).var())

    return float(np.clip((region_var + 1e-3) / (context_var + 1e-3), 0.1, 10.0))


def _rectangularity(contour: np.ndarray) -> float:
    """Contour area divided by its bounding-box area."""
    x, y, w, h = cv2.boundingRect(contour)
    box_area = w * h
    if box_area <= 0:
        return 0.0
    return float(np.clip(cv2.contourArea(contour) / box_area, 0.0, 1.0))


def _aspect_plausibility(w: int, h: int) -> float:
    """
    Mild prior against extremely thin/elongated rectangles.

    This is not a legal assumption. It only prevents the edge detector from
    flooding the review queue with package artwork and text lines.
    """
    if min(w, h) <= 0:
        return 0.0

    ratio = max(w / h, h / w)
    if ratio <= 8:
        return 1.0
    if ratio >= 20:
        return 0.0
    return float((20.0 - ratio) / 12.0)


def _candidate_score(
    gray: np.ndarray,
    bbox: BBox,
    rectangularity: float,
) -> Tuple[float, dict]:
    edge = _edge_discontinuity_score(gray, bbox)
    border = _border_edge_strength(gray, bbox)
    texture = _texture_difference(gray, bbox)
    sharp_ratio = _sharpness_ratio(gray, bbox)

    # Sharpness mismatch is symmetric: both much sharper and much softer
    # than the surrounding print are potentially suspicious.
    log_ratio = abs(float(np.log(max(sharp_ratio, 1e-6))))
    sharp_mismatch = float(np.clip(log_ratio / np.log(4.0), 0.0, 1.0))

    aspect = _aspect_plausibility(bbox[2], bbox[3])

    # Conservative weighted score. No component is enough to trigger a legal
    # finding by itself.
    score = (
        0.34 * edge
        + 0.28 * border
        + 0.18 * texture
        + 0.12 * sharp_mismatch
        + 0.08 * rectangularity
    )

    # Strongly implausible shapes are retained only when other signals are
    # unusually strong.
    score *= 0.55 + 0.45 * aspect

    signals = {
        "edge_discontinuity": round(edge, 4),
        "border_edge_strength": round(border, 4),
        "texture_difference": round(texture, 4),
        "sharpness_ratio": round(sharp_ratio, 4),
        "sharpness_mismatch": round(sharp_mismatch, 4),
        "rectangularity": round(rectangularity, 4),
        "aspect_plausibility": round(aspect, 4),
    }
    return float(np.clip(score, 0.0, 1.0)), signals


def detect_sticker_regions(
    image_bgr: np.ndarray,
    min_area_frac: float = 0.005,
    max_area_frac: float = 0.35,
    max_candidates: int = 8,
) -> List[SuspectRegion]:
    """
    Detect candidate sticker/alteration regions.

    Parameters
    ----------
    image_bgr:
        OpenCV BGR image.
    min_area_frac:
        Minimum candidate area as a fraction of image area.
    max_area_frac:
        Maximum candidate area as a fraction of image area.
    max_candidates:
        Maximum number of review flags returned.

    Returns
    -------
    List[SuspectRegion]
        Ranked candidate regions. Empty list means no candidate crossed the
        heuristic threshold, not proof that the package is unaltered.
    """
    if image_bgr is None or not isinstance(image_bgr, np.ndarray):
        return []

    if image_bgr.ndim not in (2, 3):
        return []

    if image_bgr.size == 0:
        return []

    if image_bgr.ndim == 2:
        gray = image_bgr
    elif image_bgr.shape[2] == 3:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    elif image_bgr.shape[2] == 4:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGRA2GRAY)
    else:
        return []

    height, width = gray.shape[:2]
    image_area = height * width

    if image_area < 256:
        return []

    min_area_frac = float(np.clip(min_area_frac, 0.0001, 0.25))
    max_area_frac = float(np.clip(max_area_frac, min_area_frac + 1e-4, 0.95))
    max_candidates = max(1, int(max_candidates))

    # Light denoising reduces camera noise without erasing medium-scale seams.
    smooth = cv2.GaussianBlur(gray, (5, 5), 0)

    # Use two edge scales. The first catches ordinary sticker boundaries;
    # the second helps with weaker boundaries on low-contrast packaging.
    edge_a = cv2.Canny(smooth, 45, 135)
    edge_b = cv2.Canny(smooth, 25, 90)
    edges = cv2.bitwise_or(edge_a, edge_b)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(
        edges,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    candidates: List[SuspectRegion] = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        frac = area / image_area

        if frac < min_area_frac or frac > max_area_frac:
            continue

        if w < 12 or h < 12:
            continue

        rectangularity = _rectangularity(contour)

        # Keep candidates that are plausibly rectangular, but allow some
        # perspective/rounded-corner distortion.
        if rectangularity < 0.35:
            continue

        bbox = _clip_bbox((x, y, w, h), width, height)
        score, signals = _candidate_score(gray, bbox, rectangularity)

        # Require at least two meaningful visual signals, rather than allowing
        # a single strong edge to create a review flag.
        meaningful_signals = sum(
            [
                signals["edge_discontinuity"] >= 0.08,
                signals["border_edge_strength"] >= 0.08,
                signals["texture_difference"] >= 0.12,
                signals["sharpness_mismatch"] >= 0.25,
            ]
        )

        if meaningful_signals < 2 or score < 0.18:
            continue

        reason_parts = []

        if signals["edge_discontinuity"] >= 0.08:
            reason_parts.append(
                f"local boundary/statistics discontinuity "
                f"{signals['edge_discontinuity']:.2f}"
            )

        if signals["border_edge_strength"] >= 0.08:
            reason_parts.append(
                f"border-edge strength {signals['border_edge_strength']:.2f}"
            )

        if signals["texture_difference"] >= 0.12:
            reason_parts.append(
                f"texture difference {signals['texture_difference']:.2f}"
            )

        if signals["sharpness_mismatch"] >= 0.25:
            reason_parts.append(
                f"print-sharpness ratio {signals['sharpness_ratio']:.2f}"
            )

        candidates.append(
            SuspectRegion(
                bbox=bbox,
                reason="; ".join(reason_parts),
                confidence=round(score, 4),
                signals=signals,
            )
        )

    # Highest score first, then suppress overlapping duplicates.
    candidates.sort(key=lambda item: item.confidence, reverse=True)

    kept: List[SuspectRegion] = []
    for candidate in candidates:
        if any(_iou(candidate.bbox, existing.bbox) > 0.4 for existing in kept):
            continue
        kept.append(candidate)
        if len(kept) >= max_candidates:
            break

    return kept
