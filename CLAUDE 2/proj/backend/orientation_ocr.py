"""
Per-text-region orientation-aware OCR (master spec: mixed horizontal/vertical
packaging text, e.g. a label printed sideways to save space next to normal
horizontal text - the Vaseline body-lotion photo in dataset/real_photos is
the motivating, real-world regression fixture for this module).

Architecture (as required - NOT whole-image rotation):

    image
      -> detect_text_blocks()      classical CV, two directional
                                    morphological merges (horizontal text
                                    lines vs. vertical text columns)
      -> per block: estimate_block_orientation()   Tesseract OSD, with an
                                    aspect-ratio fallback when OSD is not
                                    confident (common on small crops)
      -> rotate ONLY that block's crop to canonical (upright) orientation
      -> OCR the rotated crop
      -> map every resulting line bbox back into ORIGINAL image coordinates
         (both the pre-rotation block bbox and the corrected orientation are
         preserved on every OrientedOcrLine - nothing is discarded)

This is a practical, classical-CV MVP, not a trained text detector. It will
not find every block perfectly (very tightly packed dense text can still
merge blocks together) - see the benchmark results in IMPLEMENTATION_STATUS.md
for measured behaviour on the real photo set, not a claim of general
solved-ness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pytesseract
from PIL import Image

from ocr_extraction import OcrLine, _ocr_single

MIN_BLOCK_AREA_PX = 400
MIN_BLOCK_DIM_PX = 12


@dataclass
class OrientedOcrLine:
    text: str
    bbox: Tuple[int, int, int, int]          # in ORIGINAL image coordinates
    confidence: float
    orientation_degrees: int                  # 0, 90, 180, or 270
    source_block_bbox: Tuple[int, int, int, int]  # original-image coords
    engine: str = "tesseract"

    def as_ocr_line(self) -> OcrLine:
        """Interop with the existing (orientation-blind) OcrLine consumers."""
        return OcrLine(text=self.text, bbox=self.bbox, confidence=self.confidence)


def _binarize(gray: np.ndarray) -> np.ndarray:
    # Text is usually darker or lighter than a fairly uniform packaging
    # background; Otsu handles both light-on-dark and dark-on-light print.
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return binary


def _merge_boxes_along_axis(binary: np.ndarray, kernel_size: Tuple[int, int]) -> List[Tuple[int, int, int, int]]:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, kernel_size)
    merged = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    merged = cv2.dilate(merged, kernel, iterations=1)
    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < MIN_BLOCK_AREA_PX or w < MIN_BLOCK_DIM_PX or h < MIN_BLOCK_DIM_PX:
            continue
        boxes.append((x, y, w, h))
    return boxes


def _iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2, bx2, by2 = ax + aw, ay + ah, bx + bw, by + bh
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def detect_text_blocks(img_bgr: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """
    Find candidate text-bearing regions using two directional morphological
    merges - a WIDE-horizontal kernel to group horizontal text into line/
    paragraph blocks, and a TALL-vertical kernel to group vertical (rotated)
    text columns into blocks. Running both and taking the union is what lets
    this see a sideways label next to normal horizontal text, instead of
    forcing one global reading direction.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    binary = _binarize(gray)

    h, w = gray.shape[:2]
    horiz_kernel = (max(15, w // 40), 3)
    vert_kernel = (3, max(15, h // 40))

    horizontal_boxes = _merge_boxes_along_axis(binary, horiz_kernel)
    vertical_boxes = _merge_boxes_along_axis(binary, vert_kernel)

    all_boxes = horizontal_boxes + vertical_boxes
    # De-duplicate near-identical boxes found by both passes.
    kept: List[Tuple[int, int, int, int]] = []
    for box in sorted(all_boxes, key=lambda b: b[2] * b[3], reverse=True):
        if all(_iou(box, k) < 0.6 for k in kept):
            kept.append(box)

    # Reject accidental whole-image-sized "blocks" (morphological merge
    # occasionally connects everything on busy/dense labels). Those add no
    # regional benefit over the existing whole-image OCR pass and just waste
    # time re-OCRing the entire photo.
    image_area = h * w
    kept = [b for b in kept if (b[2] * b[3]) < 0.7 * image_area]
    return kept


def estimate_block_orientation(crop_bgr: np.ndarray) -> Tuple[int, bool]:
    """
    Returns (angle, osd_confident) where angle is one of 0, 90, 180, 270 -
    the rotation needed to make this crop's text upright.

    Uses Tesseract's orientation-and-script-detection (OSD) when it reports
    a confident result. When OSD is not confident (common on small/short
    crops with little text), this returns 90 as a starting guess but flags
    osd_confident=False so the caller can disambiguate 90-vs-270 by actually
    trying both and keeping whichever produces better OCR (see
    _ocr_best_of_two_orientations) - a fixed heuristic guess cannot tell
    "rotated clockwise" from "rotated counter-clockwise" on its own, and
    guessing wrong silently would mirror/reverse the text.
    """
    try:
        osd = pytesseract.image_to_osd(crop_bgr, output_type=pytesseract.Output.DICT)
        angle = int(osd.get("rotate", 0)) % 360
        conf = float(osd.get("orientation_conf", 0.0) or 0.0)
        if conf >= 1.0 and angle in (0, 90, 180, 270):
            return angle, True
    except Exception:
        pass

    h, w = crop_bgr.shape[:2]
    if h > w * 1.8:
        return 90, False
    return 0, True


def _rotate(crop_bgr: np.ndarray, angle: int) -> np.ndarray:
    if angle == 0:
        return crop_bgr
    if angle == 90:
        return cv2.rotate(crop_bgr, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(crop_bgr, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(crop_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return crop_bgr


def _map_bbox_to_original(
    local_bbox: Tuple[int, int, int, int],
    angle: int,
    rotated_size: Tuple[int, int],
    block_origin: Tuple[int, int],
) -> Tuple[int, int, int, int]:
    """
    local_bbox is in the ROTATED crop's coordinate system. Undo the rotation
    to get back to the ORIGINAL (unrotated) crop's coordinate system, then
    add the block's offset within the full original image.
    """
    x, y, w, h = local_bbox
    rw, rh = rotated_size  # rotated crop's (width, height)
    ox, oy = block_origin

    if angle == 0:
        ux, uy, uw, uh = x, y, w, h
    elif angle == 90:
        # rotated = ROTATE_90_CLOCKWISE(original); invert it.
        ux, uy, uw, uh = y, rw - (x + w), h, w
    elif angle == 180:
        ux, uy, uw, uh = rw - (x + w), rh - (y + h), w, h
    elif angle == 270:
        ux, uy, uw, uh = rh - (y + h), x, h, w
    else:
        ux, uy, uw, uh = x, y, w, h

    return (ox + ux, oy + uy, uw, uh)


def _score_lines(lines: List[OcrLine]) -> float:
    """Simple, cheap proxy for "did this rotation produce real text": total
    confidence-weighted alphanumeric character count. Garbage OCR from the
    wrong rotation tends to produce short, low-confidence, punctuation-heavy
    fragments; correct-orientation text produces longer, higher-confidence
    words."""
    score = 0.0
    for line in lines:
        alnum_chars = sum(1 for ch in line.text if ch.isalnum())
        score += alnum_chars * line.confidence
    return score


def _ocr_best_of_two_orientations(crop_bgr: np.ndarray) -> Tuple[int, List[OcrLine], np.ndarray]:
    """
    When OSD couldn't confidently tell us the rotation direction for a
    tall/narrow (likely-vertical-text) block, try BOTH 90 and 270 and keep
    whichever actually reads better, instead of guessing one fixed direction
    and risking mirrored/reversed text.
    """
    best_angle, best_lines, best_rotated, best_score = 90, [], _rotate(crop_bgr, 90), -1.0
    for angle in (90, 270):
        rotated = _rotate(crop_bgr, angle)
        try:
            pil_rotated = Image.fromarray(cv2.cvtColor(rotated, cv2.COLOR_BGR2RGB))
            lines = _ocr_single(pil_rotated, psm=6) or _ocr_single(pil_rotated, psm=11)
        except Exception:
            lines = []
        score = _score_lines(lines)
        if score > best_score:
            best_angle, best_lines, best_rotated, best_score = angle, lines, rotated, score
    return best_angle, best_lines, best_rotated


def run_orientation_aware_ocr(image: Image.Image) -> List[OrientedOcrLine]:
    """
    Detect text blocks, determine each block's orientation independently,
    OCR each block in its own canonical orientation, and map every resulting
    line back to the ORIGINAL image's coordinate system.

    Falls back to nothing (empty list) on any per-block failure rather than
    raising - callers should treat this as an additional evidence source
    layered on top of (not a replacement for) run_ocr()'s whole-image pass,
    since block detection can miss regions that whole-image OCR still reads
    fine (e.g. a single big horizontal paragraph).
    """
    rgb = image.convert("RGB")
    img_bgr = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)

    blocks = detect_text_blocks(img_bgr)
    results: List[OrientedOcrLine] = []

    for (bx, by, bw, bh) in blocks:
        crop = img_bgr[by: by + bh, bx: bx + bw]
        if crop.size == 0:
            continue

        try:
            angle, osd_confident = estimate_block_orientation(crop)
            if angle in (90, 270) and not osd_confident:
                angle, local_lines, rotated = _ocr_best_of_two_orientations(crop)
            else:
                rotated = _rotate(crop, angle)
                pil_rotated = Image.fromarray(cv2.cvtColor(rotated, cv2.COLOR_BGR2RGB))
                local_lines = _ocr_single(pil_rotated, psm=6)
                if not local_lines:
                    local_lines = _ocr_single(pil_rotated, psm=11)
            rh, rw = rotated.shape[:2]
        except Exception:
            continue

        for line in local_lines:
            try:
                mapped_bbox = _map_bbox_to_original(
                    line.bbox, angle, (rw, rh), (bx, by),
                )
            except Exception:
                continue

            confidence = line.confidence
            results.append(
                OrientedOcrLine(
                    text=line.text,
                    bbox=mapped_bbox,
                    confidence=confidence,
                    orientation_degrees=angle,
                    source_block_bbox=(bx, by, bw, bh),
                )
            )

    return results
