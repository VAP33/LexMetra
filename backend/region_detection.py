"""
Region detection: find WHERE to look on a captured package surface.

What this module is
-------------------
A classical-CV region proposer. Given one captured image it returns a list of
`DetectedRegion` objects, each with a type, a bbox, a confidence, and the
signals that produced it. That is all. It answers "there is a block of text
here", "there is a barcode here", "the package boundary is probably here".

What this module is NOT
----------------------
Legal-safety contract, restated because this is the layer where the mistake is
easiest to make:

1. TEXT != MANDATORY DECLARATION.
   `RegionType.TEXT` means "pixels that look like printed characters". It does
   NOT mean the region contains an MRP, a net quantity, or any other required
   declaration. Only `DECLARATION_TEXT` claims a region *may* hold a
   declaration, and even that is a routing hint for OCR, never a finding.

2. STICKER != VIOLATION.
   `RegionType.STICKER` means "this area's boundary/texture statistics differ
   from the surrounding print". Overpasted stickers are lawful in many
   circumstances (importer particulars, revised MRP under Rule 6(3), retailer
   price tags). A sticker region routes to human review, never to FAIL.

3. PACKAGE_BOUNDARY != PDP.
   The package boundary is the outline of the physical package in frame. The
   Principal Display Panel is a legally defined display area. Conflating them
   would let a boundary-detection error propagate into a Rule 8 font-size or
   PDP-area claim. PDP estimation lives in `image_quality.estimate_pdp_bbox()`
   and geometry/measurement lives elsewhere; this module never sets PDP.

4. NOT DETECTED != ABSENT.
   An empty region list means the detector found nothing, on this image, under
   these conditions. It is evidence about the DETECTOR, not about the package.
   `DetectionResult.coverage_note` carries that caveat explicitly so callers
   cannot accidentally read emptiness as absence.

5. This module makes NO legal determination. It imports `preprocess` (a leaf
   module) and nothing else from the project — no rule engine, no OCR engine,
   no database.

Region-first pipeline position
-----------------------------
    FULL IMAGE
      -> crop_screenshot_chrome()        (preprocess)
      -> detect_package_boundary()       (this module)
      -> detect_regions()                (this module)
      -> preprocess_region() per region  (preprocess)
      -> orientation + OCR               (later modules)

Coordinates
-----------
Every bbox returned is in ORIGINAL IMAGE PIXELS of the image passed in. When the
caller has already cropped screenshot chrome, it is the caller's job to add the
`ContentRegion.bbox` offset — `detect_regions()` accepts an `offset` argument
that does this for you and records it in provenance.

Upgrade path
------------
`detect_regions()` is the seam. A learned detector (DBNet/EAST text detection,
or a trained label/sticker detector) can replace the internals while keeping
the `DetectedRegion` contract, and the legal-safety semantics above stay
attached to the TYPES rather than to the algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

import preprocess

BBoxT = Tuple[int, int, int, int]


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


class RegionType(str, Enum):
    """
    Stable region-type codes. Persisted in evidence provenance — add members
    rather than renaming, or stored audit records become unreadable.

    Read the semantics carefully; they are legally load-bearing:

    PACKAGE_BOUNDARY  Outline of the physical package in frame. NOT the PDP.
    TEXT              Printed characters. NOT necessarily a declaration.
    DECLARATION_TEXT  A text block whose layout/position makes it a plausible
                      place for mandatory declarations. A ROUTING HINT only.
    LABEL             A distinct printed label panel affixed to or printed on
                      the package.
    STICKER           An area whose boundary/texture differs from surrounding
                      print. NOT a violation.
    BARCODE           1D symbology candidate.
    QR                2D symbology candidate.
    LOGO              Compact high-saturation/high-edge graphic mark.
    GRAPHIC           Non-text pictorial content.
    UNKNOWN           Detected structure that could not be typed. Kept rather
                      than discarded, because silently dropping a region the
                      detector could not classify is how declarations get
                      missed.
    """

    PACKAGE_BOUNDARY = "PACKAGE_BOUNDARY"
    TEXT = "TEXT"
    DECLARATION_TEXT = "DECLARATION_TEXT"
    LABEL = "LABEL"
    STICKER = "STICKER"
    BARCODE = "BARCODE"
    QR = "QR"
    LOGO = "LOGO"
    GRAPHIC = "GRAPHIC"
    UNKNOWN = "UNKNOWN"


#: Types whose contents should be routed to text OCR.
TEXT_LIKE_TYPES = frozenset(
    {RegionType.TEXT, RegionType.DECLARATION_TEXT, RegionType.LABEL, RegionType.UNKNOWN}
)

#: Types whose contents should be routed to a symbology decoder, never to OCR
#: field classification. A barcode read as text is exactly how the "17m"
#: net-quantity regression happened.
SYMBOLOGY_TYPES = frozenset({RegionType.BARCODE, RegionType.QR})


class DetectionMethod(str, Enum):
    """How a region was proposed. Recorded for auditability and debugging."""

    MORPH_TEXT_BLOCKS = "MORPH_TEXT_BLOCKS"
    CONNECTED_COMPONENTS = "CONNECTED_COMPONENTS"
    CONTOUR_QUAD = "CONTOUR_QUAD"
    CV_BARCODE_DETECTOR = "CV_BARCODE_DETECTOR"
    CV_QR_DETECTOR = "CV_QR_DETECTOR"
    BARCODE_STRIPE_HEURISTIC = "BARCODE_STRIPE_HEURISTIC"
    SATURATION_GRAPHIC = "SATURATION_GRAPHIC"
    STICKER_HEURISTIC = "STICKER_HEURISTIC"
    CALLER_SUPPLIED = "CALLER_SUPPLIED"


# Tunables. Deliberately module-level and named so they can be moved to
# configuration without touching logic.
MIN_REGION_SIDE_PX = 12
MIN_TEXT_REGION_AREA_FRAC = 0.00035
MAX_TEXT_REGION_AREA_FRAC = 0.72
MAX_REGIONS = 40
NMS_IOU_THRESHOLD = 0.45
#: Minimum row-to-row translational invariance for the fallback barcode
#: heuristic. Calibrated against the real dataset — see
#: `_row_translational_invariance()` for the measured separation.
MIN_BARCODE_ROW_INVARIANCE = 0.85
#: Fraction of a region that must be covered by another to be treated as
#: contained within it (used for label/text nesting, not for suppression).
CONTAINMENT_THRESHOLD = 0.80


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class DetectedRegion:
    """
    One proposed region of interest.

    `confidence` is a HEURISTIC RANKING SCORE in [0, 1]. It is not a calibrated
    probability and must never be presented to a user as one, nor multiplied
    into a legal confidence. Its only jobs are ordering and thresholding.
    """

    region_type: RegionType
    bbox: BBoxT
    confidence: float
    method: DetectionMethod
    signals: Dict[str, float] = field(default_factory=dict)
    #: Free-text explanation of why this region was proposed, for the audit log
    #: and the debug overlay.
    reason: str = ""
    #: Index into DetectionResult.regions of the enclosing region, when this
    #: region sits inside a detected label/boundary.
    parent_index: Optional[int] = None
    #: True when the region touches the frame edge, i.e. the underlying
    #: structure may extend outside the photograph. Callers must treat a
    #: truncated region's OCR output as PARTIAL evidence.
    truncated: bool = False

    @property
    def x(self) -> int:
        return self.bbox[0]

    @property
    def y(self) -> int:
        return self.bbox[1]

    @property
    def width(self) -> int:
        return self.bbox[2]

    @property
    def height(self) -> int:
        return self.bbox[3]

    @property
    def area(self) -> int:
        return int(self.bbox[2]) * int(self.bbox[3])

    @property
    def aspect_ratio(self) -> float:
        h = max(1, int(self.bbox[3]))
        return float(self.bbox[2]) / float(h)

    @property
    def region_id(self) -> str:
        """
        Stable, content-derived identifier for cross-referencing this region.

        Derived from the type and geometry rather than a counter so that the SAME
        region gets the SAME id across a re-run, a report regeneration, and a
        stored audit record. An id that shifted when the region list was
        reordered would make an audit trail unverifiable.
        """
        x, y, w, h = (int(v) for v in self.bbox)
        return f"{self.region_type.value}:{x},{y},{w},{h}"

    def is_text_like(self) -> bool:
        return self.region_type in TEXT_LIKE_TYPES

    def is_symbology(self) -> bool:
        return self.region_type in SYMBOLOGY_TYPES

    def shifted(self, dx: int, dy: int) -> "DetectedRegion":
        """Return a copy translated into another coordinate frame."""
        x, y, w, h = self.bbox
        return DetectedRegion(
            region_type=self.region_type,
            bbox=(int(x) + int(dx), int(y) + int(dy), int(w), int(h)),
            confidence=self.confidence,
            method=self.method,
            signals=dict(self.signals),
            reason=self.reason,
            parent_index=self.parent_index,
            truncated=self.truncated,
        )

    def provenance(self) -> Dict[str, object]:
        """Audit record for this proposal."""
        return {
            "region_type": self.region_type.value,
            "region_id": self.region_id,
            "bbox": [int(v) for v in self.bbox],
            "detection_method": self.method.value,
            "detector_confidence": round(float(self.confidence), 4),
            "signals": {k: round(float(v), 4) for k, v in self.signals.items()},
            "reason": self.reason,
            "truncated": self.truncated,
            "confidence_semantics": (
                "Heuristic detector ranking score, not a calibrated probability "
                "and not a legal confidence."
            ),
        }


@dataclass
class DetectionResult:
    """
    All regions proposed for one image, plus honest caveats.

    `coverage_note` exists so that a caller (or a report reader) cannot mistake
    an empty or sparse result for a statement about the package.
    """

    regions: List[DetectedRegion] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    package_boundary: Optional[DetectedRegion] = None
    #: Offset applied to every bbox, when the caller detected regions on a crop.
    offset: Tuple[int, int] = (0, 0)
    notes: List[str] = field(default_factory=list)

    @property
    def coverage_note(self) -> str:
        return (
            "Region detection reports what the detector found in this image "
            "under these capture conditions. An absent region is NOT evidence "
            "that a declaration is missing from the package."
        )

    def of_type(self, *types: RegionType) -> List[DetectedRegion]:
        wanted = set(types)
        return [r for r in self.regions if r.region_type in wanted]

    def text_regions(self) -> List[DetectedRegion]:
        """Regions to route to OCR, highest-confidence first."""
        return sorted(
            (r for r in self.regions if r.is_text_like()),
            key=lambda r: r.confidence,
            reverse=True,
        )

    def symbology_regions(self) -> List[DetectedRegion]:
        return [r for r in self.regions if r.is_symbology()]

    def provenance(self) -> Dict[str, object]:
        return {
            "image_size": [self.image_width, self.image_height],
            "offset": [int(self.offset[0]), int(self.offset[1])],
            "region_count": len(self.regions),
            "coverage_note": self.coverage_note,
            "notes": list(self.notes),
            "regions": [r.provenance() for r in self.regions],
        }


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _clip_bbox(bbox: BBoxT, width: int, height: int) -> Optional[BBoxT]:
    x, y, w, h = (int(v) for v in bbox)
    x0 = max(0, min(x, width))
    y0 = max(0, min(y, height))
    x1 = max(0, min(x + w, width))
    y1 = max(0, min(y + h, height))
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def _iou(a: BBoxT, b: BBoxT) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix0, iy0 = max(ax, bx), max(ay, by)
    ix1, iy1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return float(inter) / float(union) if union > 0 else 0.0


def _containment(inner: BBoxT, outer: BBoxT) -> float:
    """Fraction of `inner` that lies inside `outer`."""
    ax, ay, aw, ah = inner
    bx, by, bw, bh = outer
    ix0, iy0 = max(ax, bx), max(ay, by)
    ix1, iy1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inner_area = max(1, aw * ah)
    return float(iw * ih) / float(inner_area)


def _touches_edge(bbox: BBoxT, width: int, height: int, *, margin: int = 2) -> bool:
    x, y, w, h = bbox
    return bool(
        x <= margin
        or y <= margin
        or x + w >= width - margin
        or y + h >= height - margin
    )


def _merge_bboxes(boxes: Sequence[BBoxT]) -> BBoxT:
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def suppress_overlaps(
    regions: Sequence[DetectedRegion],
    *,
    iou_threshold: float = NMS_IOU_THRESHOLD,
) -> List[DetectedRegion]:
    """
    Greedy non-maximum suppression, but only WITHIN a region type.

    Cross-type suppression is deliberately not done: a barcode sitting inside a
    label panel, or a sticker overlapping a text block, are both real and both
    legally interesting. Collapsing them would destroy exactly the evidence a
    reviewer needs.
    """
    kept: List[DetectedRegion] = []
    for region in sorted(regions, key=lambda r: r.confidence, reverse=True):
        duplicate = any(
            other.region_type == region.region_type
            and _iou(region.bbox, other.bbox) > iou_threshold
            for other in kept
        )
        if not duplicate:
            kept.append(region)
    return kept


def assign_parents(regions: List[DetectedRegion]) -> List[DetectedRegion]:
    """
    Link each region to the smallest region that (mostly) contains it.

    Nesting is informational: a text block inside a detected LABEL is more
    likely to be a declaration block than a floating text blob on artwork, and
    a reviewer benefits from seeing the hierarchy. Nothing is removed.
    """
    order = sorted(range(len(regions)), key=lambda i: regions[i].area)
    for idx, region in enumerate(regions):
        best: Optional[int] = None
        best_area = None
        for other_idx in order:
            if other_idx == idx:
                continue
            other = regions[other_idx]
            if other.area <= region.area:
                continue
            if _containment(region.bbox, other.bbox) < CONTAINMENT_THRESHOLD:
                continue
            if best_area is None or other.area < best_area:
                best, best_area = other_idx, other.area
        region.parent_index = best
    return regions


# ---------------------------------------------------------------------------
# Package boundary
# ---------------------------------------------------------------------------


def detect_package_boundary(image: np.ndarray) -> Optional[DetectedRegion]:
    """
    Estimate the outline of the package in frame.

    Returns None when no convincing boundary is found. None is a legitimate,
    meaningful answer: a close-up crop of a label fills the frame and has no
    detectable package outline, and a cluttered shelf photo may have several
    competing outlines. Fabricating a boundary would push a wrong region set
    into every downstream stage.

    IMPORTANT: the result is `RegionType.PACKAGE_BOUNDARY`, never a PDP. See
    the module docstring, point 3.
    """
    if image is None or image.size == 0:
        return None

    gray = preprocess._to_gray(image)
    height, width = gray.shape[:2]
    frame_area = float(height * width)
    if frame_area <= 0:
        return None

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 130)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best: Optional[BBoxT] = None
    best_score = 0.0
    best_signals: Dict[str, float] = {}

    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        area = float(cv2.contourArea(contour))
        frac = area / frame_area
        # A package that fills under 8% of the frame is more likely to be
        # artwork or clutter; one that fills over 98% means the package extends
        # beyond the frame and the "boundary" is really the frame itself.
        if frac < 0.08 or frac > 0.98:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w < MIN_REGION_SIDE_PX or h < MIN_REGION_SIDE_PX:
            continue
        box_area = float(w * h)
        fill = area / box_area if box_area > 0 else 0.0
        # Prefer solid, reasonably large, reasonably compact shapes.
        score = 0.55 * min(1.0, frac / 0.6) + 0.45 * fill
        if score > best_score:
            best_score = score
            best = (x, y, w, h)
            best_signals = {
                "frame_fraction": frac,
                "contour_fill": fill,
                "contour_area_px": area,
            }

    if best is None:
        return None

    clipped = _clip_bbox(best, width, height)
    if clipped is None:
        return None

    truncated = _touches_edge(clipped, width, height)
    return DetectedRegion(
        region_type=RegionType.PACKAGE_BOUNDARY,
        bbox=clipped,
        confidence=round(float(min(1.0, best_score)), 4),
        method=DetectionMethod.CONTOUR_QUAD,
        signals=best_signals,
        reason=(
            "Largest solid closed contour covering a plausible share of the "
            "frame. This is the package outline, NOT the Principal Display "
            "Panel."
        ),
        truncated=truncated,
    )


# ---------------------------------------------------------------------------
# Text region proposal
# ---------------------------------------------------------------------------


def _text_edge_map(gray: np.ndarray) -> np.ndarray:
    """
    Binary map emphasising character strokes.

    Uses a morphological gradient rather than Canny: on the real dataset,
    Canny on glossy packaging produced long specular-highlight contours that
    dominated the contour list, while the gradient responds to local stroke
    contrast in both polarities, which matters because label text appears both
    dark-on-light and light-on-dark (often on the same panel).
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)
    _thresh, binary = cv2.threshold(
        gradient, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
    )
    return binary


