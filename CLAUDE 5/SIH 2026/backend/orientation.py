"""
Per-region text orientation estimation and local rotation.

WHY THIS MODULE EXISTS
----------------------
Real packages carry text at more than one orientation in a SINGLE photograph.
The mandatory real-photo case is a cylindrical body label: the brand name runs
horizontally across the front while the statutory declarations run vertically up
the side of the same label, packed densely together. Rotating the whole image to
"fix" the vertical text destroys the horizontal text, and vice versa. So:

    Never rotate the entire image as the primary solution.

Instead the pipeline is:

    IMAGE
      -> TEXT REGIONS            (region_detection.py)
      -> PER-REGION ORIENTATION  (this module)
      -> LOCAL ROTATION          (this module)
      -> PREPROCESSING           (preprocess.py)
      -> OCR                     (ocr_engine.py)
      -> MAP COORDINATES BACK    (this module)
      -> EVIDENCE

LEGAL SAFETY
------------
1. An orientation estimate is a ROUTING HINT for the OCR engine. It is never
   evidence about the package and never contributes to a legal finding.
2. AMBIGUOUS is a first-class answer. When the geometry does not clearly favour
   one axis, this module says so and asks the caller to TRY BOTH rather than
   silently committing to a guess. Silently choosing is the failure mode that
   turns a readable declaration into an apparent absence.
3. Failing to read a region at any orientation means NOT_OBSERVED, never
   MISSING. This module cannot and does not distinguish "the text is not there"
   from "we could not orient it".
4. Rotation is lossless. `rotate_crop()` uses exact 90-degree transposes, never
   interpolating warps, so no pixel evidence is invented or smeared. The source
   array is never modified.

GEOMETRY VS. FLIP
-----------------
Projection/morphology geometry can determine the AXIS of the text (horizontal
vs vertical) but it fundamentally cannot distinguish 0 from 180, nor 90 from
270 — upside-down text has exactly the same ink layout. That distinction is
only recoverable by actually attempting to read the glyphs. This module is
honest about that split: it returns an ordered CANDIDATE LIST, and the flip is
resolved by the OCR trial in `ocr_engine.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

BBoxT = Tuple[int, int, int, int]


class Orientation(int, Enum):
    """
    Clockwise rotation, in degrees, that must be applied to the region crop to
    bring its text upright.

    `DEG_90` means: the text currently reads bottom-to-top in the crop, and
    rotating the crop 90 degrees clockwise makes it read left-to-right.
    """

    DEG_0 = 0
    DEG_90 = 90
    DEG_180 = 180
    DEG_270 = 270

    @property
    def label(self) -> str:
        return f"{int(self.value)}deg"


class TextAxis(str, Enum):
    """The axis along which glyphs are arranged, before resolving the flip."""

    HORIZONTAL = "HORIZONTAL"
    VERTICAL = "VERTICAL"
    AMBIGUOUS = "AMBIGUOUS"


#: Minimum relative margin between the horizontal and vertical merge scores
#: before one axis is preferred over the other. Below this the answer is
#: AMBIGUOUS and BOTH axes are offered to the OCR trial. Chosen from the
#: measured separation on the real dataset (see `estimate_text_axis`).
AXIS_DECISION_MARGIN = 0.18

#: Regions smaller than this in either dimension carry too little ink for the
#: morphological signal to mean anything; they are reported AMBIGUOUS.
MIN_ORIENTABLE_SIDE_PX = 14

#: Upper bound on how many orientations a caller should attempt. Four is the
#: complete set, so this only exists to make the bound explicit in provenance.
MAX_ORIENTATION_CANDIDATES = 4


@dataclass(frozen=True)
class OrientationEstimate:
    """
    The outcome of orientation analysis for one region.

    Attributes
    ----------
    axis:
        Geometric axis of the text, or AMBIGUOUS.
    candidates:
        Ordered orientations to attempt, best-first. Always non-empty and
        always contains `Orientation.DEG_0` somewhere, so a region is never
        excluded from reading because orientation analysis was inconclusive.
    horizontal_score / vertical_score:
        Raw measured elongation scores. Exposed for audit; not probabilities.
    confidence:
        Ranking score in [0, 1] for the chosen axis. NOT a probability and NOT
        a legal confidence.
    notes:
        Human-readable explanation of how the axis was chosen.
    """

    axis: TextAxis
    candidates: Tuple[Orientation, ...]
    horizontal_score: float
    vertical_score: float
    confidence: float
    notes: Tuple[str, ...] = ()

    @property
    def primary(self) -> Orientation:
        return self.candidates[0]

    def provenance(self) -> Dict[str, object]:
        return {
            "axis": self.axis.value,
            "candidates": [int(c.value) for c in self.candidates],
            "horizontal_score": round(float(self.horizontal_score), 4),
            "vertical_score": round(float(self.vertical_score), 4),
            "axis_confidence": round(float(self.confidence), 4),
            "confidence_semantics": (
                "Heuristic axis-ranking score, not a calibrated probability and "
                "not a legal confidence. An orientation estimate is a routing "
                "hint for OCR only."
            ),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Rotation and coordinate mapping
# ---------------------------------------------------------------------------


def rotate_crop(crop: np.ndarray, orientation: Orientation) -> np.ndarray:
    """
    Rotate `crop` clockwise by `orientation` using an exact transpose.

    Lossless by construction: no interpolation, so no pixel value is invented.
    Always returns a new array; `crop` is never modified.
    """
    if crop is None or crop.size == 0:
        raise ValueError("rotate_crop() received an empty crop.")

    if orientation is Orientation.DEG_0:
        return crop.copy()
    if orientation is Orientation.DEG_90:
        return cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
    if orientation is Orientation.DEG_180:
        return cv2.rotate(crop, cv2.ROTATE_180)
    return cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)


def rotated_shape(
    shape: Tuple[int, int], orientation: Orientation
) -> Tuple[int, int]:
    """Return the (height, width) a crop of `shape` has after rotation."""
    h, w = int(shape[0]), int(shape[1])
    if orientation in (Orientation.DEG_90, Orientation.DEG_270):
        return w, h
    return h, w


def map_bbox_from_rotated(
    bbox: BBoxT,
    orientation: Orientation,
    unrotated_shape: Tuple[int, int],
) -> BBoxT:
    """
    Map a box found in a ROTATED crop back into UNROTATED crop coordinates.

    Args:
        bbox:             (x, y, w, h) as located in the rotated image.
        orientation:      the clockwise rotation that produced the rotated image.
        unrotated_shape:  (height, width) of the crop BEFORE rotation.

    This is the inverse of `rotate_crop()` acting on coordinates, and it is the
    step that keeps a vertically-printed net-quantity declaration pinned to the
    right pixels on the original photograph. Getting it wrong would attach a
    correct reading to the wrong part of the package, which is an evidence
    integrity failure even when the text itself is right.
    """
    x, y, w, h = (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
    src_h, src_w = int(unrotated_shape[0]), int(unrotated_shape[1])

    if orientation is Orientation.DEG_0:
        return x, y, w, h

    if orientation is Orientation.DEG_90:
        # Clockwise 90: source (sx, sy) -> rotated (src_h - 1 - sy, sx).
        # Inverting for the box corner gives:
        return y, src_h - (x + w), h, w

    if orientation is Orientation.DEG_180:
        return src_w - (x + w), src_h - (y + h), w, h

    # DEG_270 (counter-clockwise 90): source (sx, sy) -> rotated (sy, src_w-1-sx)
    return src_w - (y + h), x, h, w


def compose_to_original(
    bbox: BBoxT,
    orientation: Orientation,
    unrotated_shape: Tuple[int, int],
    offset: Tuple[int, int],
) -> BBoxT:
    """
    Full two-step mapping: rotated-crop box -> unrotated crop -> original image.

    `offset` is the (x, y) position of the crop's top-left corner in the
    original image, i.e. exactly what `preprocess.preprocess_region()` returns.
    Variant scaling must already have been undone by
    `PreprocessedVariant.map_bbox_to_source()` before calling this.
    """
    x, y, w, h = map_bbox_from_rotated(bbox, orientation, unrotated_shape)
    return x + int(offset[0]), y + int(offset[1]), w, h


# ---------------------------------------------------------------------------
# Axis estimation
# ---------------------------------------------------------------------------


def _ink_mask(crop: np.ndarray) -> np.ndarray:
    """
    Return a binary mask where 255 marks glyph ink, whichever polarity it has.

    Otsu is used rather than a fixed threshold because label colours vary
    enormously. The polarity is then normalised by assuming ink is the MINORITY
    class, which holds for text regions of any colour scheme; a region where
    that assumption fails is not a text region and its axis score will be
    correspondingly weak.
    """
    if crop.ndim == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop

    gray = np.ascontiguousarray(gray)
    if gray.dtype != np.uint8:
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    # Mild blur suppresses sensor noise without closing letter gaps.
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _thresh, binary = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    if float(np.mean(binary > 0)) > 0.5:
        binary = cv2.bitwise_not(binary)

    return binary


def _glyph_scale(binary: np.ndarray) -> float:
    """
    Estimate a characteristic glyph size in pixels from component statistics.

    The closing kernel length is derived from this rather than fixed, because a
    kernel tuned for 30px display type will merge an entire dense declaration
    panel into one blob at 8px, erasing the very signal being measured.
    """
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    if count <= 1:
        return 8.0

    sizes: List[float] = []
    total = binary.shape[0] * binary.shape[1]
    for i in range(1, count):
        w = int(stats[i, cv2.CC_STAT_WIDTH])
        h = int(stats[i, cv2.CC_STAT_HEIGHT])
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 4 or w * h > 0.5 * total:
            continue
        sizes.append(float(min(w, h)))

    if not sizes:
        return 8.0
    return float(np.clip(np.median(sizes), 3.0, 40.0))


def _merge_elongation(binary: np.ndarray, *, axis: str, kernel_len: int) -> float:
    """
    Close along one axis and measure how elongated the resulting blobs are.

    THE SIGNAL: glyphs merge into a continuous run along their READING
    DIRECTION, because the gaps between characters on a line are small compared
    with the gaps between lines. Closing a horizontal line of text with a
    horizontal kernel yields one long thin blob; closing the same text with a
    vertical kernel yields nothing new. So whichever axis produces the greater
    elongation is the axis the text runs along.

    Returned value is a bounded area-weighted mean elongation in [0, 1] terms
    of `1 - short/long` for the merged blobs, restricted to blobs that actually
    grew. It is a ranking score, not a probability.
    """
    if kernel_len < 3:
        kernel_len = 3

    if axis == "horizontal":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_len, 1))
    else:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_len))

    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)

    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        closed, connectivity=8
    )
    if count <= 1:
        return 0.0

    total_area = float(binary.shape[0] * binary.shape[1])
    weighted = 0.0
    weight = 0.0

    for i in range(1, count):
        w = float(stats[i, cv2.CC_STAT_WIDTH])
        h = float(stats[i, cv2.CC_STAT_HEIGHT])
        area = float(stats[i, cv2.CC_STAT_AREA])

        if area < 6 or w < 1 or h < 1:
            continue
        # A blob covering most of the region's bounding box CAN be a filled
        # graphic rather than a merged text run — but bounding-box size alone
        # cannot tell the two apart. A multi-line declaration paragraph closed
        # along its reading axis often fuses into a single component whose
        # bounding box spans nearly the whole crop (every line touches the
        # blob, even though the lines never merge with each other), while a
        # true filled graphic is also solidly INKED across that same bounding
        # box. Distinguish them with the blob's own fill density
        # (`area / (w*h)`): a fused paragraph stays sparse (text is mostly
        # background), a filled graphic does not. Without this check, a
        # regression could silently zero out the correct axis's score for
        # every large multi-line declaration block, which is precisely the
        # panel legal findings most depend on — the wrong axis would then win
        # by default and the region would be rotated into unreadable OCR
        # input. See test_orientation.py::
        # test_a_large_sparse_multiline_block_is_not_treated_as_a_filled_graphic.
        bbox_area = w * h
        fill_density = area / bbox_area if bbox_area > 0 else 0.0
        if bbox_area > 0.85 * total_area and fill_density > 0.5:
            continue

        if axis == "horizontal":
            elongation = 1.0 - (h / max(w, 1.0))
        else:
            elongation = 1.0 - (w / max(h, 1.0))

        elongation = float(np.clip(elongation, 0.0, 1.0))
        weighted += elongation * area
        weight += area

    if weight <= 0:
        return 0.0
    return float(np.clip(weighted / weight, 0.0, 1.0))


def estimate_text_axis(crop: np.ndarray) -> Tuple[TextAxis, float, float, float]:
    """
    Decide whether the glyphs in `crop` run horizontally or vertically.

    Returns `(axis, horizontal_score, vertical_score, confidence)`.

    AMBIGUOUS is returned whenever the two scores are within
    `AXIS_DECISION_MARGIN` of each other, or the region is too small to carry a
    meaningful signal. That is deliberate: the caller then tries both axes
    rather than silently discarding half the possibilities.
    """
    if crop is None or crop.size == 0:
        return TextAxis.AMBIGUOUS, 0.0, 0.0, 0.0

    h, w = crop.shape[:2]
    if min(h, w) < MIN_ORIENTABLE_SIDE_PX:
        return TextAxis.AMBIGUOUS, 0.0, 0.0, 0.0

    binary = _ink_mask(crop)
    ink_fraction = float(np.mean(binary > 0))

    # Essentially blank, or essentially solid: no glyph layout to measure.
    if ink_fraction < 0.005 or ink_fraction > 0.85:
        return TextAxis.AMBIGUOUS, 0.0, 0.0, 0.0

    scale = _glyph_scale(binary)
    kernel_len = int(np.clip(round(scale * 1.6), 3, 25))

    h_score = _merge_elongation(binary, axis="horizontal", kernel_len=kernel_len)
    v_score = _merge_elongation(binary, axis="vertical", kernel_len=kernel_len)

    spread = abs(h_score - v_score)
    denominator = max(h_score, v_score, 1e-6)
    relative = spread / denominator

    if relative < AXIS_DECISION_MARGIN:
        return TextAxis.AMBIGUOUS, h_score, v_score, float(relative)

    axis = TextAxis.HORIZONTAL if h_score > v_score else TextAxis.VERTICAL
    confidence = float(np.clip(relative, 0.0, 1.0))
    return axis, h_score, v_score, confidence


def estimate_region_orientation(
    crop: np.ndarray,
    *,
    max_candidates: int = MAX_ORIENTATION_CANDIDATES,
) -> OrientationEstimate:
    """
    Produce the ordered orientations an OCR trial should attempt for one region.

    The ordering encodes what geometry can and cannot tell us:

    * HORIZONTAL axis -> `[0, 180, 90, 270]`. Upright is far more common than
      upside-down on retail packaging, so 0 leads, but 180 is still offered
      because geometry cannot rule it out.
    * VERTICAL axis   -> `[90, 270, 0, 180]`. On Indian retail packaging, side
      declarations are most often printed reading bottom-to-top, which a
      clockwise 90 correction fixes; 270 covers the other convention.
    * AMBIGUOUS       -> `[0, 90, 180, 270]`, i.e. try everything, cheapest
      assumption first.

    The lower-ranked candidates are retained rather than dropped so that a
    wrong axis call degrades into a slower read, never into an unread region
    reported as NOT_OBSERVED.
    """
    axis, h_score, v_score, confidence = estimate_text_axis(crop)

    if axis is TextAxis.HORIZONTAL:
        order = (
            Orientation.DEG_0,
            Orientation.DEG_180,
            Orientation.DEG_90,
            Orientation.DEG_270,
        )
        note = (
            f"Glyphs merge along the horizontal axis "
            f"(h={h_score:.3f} > v={v_score:.3f}); reading upright first."
        )
    elif axis is TextAxis.VERTICAL:
        order = (
            Orientation.DEG_90,
            Orientation.DEG_270,
            Orientation.DEG_0,
            Orientation.DEG_180,
        )
        note = (
            f"Glyphs merge along the vertical axis "
            f"(v={v_score:.3f} > h={h_score:.3f}); rotating this region only, "
            "not the whole image."
        )
    else:
        order = (
            Orientation.DEG_0,
            Orientation.DEG_90,
            Orientation.DEG_180,
            Orientation.DEG_270,
        )
        note = (
            f"Axis inconclusive (h={h_score:.3f}, v={v_score:.3f}); all four "
            "orientations offered rather than guessing one."
        )

    limit = int(np.clip(max_candidates, 1, MAX_ORIENTATION_CANDIDATES))
    candidates = order[:limit]

    notes = [
        note,
        "Geometry cannot separate 0 from 180 or 90 from 270; the flip is "
        "resolved by attempting to read the glyphs.",
    ]

    return OrientationEstimate(
        axis=axis,
        candidates=candidates,
        horizontal_score=h_score,
        vertical_score=v_score,
        confidence=confidence,
        notes=tuple(notes),
    )


def dominant_axis_summary(
    estimates: Sequence[OrientationEstimate],
) -> Dict[str, object]:
    """
    Summarise per-region axes for one image, for observability.

    A MIXED result is the normal, expected outcome for a cylindrical body
    label, and reporting it is how the pipeline demonstrates that it handled
    multiple orientations in one photograph instead of forcing one global
    rotation.
    """
    counts: Dict[str, int] = {a.value: 0 for a in TextAxis}
    for estimate in estimates:
        counts[estimate.axis.value] += 1

    decided = counts[TextAxis.HORIZONTAL.value] + counts[TextAxis.VERTICAL.value]
    mixed = (
        counts[TextAxis.HORIZONTAL.value] > 0
        and counts[TextAxis.VERTICAL.value] > 0
    )

    return {
        "axis_counts": counts,
        "regions_analysed": len(estimates),
        "regions_with_decided_axis": decided,
        "mixed_orientation_image": mixed,
        "note": (
            "Multiple text orientations were found in a single image and each "
            "region was rotated locally. The original image was never rotated."
            if mixed
            else "Per-region orientation applied; the original image was never "
            "rotated."
        ),
    }