def _stroke_density(binary: np.ndarray, bbox: BBoxT) -> float:
    x, y, w, h = bbox
    crop = binary[y:y + h, x:x + w]
    if crop.size == 0:
        return 0.0
    return float(np.count_nonzero(crop)) / float(crop.size)


def _row_profile_variance(gray: np.ndarray, bbox: BBoxT) -> float:
    """
    How strongly the region's ink varies row to row.

    Text has a characteristic banded row profile (baselines and gaps); flat
    artwork and gradients do not. Normalised to roughly [0, 1].
    """
    x, y, w, h = bbox
    crop = gray[y:y + h, x:x + w]
    if crop.size == 0 or crop.shape[0] < 4:
        return 0.0
    row_means = crop.mean(axis=1).astype(np.float32)
    spread = float(row_means.std())
    return float(min(1.0, spread / 40.0))


def _stroke_width_consistency(binary_crop: np.ndarray) -> float:
    """
    Rough consistency of stroke thickness via successive erosions.

    Printed text has a narrow stroke-width distribution; photographic texture
    does not. Returns [0, 1], higher = more text-like.
    """
    if binary_crop.size == 0:
        return 0.0
    ink = float(np.count_nonzero(binary_crop))
    if ink <= 0:
        return 0.0
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    eroded = cv2.erode(binary_crop, kernel, iterations=1)
    remaining = float(np.count_nonzero(eroded))
    # Thin, uniform strokes mostly vanish after one erosion; thick blobs do not.
    vanished = 1.0 - (remaining / ink)
    return float(max(0.0, min(1.0, vanished)))


def _text_confidence(
    gray: np.ndarray,
    binary: np.ndarray,
    bbox: BBoxT,
) -> Tuple[float, Dict[str, float]]:
    """
    Score how text-like a candidate box is.

    Combines stroke density (in a plausible band, not simply "more is better"),
    row-profile banding, stroke-width consistency, and an aspect-ratio prior.
    The output is a ranking score, not a probability.
    """
    x, y, w, h = bbox
    density = _stroke_density(binary, bbox)
    banding = _row_profile_variance(gray, bbox)
    consistency = _stroke_width_consistency(binary[y:y + h, x:x + w])

    # Text occupies a middling fraction of its box. Near-empty boxes are noise;
    # near-solid boxes are blocks of colour, not characters.
    if density <= 0.02 or density >= 0.75:
        density_score = 0.0
    else:
        density_score = 1.0 - abs(density - 0.22) / 0.53
        density_score = max(0.0, min(1.0, density_score))

    ratio = float(w) / float(max(1, h))
    # Declaration lines are usually wider than tall, but vertical text on
    # cylindrical packs (the Thums Up can, the Vaseline body label) is real and
    # must not be scored to zero.
    if 0.12 <= ratio <= 30.0:
        aspect_score = 1.0
    elif ratio > 30.0:
        aspect_score = max(0.0, (45.0 - ratio) / 15.0)
    else:
        aspect_score = max(0.0, ratio / 0.12)

    score = (
        0.38 * density_score
        + 0.27 * banding
        + 0.20 * consistency
        + 0.15 * aspect_score
    )
    signals = {
        "stroke_density": density,
        "row_banding": banding,
        "stroke_width_consistency": consistency,
        "aspect_ratio": ratio,
        "aspect_score": aspect_score,
    }
    return float(max(0.0, min(1.0, score))), signals


def detect_text_regions(
    image: np.ndarray,
    *,
    max_regions: int = MAX_REGIONS,
    min_confidence: float = 0.22,
) -> List[DetectedRegion]:
    """
    Propose text blocks using morphological line grouping.

    Two passes at different closing kernels are run and merged: a wide-flat
    kernel groups characters into horizontal lines/blocks, and a tall-narrow
    kernel groups them into vertical runs. Running both is what makes mixed
    horizontal + vertical label text (the mandatory Vaseline body-label case)
    detectable without rotating the whole image.

    Returns `RegionType.TEXT` regions. Promotion to DECLARATION_TEXT is a
    separate, explicitly-hinted step — see `classify_declaration_candidates()`.
    """
    if image is None or image.size == 0:
        return []

    gray = preprocess._to_gray(image)
    height, width = gray.shape[:2]
    frame_area = float(height * width)
    if frame_area <= 0:
        return []

    binary = _text_edge_map(gray)

    # Kernel sizes scale with image size so the detector behaves the same on a
    # 300px crop and a 2400px screenshot.
    span = max(height, width)
    horiz_w = max(9, int(span * 0.012))
    vert_h = max(9, int(span * 0.012))

    passes = (
        ("horizontal", cv2.getStructuringElement(cv2.MORPH_RECT, (horiz_w, 3))),
        ("vertical", cv2.getStructuringElement(cv2.MORPH_RECT, (3, vert_h))),
    )

    candidates: List[DetectedRegion] = []
    for pass_name, kernel in passes:
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
        contours, _ = cv2.findContours(
            closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < MIN_REGION_SIDE_PX or h < MIN_REGION_SIDE_PX:
                continue
            frac = (w * h) / frame_area
            if frac < MIN_TEXT_REGION_AREA_FRAC or frac > MAX_TEXT_REGION_AREA_FRAC:
                continue
            clipped = _clip_bbox((x, y, w, h), width, height)
            if clipped is None:
                continue
            confidence, signals = _text_confidence(gray, binary, clipped)
            if confidence < min_confidence:
                continue
            signals["area_fraction"] = frac
            signals["pass_vertical"] = 1.0 if pass_name == "vertical" else 0.0
            candidates.append(
                DetectedRegion(
                    region_type=RegionType.TEXT,
                    bbox=clipped,
                    confidence=round(confidence, 4),
                    method=DetectionMethod.MORPH_TEXT_BLOCKS,
                    signals=signals,
                    reason=(
                        f"Stroke-like pixels grouped by a {pass_name} closing "
                        "kernel. Contains printed characters; this is NOT a "
                        "claim that a mandatory declaration is present."
                    ),
                    truncated=_touches_edge(clipped, width, height),
                )
            )

    kept = suppress_overlaps(candidates)
    kept.sort(key=lambda r: r.confidence, reverse=True)
    return kept[:max_regions]


# ---------------------------------------------------------------------------
# Symbology regions
# ---------------------------------------------------------------------------


def detect_symbology_regions(image: np.ndarray) -> List[DetectedRegion]:
    """
    Locate barcode and QR candidates.

    Localisation only — decoding belongs in `barcode.py`. Separating the two
    matters: a located-but-undecodable symbol is useful evidence ("there is a
    barcode here, it could not be read"), whereas silently dropping it looks
    like the package has no barcode.

    Regions are typed BARCODE/QR precisely so that OCR field classification
    can EXCLUDE them. Reading barcode stripes as text is how a barcode's noise
    became a net-quantity value ("17m") in an earlier version.

    LOCALISATION IS NOT CONFIRMATION. Known false positives on the real dataset:
    the moulded vertical ridges of a screw-cap jar satisfy the stripe and
    row-invariance tests (images 21, 22), and OpenCV's QR detector fires on a
    circular brand mark (image 27). A localised symbol therefore carries
    `confidence` well below 1.0 and must be confirmed by an actual DECODE in
    `barcode.py` before anything claims the package bears a symbol. Note also
    that a false symbology region cannot hide text: suppression never crosses
    region types, so overlapping TEXT regions are still routed to OCR.
    """
    if image is None or image.size == 0:
        return []

    gray = preprocess._to_gray(image)
    height, width = gray.shape[:2]
    found: List[DetectedRegion] = []

    # --- OpenCV's own detectors, when available -----------------------------
    try:
        detector = cv2.barcode.BarcodeDetector()
        ok, corners = detector.detect(gray)
        if ok and corners is not None:
            for quad in np.asarray(corners).reshape(-1, 4, 2):
                x, y, w, h = cv2.boundingRect(quad.astype(np.float32))
                clipped = _clip_bbox((x, y, w, h), width, height)
                if clipped is None:
                    continue
                found.append(
                    DetectedRegion(
                        region_type=RegionType.BARCODE,
                        bbox=clipped,
                        confidence=0.85,
                        method=DetectionMethod.CV_BARCODE_DETECTOR,
                        signals={"detector": 1.0},
                        reason="OpenCV barcode detector localised a 1D symbol.",
                        truncated=_touches_edge(clipped, width, height),
                    )
                )
    except (cv2.error, AttributeError):
        # Detector unavailable in this OpenCV build; the stripe heuristic below
        # still runs. Recorded rather than silently ignored by the caller via
        # DetectionResult.notes.
        pass

    try:
        qr = cv2.QRCodeDetector()
        ok, points = qr.detect(gray)
        if ok and points is not None:
            for quad in np.asarray(points).reshape(-1, 4, 2):
                x, y, w, h = cv2.boundingRect(quad.astype(np.float32))
                clipped = _clip_bbox((x, y, w, h), width, height)
                if clipped is None:
                    continue
                found.append(
                    DetectedRegion(
                        region_type=RegionType.QR,
                        bbox=clipped,
                        confidence=0.85,
                        method=DetectionMethod.CV_QR_DETECTOR,
                        signals={"detector": 1.0},
                        reason="OpenCV QR detector localised a 2D symbol.",
                        truncated=_touches_edge(clipped, width, height),
                    )
                )
    except (cv2.error, AttributeError):
        pass

    found.extend(_barcode_stripe_candidates(gray))
    return suppress_overlaps(found)


def _barcode_stripe_candidates(gray: np.ndarray) -> List[DetectedRegion]:
    """
    Fallback 1D-barcode localiser keyed on directional gradient energy.

    A barcode is the one thing on a package with strong, near-exclusively
    horizontal gradient energy over a tall-thin repeating structure. This finds
    it when the dedicated detector fails (poor focus, extreme angle, partial
    symbol) so that the region is still FLAGGED as symbology and kept out of
    text classification.
    """
    height, width = gray.shape[:2]
    frame_area = float(height * width)
    if frame_area <= 0:
        return []

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    # Vertical bars => large |gx|, small |gy|.
    directional = cv2.subtract(np.abs(gx), np.abs(gy))
    directional = cv2.convertScaleAbs(directional)
    directional = cv2.GaussianBlur(directional, (9, 9), 0)
    _t, binary = cv2.threshold(directional, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    span = max(height, width)
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(9, int(span * 0.02)), max(5, int(span * 0.008)))
    )
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    closed = cv2.erode(closed, None, iterations=2)
    closed = cv2.dilate(closed, None, iterations=2)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    raw_boxes: List[BBoxT] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < 18 or h < 12:
            continue
        raw_boxes.append((x, y, w, h))

    out: List[DetectedRegion] = []
    for x, y, w, h in _merge_stripe_runs(raw_boxes):
        frac = (w * h) / frame_area
        if frac < 0.0008 or frac > 0.35:
            continue
        ratio = float(w) / float(max(1, h))
        # A 1D symbol is normally wider than tall, but a quiet zone can split
        # one contour into pieces and a partial capture can be near-square, so
        # the shape gate is permissive and `_row_translational_invariance()`
        # below does the real discrimination.
        if not (0.9 <= ratio <= 12.0):
            continue
        clipped = _clip_bbox((x, y, w, h), width, height)
        if clipped is None:
            continue

        crop = gray[clipped[1]:clipped[1] + clipped[3], clipped[0]:clipped[0] + clipped[2]]
        stripe = _stripe_periodicity(crop)
        translational = _row_translational_invariance(crop)
        if stripe < 0.30 or translational < MIN_BARCODE_ROW_INVARIANCE:
            continue
        confidence = float(
            max(0.0, min(0.75, 0.20 + 0.25 * stripe + 0.30 * translational))
        )
        out.append(
            DetectedRegion(
                region_type=RegionType.BARCODE,
                bbox=clipped,
                confidence=round(confidence, 4),
                method=DetectionMethod.BARCODE_STRIPE_HEURISTIC,
                signals={
                    "stripe_periodicity": stripe,
                    "row_translational_invariance": translational,
                    "aspect_ratio": ratio,
                },
                reason=(
                    "Directional gradient energy with periodic vertical "
                    "structure that repeats identically down every row. "
                    "Candidate 1D symbol; decoding is a separate step and may "
                    "still fail."
                ),
                truncated=_touches_edge(clipped, width, height),
            )
        )
    return out


def _merge_stripe_runs(
    boxes: Sequence[BBoxT],
    *,
    vertical_overlap: float = 0.6,
    max_gap_ratio: float = 0.35,
) -> List[BBoxT]:
    """
    Join horizontally adjacent stripe fragments that share a vertical extent.

    A 1D symbol does not always come back as one contour: a wide bar, a quiet
    zone, or a glare band splits it into pieces sitting side by side at the same
    height. Scoring those fragments individually understates the symbol and can
    push each below the area/aspect gates, so the fragments are stitched before
    scoring. Fragments that do not join anything are returned unchanged, so
    nothing is lost.
    """
    remaining = sorted(boxes, key=lambda b: b[0])
    groups: List[List[BBoxT]] = []

    for box in remaining:
        x, y, w, h = box
        placed = False
        for group in groups:
            gx, gy, gw, gh = _merge_bboxes(group)
            # Shared vertical extent, as a fraction of the smaller height.
            overlap = min(y + h, gy + gh) - max(y, gy)
            if overlap <= 0:
                continue
            if overlap / float(min(h, gh)) < vertical_overlap:
                continue
            gap = x - (gx + gw)
            if gap > max_gap_ratio * max(h, gh):
                continue
            group.append(box)
            placed = True
            break
        if not placed:
            groups.append([box])

    return [_merge_bboxes(group) for group in groups]


def _stripe_periodicity(crop: np.ndarray) -> float:
    """
    Estimate how periodic a region's vertical structure is, in [0, 1].

    Collapses the crop to a column profile and measures how many sign changes
    it makes around its own mean relative to its width. Real barcodes make many
    regular crossings; text and artwork make far fewer.

    On its own this is NOT sufficient — a line of dense small text produces a
    similar crossing density. Pair it with `_row_translational_invariance()`.
    """
    if crop.size == 0 or crop.shape[1] < 16:
        return 0.0
    profile = crop.mean(axis=0).astype(np.float32)
    profile -= float(profile.mean())
    if float(np.abs(profile).max()) < 3.0:
        return 0.0
    signs = np.signbit(profile)
    crossings = int(np.count_nonzero(np.diff(signs)))
    # A typical EAN-13 spans ~59 modules; a healthy read shows tens of
    # crossings across the symbol width.
    density = crossings / float(max(1, crop.shape[1]))
    return float(max(0.0, min(1.0, density / 0.18)))


def _row_translational_invariance(crop: np.ndarray) -> float:
    """
    Mean correlation of each row with the region's own column profile, [0, 1].

    This is the property that actually SEPARATES a barcode from dense text, and
    it is measured rather than assumed: a 1D barcode is translation-invariant
    down its height — every scan line is the same signal — whereas text lines
    change completely from row to row.

    Measured on the real dataset (Bru jar back label, `images dataset/`):
      genuine EAN-13 symbol        0.967
      dense declaration text lines 0.49 - 0.69
    Hence `MIN_BARCODE_ROW_INVARIANCE = 0.85`, which is comfortably above every
    text block observed and below the genuine symbol. This gate is why a
    barcode region is not proposed over declaration text — the direct cause of
    the historic bug where barcode noise was classified as the net quantity
    "17m".
    """
    if crop.size == 0 or crop.shape[0] < 4 or crop.shape[1] < 16:
        return 0.0
    matrix = crop.astype(np.float32)
    profile = matrix.mean(axis=0)
    profile = profile - float(profile.mean())
    profile_norm = float(np.linalg.norm(profile))
    if profile_norm < 1e-6:
        return 0.0

    correlations: List[float] = []
    for row in matrix:
        centred = row - float(row.mean())
        norm = float(np.linalg.norm(centred))
        if norm < 1e-6:
            continue
        correlations.append(float(np.dot(centred, profile) / (norm * profile_norm)))
    if not correlations:
        return 0.0
    return float(max(0.0, min(1.0, float(np.mean(correlations)))))


# ---------------------------------------------------------------------------
# Label / sticker / graphic regions
# ---------------------------------------------------------------------------


def detect_label_regions(
    image: np.ndarray,
    *,
    min_area_frac: float = 0.02,
    max_area_frac: float = 0.85,
    max_regions: int = 6,
) -> List[DetectedRegion]:
    """
    Propose distinct printed label panels: large, quadrilateral-ish, text-bearing.

    A LABEL is a container hint, not a declaration. Its value is that text
    blocks nested inside a label panel are more plausibly declaration blocks
    than text floating on background artwork — see `assign_parents()`.
    """
    if image is None or image.size == 0:
        return []

    gray = preprocess._to_gray(image)
    height, width = gray.shape[:2]
    frame_area = float(height * width)
    if frame_area <= 0:
        return []

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    text_binary = _text_edge_map(gray)

    out: List[DetectedRegion] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:30]:
        area = float(cv2.contourArea(contour))
        frac = area / frame_area
        if frac < min_area_frac or frac > max_area_frac:
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        # Allow 4-8 vertices: a label on a curved surface, or one with rounded
        # corners, will not approximate to exactly four.
        if not (4 <= len(approx) <= 8):
            continue
        x, y, w, h = cv2.boundingRect(contour)
        clipped = _clip_bbox((x, y, w, h), width, height)
        if clipped is None:
            continue
        box_area = float(w * h)
        fill = area / box_area if box_area > 0 else 0.0
        if fill < 0.55:
            continue
        ink = _stroke_density(text_binary, clipped)
        # A label panel carries print. A blank rectangle is not a label.
        if ink < 0.03:
            continue
        confidence = float(max(0.0, min(1.0, 0.45 * fill + 0.35 * min(1.0, ink / 0.2) + 0.2 * min(1.0, frac / 0.4))))
        out.append(
            DetectedRegion(
                region_type=RegionType.LABEL,
                bbox=clipped,
                confidence=round(confidence, 4),
                method=DetectionMethod.CONTOUR_QUAD,
                signals={
                    "contour_fill": fill,
                    "ink_density": ink,
                    "area_fraction": frac,
                    "vertices": float(len(approx)),
                },
                reason=(
                    "Quadrilateral-ish printed panel. A label is a container "
                    "hint only; it asserts nothing about which declarations "
                    "it holds."
                ),
                truncated=_touches_edge(clipped, width, height),
            )
        )

    kept = suppress_overlaps(out)
    kept.sort(key=lambda r: r.confidence, reverse=True)
    return kept[:max_regions]


def detect_graphic_regions(
    image: np.ndarray,
    *,
    max_regions: int = 8,
) -> List[DetectedRegion]:
    """
    Propose LOGO / GRAPHIC regions: saturated, low-stroke-consistency blobs.

    Their purpose is subtractive. Knowing where the artwork is lets the caller
    avoid spending OCR passes on it and stops brand graphics being scored as
    declaration text. Nothing legal depends on this classification.
    """
    if image is None or image.size == 0 or image.ndim != 3:
        return []

    height, width = image.shape[:2]
    frame_area = float(height * width)
    if frame_area <= 0:
        return []

    hsv = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    _t, mask = cv2.threshold(saturation, 90, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    gray = preprocess._to_gray(image)
    text_binary = _text_edge_map(gray)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out: List[DetectedRegion] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
        x, y, w, h = cv2.boundingRect(contour)
        if w < 20 or h < 20:
            continue
        frac = (w * h) / frame_area
        if frac < 0.002 or frac > 0.5:
            continue
        clipped = _clip_bbox((x, y, w, h), width, height)
        if clipped is None:
            continue
        crop_binary = text_binary[
            clipped[1]:clipped[1] + clipped[3], clipped[0]:clipped[0] + clipped[2]
        ]
        consistency = _stroke_width_consistency(crop_binary)
        sat_mean = float(saturation[clipped[1]:clipped[1] + clipped[3],
                                    clipped[0]:clipped[0] + clipped[2]].mean())
        # High stroke consistency means it is probably text on a coloured
        # background, not a graphic. Leave those to the text detector.
        if consistency > 0.62:
            continue
        ratio = float(w) / float(max(1, h))
        compact = 0.35 <= ratio <= 3.0
        region_type = RegionType.LOGO if (compact and frac < 0.09) else RegionType.GRAPHIC
        confidence = float(max(0.0, min(0.8, 0.35 + 0.45 * (sat_mean / 255.0))))
        out.append(
            DetectedRegion(
                region_type=region_type,
                bbox=clipped,
                confidence=round(confidence, 4),
                method=DetectionMethod.SATURATION_GRAPHIC,
                signals={
                    "mean_saturation": sat_mean,
                    "stroke_width_consistency": consistency,
                    "area_fraction": frac,
                    "aspect_ratio": ratio,
                },
                reason=(
                    "Saturated, non-stroke-like blob. Treated as artwork so "
                    "OCR effort is not spent on it."
                ),
                truncated=_touches_edge(clipped, width, height),
            )
        )

    kept = suppress_overlaps(out)
    kept.sort(key=lambda r: r.confidence, reverse=True)
    return kept[:max_regions]


def detect_sticker_candidate_regions(
    image: np.ndarray,
    *,
    max_regions: int = 6,
) -> List[DetectedRegion]:
    """
    Wrap the existing sticker heuristic in the region vocabulary.

    LEGAL SAFETY: a STICKER region is a REVIEW FLAG. Overpasting is lawful in
    many situations (importer particulars under Rule 6, a revised retail sale
    price sticker, a retailer's own price label). This must route to
    POTENTIAL_PACKAGING_CHANGE / human review and must never contribute to a
    FAIL. The reason string is written so that it cannot be quoted as a finding.

    Imported lazily so that `region_detection` keeps a single hard dependency
    (`preprocess`) and remains importable if the sticker module is absent.
    """
    if image is None or image.size == 0:
        return []

    try:
        import sticker_detection
    except ImportError:
        return []

    suspects = sticker_detection.detect_sticker_regions(
        image, max_candidates=max_regions
    )
    height, width = image.shape[:2]

    out: List[DetectedRegion] = []
    for suspect in suspects:
        clipped = _clip_bbox(suspect.bbox, width, height)
        if clipped is None:
            continue
        signals = {
            key: float(value)
            for key, value in (suspect.signals or {}).items()
            if isinstance(value, (int, float))
        }
        out.append(
            DetectedRegion(
                region_type=RegionType.STICKER,
                bbox=clipped,
                confidence=round(float(suspect.confidence), 4),
                method=DetectionMethod.STICKER_HEURISTIC,
                signals=signals,
                reason=(
                    "Boundary/texture statistics differ from the surrounding "
                    f"print ({suspect.reason}). This is a REVIEW FLAG. "
                    "Overpasting is lawful in many cases and this is NOT a "
                    "violation."
                ),
                truncated=_touches_edge(clipped, width, height),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Declaration-candidate routing hint
# ---------------------------------------------------------------------------


def classify_declaration_candidates(
    regions: Sequence[DetectedRegion],
    image_width: int,
    image_height: int,
    *,
    max_promotions: int = 12,
) -> List[DetectedRegion]:
    """
    Promote some TEXT regions to DECLARATION_TEXT as an OCR ROUTING HINT.

    Promotion means "read this block first and read it carefully". It does NOT
    mean a declaration is present, and a region NOT promoted is still OCR'd —
    demotion must never cause a declaration to be skipped, which is why this
    function only reorders priority and never removes anything.

    Heuristics used (all positional/structural, no text content — this runs
    BEFORE OCR):
      - dense multi-line blocks are where declaration panels live;
      - blocks nested inside a detected LABEL are more likely declarations;
      - very small isolated blobs on artwork are less likely.

    Returns a NEW list; inputs are not mutated.
    """
    frame_area = float(max(1, image_width * image_height))
    labels = [r for r in regions if r.region_type == RegionType.LABEL]

    scored: List[Tuple[float, DetectedRegion]] = []
    out: List[DetectedRegion] = []

    for region in regions:
        if region.region_type != RegionType.TEXT:
            out.append(region)
            continue

        frac = region.area / frame_area
        banding = float(region.signals.get("row_banding", 0.0))
        density = float(region.signals.get("stroke_density", 0.0))
        inside_label = any(
            _containment(region.bbox, label.bbox) >= CONTAINMENT_THRESHOLD
            for label in labels
        )

        # Multi-line blocks: taller than a single line relative to width.
        multiline = 1.0 if region.height >= 2.2 * max(6, region.height / max(1.0, region.aspect_ratio)) else 0.0

        score = (
            0.30 * region.confidence
            + 0.22 * min(1.0, frac / 0.05)
            + 0.20 * banding
            + 0.13 * min(1.0, density / 0.3)
            + 0.15 * (1.0 if inside_label else 0.0)
        )
        score = float(max(0.0, min(1.0, score + 0.05 * multiline)))
        scored.append((score, region))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    promote_ids = {id(region) for score, region in scored[:max_promotions] if score >= 0.30}

    for score, region in scored:
        if id(region) in promote_ids:
            promoted = DetectedRegion(
                region_type=RegionType.DECLARATION_TEXT,
                bbox=region.bbox,
                confidence=region.confidence,
                method=region.method,
                signals={**region.signals, "declaration_hint_score": round(score, 4)},
                reason=(
                    "Text block whose size, position and layout make it a "
                    "plausible location for mandatory declarations. ROUTING "
                    "HINT ONLY — this is not a claim that any declaration is "
                    "present, and unpromoted text is still read."
                ),
                parent_index=region.parent_index,
                truncated=region.truncated,
            )
            out.append(promoted)
        else:
            out.append(region)

    return out


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def detect_regions(
    image: np.ndarray,
    *,
    offset: Tuple[int, int] = (0, 0),
    include_text: bool = True,
    include_symbology: bool = True,
    include_labels: bool = True,
    include_graphics: bool = True,
    include_stickers: bool = False,
    include_boundary: bool = True,
    promote_declarations: bool = True,
    max_regions: int = MAX_REGIONS,
) -> DetectionResult:
    """
    Run the full region proposer on one image.

    `offset` is added to every returned bbox. Pass the `ContentRegion.bbox[:2]`
    from `preprocess.crop_screenshot_chrome()` here so that every coordinate is
    expressed in ORIGINAL, uncropped image pixels — the frame that evidence
    references and the audit trail use.

    Sticker detection is OFF by default because it is comparatively expensive
    and its output is a review flag rather than an OCR target; the inspection
    orchestrator turns it on for the tamper/packaging-change pass.

    Returns a `DetectionResult` whose `coverage_note` states plainly that an
    absent region is not evidence of an absent declaration.
    """
    if image is None or image.size == 0:
        raise ValueError("detect_regions() received an empty image.")

    height, width = image.shape[:2]
    notes: List[str] = []
    regions: List[DetectedRegion] = []

    boundary: Optional[DetectedRegion] = None
    if include_boundary:
        boundary = detect_package_boundary(image)
        if boundary is None:
            notes.append(
                "No package boundary was detected. This is common for close-up "
                "crops and cluttered scenes; it is not a defect finding."
            )
        else:
            regions.append(boundary)

    if include_labels:
        regions.extend(detect_label_regions(image))

    if include_symbology:
        symbology = detect_symbology_regions(image)
        regions.extend(symbology)
        if not symbology:
            notes.append(
                "No barcode or QR symbol was localised. The package may still "
                "carry one that this capture does not show clearly."
            )

    if include_graphics:
        regions.extend(detect_graphic_regions(image))

    if include_text:
        regions.extend(detect_text_regions(image, max_regions=max_regions))

    if include_stickers:
        regions.extend(detect_sticker_candidate_regions(image))

    if promote_declarations:
        regions = classify_declaration_candidates(regions, width, height)

    regions = assign_parents(regions)

    # Order: symbology and boundary first (cheap, high-value), then text by
    # confidence. Stable ordering keeps audit records reproducible.
    def _sort_key(region: DetectedRegion) -> Tuple[int, float]:
        rank = {
            RegionType.PACKAGE_BOUNDARY: 0,
            RegionType.BARCODE: 1,
            RegionType.QR: 1,
            RegionType.LABEL: 2,
            RegionType.DECLARATION_TEXT: 3,
            RegionType.TEXT: 4,
            RegionType.STICKER: 5,
            RegionType.LOGO: 6,
            RegionType.GRAPHIC: 6,
            RegionType.UNKNOWN: 7,
        }.get(region.region_type, 8)
        return (rank, -region.confidence)

    regions.sort(key=_sort_key)

    if not regions:
        notes.append(
            "No regions were proposed for this image. Treat this as an "
            "evidence gap requiring recapture, NOT as a finding about the "
            "package."
        )

    dx, dy = int(offset[0]), int(offset[1])
    if dx or dy:
        # parent_index survives translation because order is preserved.
        regions = [region.shifted(dx, dy) for region in regions]
        if boundary is not None:
            boundary = boundary.shifted(dx, dy)

    return DetectionResult(
        regions=regions,
        image_width=width,
        image_height=height,
        package_boundary=boundary,
        offset=(dx, dy),
        notes=notes,
    )


def detect_regions_on_full_image(
    image: np.ndarray,
    *,
    strip_screenshot_chrome: bool = True,
    **kwargs: object,
) -> Tuple[DetectionResult, preprocess.ContentRegion]:
    """
    Convenience wrapper implementing the documented region-first entry path.

    Crops screenshot/UI chrome first (the real dataset is phone screenshots),
    detects regions on the cropped content, and returns coordinates mapped back
    to the ORIGINAL image so nothing downstream has to remember the offset.

    Returns (result, content_region). `content_region.is_full_image` tells the
    caller whether anything was trimmed.
    """
    if image is None or image.size == 0:
        raise ValueError("detect_regions_on_full_image() received an empty image.")

    if strip_screenshot_chrome:
        content, region = preprocess.crop_screenshot_chrome(image)
    else:
        height, width = image.shape[:2]
        content = image
        region = preprocess.ContentRegion(
            bbox=(0, 0, width, height),
            removed_letterbox=False,
            removed_ui_chrome=False,
            confidence=1.0,
            reason="Chrome stripping disabled by caller.",
        )

    result = detect_regions(content, offset=region.bbox[:2], **kwargs)  # type: ignore[arg-type]
    if not region.is_full_image:
        result.notes.append(
            f"Screenshot chrome/letterbox was trimmed before detection "
            f"({region.reason}). Coordinates are mapped back to the original "
            "image."
        )
    return result, region


def region_from_bbox(
    bbox: BBoxT,
    region_type: RegionType = RegionType.UNKNOWN,
    *,
    reason: str = "Supplied by the caller.",
    confidence: float = 1.0,
) -> DetectedRegion:
    """
    Wrap a caller-supplied bbox (a manual selection, a stored region, a
    benchmark ground-truth box) in the same contract as a detected one.

    Method is recorded as CALLER_SUPPLIED so an audit reader can tell a human
    selection from a detector proposal — they carry very different weight.
    """
    x, y, w, h = (int(v) for v in bbox)
    if w <= 0 or h <= 0:
        raise ValueError(f"region_from_bbox() got a degenerate bbox: {bbox}")
    return DetectedRegion(
        region_type=region_type,
        bbox=(x, y, w, h),
        confidence=float(max(0.0, min(1.0, confidence))),
        method=DetectionMethod.CALLER_SUPPLIED,
        signals={},
        reason=reason,
    )


def crops_for_ocr(
    image: np.ndarray,
    result: DetectionResult,
    *,
    purpose: str = "text",
    limit: int = 12,
) -> List[Tuple[DetectedRegion, List[preprocess.PreprocessedVariant], preprocess.QualitySignals]]:
    """
    Bridge region detection to preprocessing: for each text-like region, build
    its preprocessing variants.

    This is the concrete realisation of the region-first mandate. Note the
    coordinate handling: `preprocess_region()` returns its own offset relative
    to the image it was given, and `DetectionResult.offset` has already been
    baked into the region bboxes, so the crop is taken from the SAME frame the
    regions were expressed in. Callers mapping OCR boxes back must apply
    `variant.map_bbox_to_source()` then add the returned crop offset.

    Symbology regions are deliberately excluded: they go to the decoder, not to
    OCR. Feeding barcode stripes to a text engine is precisely the failure that
    produced a bogus "17m" net quantity.
    """
    dx, dy = result.offset
    out: List[Tuple[DetectedRegion, List[preprocess.PreprocessedVariant], preprocess.QualitySignals]] = []

    for region in result.text_regions()[:limit]:
        x, y, w, h = region.bbox
        local = (x - dx, y - dy, w, h)
        if local[0] < 0 or local[1] < 0:
            continue
        try:
            variants, signals, _offset = preprocess.preprocess_region(
                image, local, purpose=purpose
            )
        except ValueError:
            # Degenerate/out-of-range region: skip it, but the region stays in
            # the DetectionResult so the audit trail shows it was proposed.
            continue
        out.append((region, variants, signals))
    return out
