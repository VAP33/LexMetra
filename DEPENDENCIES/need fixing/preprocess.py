"""
Modular, quality-driven image preprocessing for OCR evidence extraction.

Legal-safety contract (read before changing anything here)
----------------------------------------------------------
Preprocessing is an EVIDENCE TRANSFORMATION, not new evidence.

1. The ORIGINAL image is never modified. Every function in this module either
   returns a NEW array or a `PreprocessedVariant` wrapping a new array.
2. Every derived image carries provenance: which method produced it, with what
   parameters, from which source region of which source image.
3. Preprocessing must never be described as "recovering" information that is
   not physically present in the source. If a character is under specular
   glare, no amount of CLAHE makes it legally observed. Downstream code is
   responsible for keeping such a field UNCERTAIN — see `evidence.py`.
4. This module makes NO legal determination. It does not know what MRP is.

Design notes
------------
- Variants are SELECTED from quality signals rather than applied
  combinatorially. Running 12 transforms on every region would be slow and
  would inflate false positives during fusion (more chances for one variant to
  hallucinate a plausible-looking number).
- `RecipeStep` values are stable string codes so that a derived image can be
  reproduced later from an audit record.
- Nothing here imports the rule engine, the OCR engine, or the database. It is
  deliberately a leaf module so it can be unit tested without a live
  environment and replaced by a learned model later.

Real-dataset motivation
-----------------------
The bundled real-photo dataset (`images dataset/`) is phone screenshots of
packaged commodities. Several images contain:
  - black letterbox bars (portrait photo shown in a 9:19.5 screenshot),
  - Android gallery UI chrome (status bar, title bar, filmstrip, action row),
  - curved/cylindrical labels (Bru jar, Pringles can, Thums Up can),
  - spherical labels (Gems ball),
  - specular glare from retail lighting,
  - dense small declaration text with mixed orientation.
`detect_content_region()` and `crop_screenshot_chrome()` exist specifically
because feeding UI chrome into OCR produces confident junk text ("10:10",
"Pune Nanded", "Speed") that must never reach field classification.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Recipe vocabulary
# ---------------------------------------------------------------------------


class RecipeStep(str, Enum):
    """
    Stable identifiers for preprocessing operations.

    These strings are persisted in evidence provenance. Renaming one is a
    breaking change to stored audit records — add a new member instead.
    """

    ORIGINAL = "ORIGINAL"
    GRAYSCALE = "GRAYSCALE"
    UPSCALE = "UPSCALE"
    CONTRAST_STRETCH = "CONTRAST_STRETCH"
    CLAHE = "CLAHE"
    ILLUMINATION_NORMALIZE = "ILLUMINATION_NORMALIZE"
    DENOISE_LIGHT = "DENOISE_LIGHT"
    UNSHARP_MASK = "UNSHARP_MASK"
    ADAPTIVE_THRESHOLD = "ADAPTIVE_THRESHOLD"
    OTSU_THRESHOLD = "OTSU_THRESHOLD"
    INVERT = "INVERT"
    CHANNEL_SELECT = "CHANNEL_SELECT"
    GLARE_SUPPRESS = "GLARE_SUPPRESS"
    PERSPECTIVE_RECTIFY = "PERSPECTIVE_RECTIFY"
    ROTATE_90 = "ROTATE_90"
    ROTATE_180 = "ROTATE_180"
    ROTATE_270 = "ROTATE_270"
    MORPH_OPEN = "MORPH_OPEN"
    BILATERAL = "BILATERAL"


class TextPolarity(str, Enum):
    """Whether text is dark-on-light, light-on-dark, or indeterminate."""

    DARK_ON_LIGHT = "DARK_ON_LIGHT"
    LIGHT_ON_DARK = "LIGHT_ON_DARK"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


# Target text height for OCR, in pixels. Measured against the real dataset:
# Tesseract does best when character height sits in roughly the 20-30 px band,
# and gets WORSE when a region is upscaled past it (interpolation invents
# stroke detail that the engine then mis-segments). Upscaling is therefore
# targeted at this height rather than applied as a fixed multiplier.
TARGET_TEXT_HEIGHT_PX = 26.0

# Ceiling on upscaling. Beyond ~4x, cubic interpolation is fabricating stroke
# structure rather than resolving it, which is exactly the "invent a plausible
# digit" failure mode this pipeline must avoid.
MAX_UPSCALE_FACTOR = 4.0


# ---------------------------------------------------------------------------
# Quality signals
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QualitySignals:
    """
    Region- or image-level quality measurements used to SELECT preprocessing.

    All scores are normalized to [0, 1] with "higher is better" polarity,
    consistent with `image_quality.py`, EXCEPT the explicitly-named
    `*_fraction` fields which are raw fractions where higher means more of the
    named defect.

    These are classical heuristics, not a calibrated perceptual model. They are
    good enough to choose a preprocessing recipe; they are NOT evidence of
    legal compliance and must never be used as such.
    """

    width: int
    height: int
    sharpness: float          # higher = sharper
    exposure: float           # higher = better exposed
    glare: float              # higher = LESS glare (matches image_quality.py)
    contrast: float           # higher = more local contrast
    glare_fraction: float     # raw fraction of blown-highlight pixels
    dark_fraction: float      # raw fraction of near-black pixels
    illumination_unevenness: float   # 0 = flat lighting, 1 = extreme gradient
    estimated_text_height_px: Optional[float]
    polarity: TextPolarity
    is_low_resolution: bool
    notes: Tuple[str, ...] = ()

    @property
    def has_glare_problem(self) -> bool:
        return self.glare < 0.55 or self.glare_fraction > 0.045

    @property
    def has_blur_problem(self) -> bool:
        return self.sharpness < 0.18

    @property
    def has_contrast_problem(self) -> bool:
        return self.contrast < 0.28

    @property
    def has_exposure_problem(self) -> bool:
        return self.exposure < 0.40 or self.dark_fraction > 0.35

    @property
    def has_uneven_illumination(self) -> bool:
        return self.illumination_unevenness > 0.30

    @property
    def has_tiny_text(self) -> bool:
        if self.estimated_text_height_px is None:
            return min(self.width, self.height) < 120
        return self.estimated_text_height_px < TARGET_TEXT_HEIGHT_PX

    def upscale_factor_for_text(self) -> float:
        """
        Factor that would bring measured text height up to the OCR sweet spot.

        Measured on the real dataset: Tesseract's accuracy peaks when x-height
        lands in roughly the 20-30 px band, and DEGRADES above it. Blindly
        applying a fixed 2x or 3x to an already-large region made readings
        worse (a correctly-read "MRP ... 420" became unreadable at 2x). So the
        factor is derived from the measurement rather than fixed, and is capped
        so an aggressive estimate cannot blow the region up.
        """
        if self.estimated_text_height_px is None:
            # No text-like components found. Fall back to a modest bump only
            # when the region is genuinely small.
            return 2.0 if min(self.width, self.height) < 120 else 1.0
        if self.estimated_text_height_px <= 0:
            return 1.0
        factor = TARGET_TEXT_HEIGHT_PX / float(self.estimated_text_height_px)
        return float(max(1.0, min(MAX_UPSCALE_FACTOR, factor)))


@dataclass
class PreprocessedVariant:
    """
    One derived image plus the provenance needed to reproduce and audit it.

    `image` is always a NEW array; callers may not assume it shares memory with
    the source. `recipe` is the ordered list of operations applied. `params`
    records the actual numeric parameters used so the transform is
    reproducible from an audit record alone.
    """

    name: str
    image: np.ndarray
    recipe: Tuple[RecipeStep, ...]
    params: Dict[str, object] = field(default_factory=dict)
    # Scale factor applied relative to the input given to build_variants().
    # Coordinates found in this variant must be divided by these to map back.
    scale_x: float = 1.0
    scale_y: float = 1.0
    # True when the variant is binarised. Binary variants are useful for OCR
    # but destroy information, so fusion weights them slightly lower.
    is_binary: bool = False
    priority: int = 50

    def map_point_to_source(self, x: float, y: float) -> Tuple[float, float]:
        """Map a coordinate found in this variant back to the source image."""
        sx = self.scale_x if self.scale_x else 1.0
        sy = self.scale_y if self.scale_y else 1.0
        return x / sx, y / sy

    def map_bbox_to_source(
        self, bbox: Tuple[float, float, float, float]
    ) -> Tuple[int, int, int, int]:
        """Map an (x, y, w, h) box found in this variant back to the source."""
        x, y, w, h = bbox
        sx = self.scale_x if self.scale_x else 1.0
        sy = self.scale_y if self.scale_y else 1.0
        return (
            int(round(x / sx)),
            int(round(y / sy)),
            max(1, int(round(w / sx))),
            max(1, int(round(h / sy))),
        )

    def provenance(self) -> Dict[str, object]:
        """Serialisable provenance record for audit storage."""
        return {
            "variant_name": self.name,
            "recipe": [step.value for step in self.recipe],
            "params": dict(self.params),
            "scale_x": round(float(self.scale_x), 6),
            "scale_y": round(float(self.scale_y), 6),
            "is_binary": bool(self.is_binary),
        }


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------


def _to_gray(image: np.ndarray) -> np.ndarray:
    """Return a single-channel uint8 copy of `image` (never a view)."""
    if image.ndim == 2:
        return image.copy()
    if image.ndim == 3:
        if image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        if image.shape[2] == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if image.shape[2] == 1:
            return image[:, :, 0].copy()
    raise ValueError(f"Unsupported image shape for grayscale conversion: {image.shape}")


def _ensure_uint8(image: np.ndarray) -> np.ndarray:
    if image.dtype == np.uint8:
        return image
    return np.clip(image, 0, 255).astype(np.uint8)


def image_fingerprint(image: np.ndarray) -> str:
    """
    Stable content hash of an image array.

    Used to prove in an audit trail that a stored original was not altered
    between capture and evaluation. Not a cryptographic guarantee of
    provenance (anyone with write access could recompute it) — it detects
    accidental mutation, which is the actual risk in this pipeline.
    """
    arr = np.ascontiguousarray(image)
    digest = hashlib.sha256()
    digest.update(str(arr.shape).encode("ascii"))
    digest.update(str(arr.dtype).encode("ascii"))
    digest.update(arr.tobytes())
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Screenshot / letterbox chrome removal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContentRegion:
    """
    The sub-rectangle of an image that actually contains photographed content.

    `bbox` is (x, y, w, h) in ORIGINAL image coordinates. Any OCR performed on
    the cropped content must have its coordinates offset by (x, y) before being
    stored as evidence, otherwise provenance points at the wrong pixels.
    """

    bbox: Tuple[int, int, int, int]
    removed_letterbox: bool
    removed_ui_chrome: bool
    confidence: float
    reason: str

    @property
    def is_full_image(self) -> bool:
        return not (self.removed_letterbox or self.removed_ui_chrome)


def _uniform_level_run(
    means: np.ndarray,
    stds: np.ndarray,
    limit: int,
    *,
    tolerance: float,
    level_tolerance: float = 6.0,
) -> int:
    """
    Depth of an edge-anchored band of near-uniform lines at a CONSISTENT level.

    Requiring a consistent level matters: a black letterbox bar sitting above a
    plain light background would otherwise be read as one long "uniform" run
    spanning both, and the combined band's mean lands in the mid-greys, which
    then fails the letterbox test and loses the trim entirely. Breaking the run
    at the intensity step keeps the bar and the background separate.

    Pass reversed arrays to measure from the opposite edge.
    """
    limit = int(min(limit, means.size))
    if limit <= 0 or stds[0] > tolerance:
        return 0

    level = float(means[0])
    depth = 0
    for index in range(limit):
        if stds[index] > tolerance:
            break
        if abs(float(means[index]) - level) > level_tolerance:
            break
        depth += 1
    return depth


def detect_content_region(
    image: np.ndarray,
    *,
    letterbox_tolerance: float = 6.0,
    max_trim_fraction: float = 0.45,
) -> ContentRegion:
    """
    Find the photographed content inside a screenshot or letterboxed image.

    Two distinct artefacts are handled:

    * LETTERBOX BARS -- solid near-uniform (usually black) bands at the top
      and/or bottom (or left/right) of the frame. These are detected as
      contiguous runs of near-zero-variance rows/columns anchored at an edge.

    * UI CHROME -- Android/iOS gallery furniture: status bar, title bar,
      filmstrip, action-button row. These are NOT uniform, so a variance test
      alone will not find them. They are detected as edge-anchored bands whose
      mean intensity and structure differ sharply from the photographic
      interior, and they are only trimmed when the resulting crop still
      contains the dominant photographic content.

    Conservative by design: when in doubt, return the full image. A wrong crop
    silently discards evidence, which is far worse than leaving some chrome in
    frame (chrome text is filtered again later by field classification).

    Returns a `ContentRegion` whose bbox is in ORIGINAL coordinates.
    """
    if image is None or image.size == 0:
        raise ValueError("detect_content_region() received an empty image.")

    gray = _to_gray(image)
    height, width = gray.shape[:2]

    if height < 32 or width < 32:
        return ContentRegion(
            bbox=(0, 0, width, height),
            removed_letterbox=False,
            removed_ui_chrome=False,
            confidence=1.0,
            reason="Image too small to analyse for chrome; using full frame.",
        )

    row_means = gray.mean(axis=1)
    row_stds = gray.std(axis=1)
    col_means = gray.mean(axis=0)
    col_stds = gray.std(axis=0)

    max_trim_rows = int(height * max_trim_fraction)
    max_trim_cols = int(width * max_trim_fraction)

    top = _uniform_level_run(
        row_means, row_stds, max_trim_rows, tolerance=letterbox_tolerance
    )
    bottom = _uniform_level_run(
        row_means[::-1], row_stds[::-1], max_trim_rows, tolerance=letterbox_tolerance
    )
    left = _uniform_level_run(
        col_means, col_stds, max_trim_cols, tolerance=letterbox_tolerance
    )
    right = _uniform_level_run(
        col_means[::-1], col_stds[::-1], max_trim_cols, tolerance=letterbox_tolerance
    )

    # Only trim uniform bands that are actually dark or actually saturated.
    # A uniform mid-grey band is more likely to be part of the photograph
    # (a plain wall, a shelf edge) than a letterbox bar.
    def _band_is_letterbox(band: np.ndarray) -> bool:
        if band.size == 0:
            return False
        mean = float(band.mean())
        # Near-black covers the usual case. The near-white bound is set very
        # high (fully blown out) on purpose: an ordinary light background —
        # a white tabletop, a bright shelf, the light margin of a label — is
        # uniform and bright but is genuinely part of the photograph, and
        # trimming it would silently discard evidence.
        return mean <= 32.0 or mean >= 250.0

    if top and not _band_is_letterbox(gray[:top, :]):
        top = 0
    if bottom and not _band_is_letterbox(gray[height - bottom:, :]):
        bottom = 0
    if left and not _band_is_letterbox(gray[:, :left]):
        left = 0
    if right and not _band_is_letterbox(gray[:, width - right:]):
        right = 0

    removed_letterbox = bool(top or bottom or left or right)

    inner_y0, inner_y1 = top, height - bottom
    inner_x0, inner_x1 = left, width - right

    if inner_y1 - inner_y0 < 32 or inner_x1 - inner_x0 < 32:
        # Trim would destroy the image; abandon it.
        return ContentRegion(
            bbox=(0, 0, width, height),
            removed_letterbox=False,
            removed_ui_chrome=False,
            confidence=0.4,
            reason="Letterbox trim rejected: remaining region too small.",
        )

    # Chrome detection runs on the FULL frame rather than on the
    # letterbox-trimmed interior. Gallery furniture is a stack of alternating
    # dark control rows and a colourful thumbnail filmstrip; the letterbox pass
    # eats the outermost dark rows, which would leave the chrome pass starting
    # mid-filmstrip with no edge-anchored band to find. Measuring from the true
    # edge and then taking whichever trim is deeper keeps both passes honest.
    chrome_top, chrome_bottom = _detect_ui_chrome_bands(gray[:, inner_x0:inner_x1])

    final_y0 = max(inner_y0, chrome_top)
    final_y1 = min(inner_y1, height - chrome_bottom)
    removed_ui_chrome = bool(chrome_top > inner_y0 or chrome_bottom > bottom)

    if final_y1 - final_y0 < max(48, int(height * 0.25)):
        # Chrome trim too aggressive: keep the letterbox result only.
        final_y0, final_y1 = inner_y0, inner_y1
        removed_ui_chrome = False

    reasons: List[str] = []
    if removed_letterbox:
        reasons.append(
            f"Removed uniform letterbox bands (top={top}, bottom={bottom}, "
            f"left={left}, right={right})."
        )
    if removed_ui_chrome:
        reasons.append(
            f"Removed screenshot UI chrome (top={chrome_top}, bottom={chrome_bottom})."
        )
    if not reasons:
        reasons.append("No letterbox or UI chrome detected; using full frame.")

    trimmed_fraction = 1.0 - (
        ((final_y1 - final_y0) * (inner_x1 - inner_x0)) / float(height * width)
    )
    confidence = 0.9 if trimmed_fraction < 0.5 else 0.6

    return ContentRegion(
        bbox=(inner_x0, final_y0, inner_x1 - inner_x0, final_y1 - final_y0),
        removed_letterbox=removed_letterbox,
        removed_ui_chrome=removed_ui_chrome,
        confidence=confidence,
        reason=" ".join(reasons),
    )


def _edge_anchored_run(mask: np.ndarray, limit: int) -> int:
    """Length of the contiguous True run starting at index 0, capped at `limit`."""
    count = 0
    for value in mask[:limit]:
        if not value:
            break
        count += 1
    return count


def _detect_ui_chrome_bands(gray: np.ndarray) -> Tuple[int, int]:
    """
    Detect edge-anchored screenshot UI bands (status/title bar, video controls,
    thumbnail filmstrip, action-button row).

    Two complementary passes, because gallery chrome is not homogeneous:

    * FLATNESS PASS -- a status/title bar is a flat background colour with a
      little text, so its per-row median absolute deviation is far lower than
      that of photographic rows. Compared against the photographic middle of
      the frame rather than an absolute threshold, so it adapts to both bright
      and dark photographs.

    * DARK-CHROME PASS -- video player controls and the thumbnail filmstrip sit
      on a near-black background. Those rows are *not* flat (the thumbnails are
      colourful), but they have a high fraction of near-black pixels, which
      photographic subject rows in this dataset do not. Detected as an
      edge-anchored run of rows whose near-black fraction is high while the
      frame interior's is low.

    Both passes trim only contiguous runs anchored at the top or bottom edge,
    and both require a band of meaningful thickness so that a plain shelf edge
    or a dark tabletop is not mistaken for chrome.

    Returns (rows_to_trim_top, rows_to_trim_bottom) in the coordinates of the
    array passed in.
    """
    height, width = gray.shape[:2]
    if height < 64:
        return 0, 0

    grayf = gray.astype(np.float32)
    max_band = int(height * 0.24)
    min_band = max(8, int(height * 0.02))

    mid_start, mid_end = int(height * 0.35), int(height * 0.65)

    # --- Pass 1: flat status/title bars -----------------------------------
    row_mad = np.median(np.abs(grayf - np.median(gray, axis=1, keepdims=True)), axis=1)
    mid_mad = float(np.median(row_mad[mid_start:mid_end])) if mid_end > mid_start else 0.0
    flat_like = (
        row_mad < (mid_mad * 0.35)
        if mid_mad > 1e-3
        else np.zeros(height, dtype=bool)
    )

    # --- Pass 2: dark video-control / filmstrip chrome --------------------
    dark_fraction_per_row = np.mean(gray <= 45, axis=1)
    mid_dark = (
        float(np.median(dark_fraction_per_row[mid_start:mid_end]))
        if mid_end > mid_start
        else 1.0
    )
    # Only meaningful when the photograph itself is not predominantly black.
    dark_like = (
        dark_fraction_per_row > 0.55
        if mid_dark < 0.35
        else np.zeros(height, dtype=bool)
    )

    chrome_like = flat_like | dark_like

    top = _tolerant_band_depth(chrome_like, max_band)
    bottom = _tolerant_band_depth(chrome_like[::-1], max_band)

    # Require a meaningful band; a couple of flat rows is just a plain surface.
    if top < min_band:
        top = 0
    if bottom < min_band:
        bottom = 0

    return top, bottom


def _tolerant_band_depth(
    chrome_like: np.ndarray, limit: int, *, min_density: float = 0.62
) -> int:
    """
    Depth of an edge-anchored chrome band, tolerating non-chrome rows inside it.

    A strict contiguous run is not enough for real gallery screenshots: the
    bottom furniture is typically a dark action-button row, then a *colourful*
    thumbnail filmstrip, then a dark playback-control bar. The filmstrip breaks
    a contiguous dark/flat run, so a strict scan stops after the first band and
    leaves the filmstrip in frame, where its text and product thumbnails become
    OCR noise.

    Instead we take the deepest depth `d` (from index 0 of the given mask) such
    that at least `min_density` of the first `d` rows are chrome-like AND row
    `d - 1` is itself chrome-like — the latter keeps the boundary on chrome
    rather than slicing into the photograph.

    Pass a reversed mask to measure from the opposite edge.
    """
    limit = int(min(limit, chrome_like.size))
    if limit <= 0:
        return 0

    prefix = np.cumsum(chrome_like[:limit].astype(np.int32))
    best = 0
    for depth in range(1, limit + 1):
        if not chrome_like[depth - 1]:
            continue
        if prefix[depth - 1] / float(depth) >= min_density:
            best = depth
    return best


def crop_screenshot_chrome(image: np.ndarray) -> Tuple[np.ndarray, ContentRegion]:
    """
    Convenience wrapper: detect chrome and return (cropped_copy, region).

    The returned array is a COPY, so the original is never aliased or mutated.
    Callers MUST offset any coordinates discovered in the crop by
    `region.bbox[:2]` before recording them as evidence.
    """
    region = detect_content_region(image)
    x, y, w, h = region.bbox
    return image[y : y + h, x : x + w].copy(), region


# ---------------------------------------------------------------------------
# Quality measurement
# ---------------------------------------------------------------------------


def _estimate_text_height(gray: np.ndarray) -> Optional[float]:
    """
    Estimate the median height in pixels of text-like connected components.

    Returns None when no plausible text components are found. This drives the
    "tiny text -> upscale" decision. It is an estimate for preprocessing
    selection only and is NOT a legal font measurement — legal font height
    requires physical calibration (see the measurement rules in the engine).
    """
    if gray.size == 0:
        return None

    height, width = gray.shape[:2]

    # Adaptive threshold finds strokes under uneven lighting better than Otsu.
    block = max(11, (min(height, width) // 20) | 1)
    try:
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, 5
        )
    except cv2.error:
        return None

    num, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, 8)
    if num <= 1:
        return None

    heights: List[float] = []
    for index in range(1, num):
        x, y, w, h, area = stats[index]
        if h < 4 or h > height * 0.5:
            continue
        if w < 2 or w > width * 0.6:
            continue
        aspect = w / float(h)
        if aspect > 6.0:
            continue
        fill = area / float(max(1, w * h))
        if fill < 0.08 or fill > 0.95:
            continue
        heights.append(float(h))

    if len(heights) < 5:
        return None
    return float(np.median(heights))


def _estimate_polarity(gray: np.ndarray) -> TextPolarity:
    """
    Decide whether text is dark-on-light or light-on-dark.

    Compares the count of dark-stroke vs light-stroke pixels after removing the
    dominant background level. Packages like the Bru jar (white text on dark
    green) and the Thums Up can (white on blue) are LIGHT_ON_DARK; most
    nutrition panels are DARK_ON_LIGHT. Getting this right decides whether an
    inverted threshold variant is worth generating.
    """
    if gray.size == 0:
        return TextPolarity.UNKNOWN

    background = float(np.median(gray))
    darker = float(np.mean(gray < background - 30))
    lighter = float(np.mean(gray > background + 30))

    if darker < 0.005 and lighter < 0.005:
        return TextPolarity.UNKNOWN
    if darker > lighter * 1.8:
        return TextPolarity.DARK_ON_LIGHT
    if lighter > darker * 1.8:
        return TextPolarity.LIGHT_ON_DARK
    return TextPolarity.MIXED


def _illumination_unevenness(gray: np.ndarray) -> float:
    """
    0 = flat lighting, ->1 = strong illumination gradient across the region.

    Measured as the spread of a heavily blurred (low-frequency) version of the
    image, which isolates lighting from texture.
    """
    if gray.size == 0:
        return 0.0
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    low_freq = cv2.GaussianBlur(small, (0, 0), sigmaX=6)
    spread = float(low_freq.max() - low_freq.min())
    return float(max(0.0, min(1.0, spread / 160.0)))


def measure_quality(image: np.ndarray, *, notes: Sequence[str] = ()) -> QualitySignals:
    """
    Measure preprocessing-relevant quality signals for an image or region.

    Polarity conventions match `image_quality.py` so the two modules can be
    reasoned about together: `sharpness`, `exposure`, `glare` and `contrast`
    are all "higher is better".
    """
    if image is None or image.size == 0:
        raise ValueError("measure_quality() received an empty image.")

    gray = _to_gray(image)
    height, width = gray.shape[:2]

    sharpness = float(
        max(0.0, min(1.0, cv2.Laplacian(gray, cv2.CV_64F).var() / 500.0))
    )

    mean_val = float(gray.mean())
    exposure = float(max(0.0, min(1.0, 1.0 - abs(mean_val - 128.0) / 128.0)))

    glare_fraction = float(np.mean(gray >= 250))
    glare = float(max(0.0, min(1.0, 1.0 - glare_fraction * 6.0)))

    dark_fraction = float(np.mean(gray <= 25))

    # Local contrast via standard deviation of a mid-scale high-pass.
    blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=3)
    high_pass = gray.astype(np.float32) - blurred.astype(np.float32)
    contrast = float(max(0.0, min(1.0, float(high_pass.std()) / 28.0)))

    return QualitySignals(
        width=width,
        height=height,
        sharpness=round(sharpness, 4),
        exposure=round(exposure, 4),
        glare=round(glare, 4),
        contrast=round(contrast, 4),
        glare_fraction=round(glare_fraction, 5),
        dark_fraction=round(dark_fraction, 5),
        illumination_unevenness=round(_illumination_unevenness(gray), 4),
        estimated_text_height_px=_estimate_text_height(gray),
        polarity=_estimate_polarity(gray),
        is_low_resolution=min(width, height) < 120,
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# Individual transforms (each returns a NEW array)
# ---------------------------------------------------------------------------


def apply_clahe(
    gray: np.ndarray, *, clip_limit: float = 2.5, tile: int = 8
) -> np.ndarray:
    """Contrast-Limited Adaptive Histogram Equalisation on a grayscale image."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile, tile))
    return clahe.apply(_ensure_uint8(gray))


def normalize_illumination(gray: np.ndarray, *, sigma: float = 25.0) -> np.ndarray:
    """
    Flatten a lighting gradient by dividing out a heavily blurred estimate of
    the illumination field.

    Useful for hand-held retail photos where one side of the package is lit and
    the other is in shadow (common across the real dataset).
    """
    gray = _ensure_uint8(gray)
    background = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma).astype(np.float32)
    background[background < 1.0] = 1.0
    normalized = (gray.astype(np.float32) / background) * float(np.mean(background))
    return np.clip(normalized, 0, 255).astype(np.uint8)


def suppress_glare(gray: np.ndarray, *, threshold: int = 245) -> np.ndarray:
    """
    Reduce the visual dominance of specular highlights.

    IMPORTANT: this does NOT recover text underneath a highlight. Saturated
    pixels carry no information; inpainting them fabricates plausible-looking
    structure. This function only pulls blown highlights down toward local
    surroundings so that neighbouring readable strokes are not crushed by
    subsequent contrast normalisation. Any field whose characters fall inside
    the highlight mask must still be reported UNCERTAIN with a recapture
    recommendation.
    """
    gray = _ensure_uint8(gray)
    mask = (gray >= threshold).astype(np.uint8)
    if not mask.any():
        return gray.copy()

    # Replace saturated pixels with a local median so they stop dominating,
    # then record nothing about their content.
    median = cv2.medianBlur(gray, 7)
    out = gray.copy()
    out[mask == 1] = median[mask == 1]
    return out


def glare_mask(gray: np.ndarray, *, threshold: int = 245, dilate: int = 3) -> np.ndarray:
    """
    Binary mask (uint8 0/255) of specular-highlight pixels.

    Used by the evidence layer to decide whether a declaration region is
    obscured and therefore UNCERTAIN rather than absent.
    """
    gray = _ensure_uint8(gray)
    mask = ((gray >= threshold).astype(np.uint8)) * 255
    if dilate > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate * 2 + 1,) * 2)
        mask = cv2.dilate(mask, kernel)
    return mask


def unsharp_mask(
    gray: np.ndarray, *, sigma: float = 1.2, amount: float = 1.1
) -> np.ndarray:
    """
    Sharpen via unsharp masking.

    Bounded `amount` on purpose: aggressive sharpening on a blurred capture
    manufactures edges that OCR reads as confident wrong characters. A blurred
    region should be REJECTED for recapture, not sharpened until it produces
    something.
    """
    gray = _ensure_uint8(gray)
    blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma)
    sharpened = cv2.addWeighted(gray, 1.0 + amount, blurred, -amount, 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def denoise_light(gray: np.ndarray, *, diameter: int = 5) -> np.ndarray:
    """Edge-preserving light denoise (bilateral) that keeps stroke edges."""
    return cv2.bilateralFilter(_ensure_uint8(gray), diameter, 45, 45)


def contrast_stretch(gray: np.ndarray, *, low_pct: float = 1.0, high_pct: float = 99.0) -> np.ndarray:
    """Linear percentile contrast stretch."""
    gray = _ensure_uint8(gray)
    lo = float(np.percentile(gray, low_pct))
    hi = float(np.percentile(gray, high_pct))
    if hi - lo < 1e-3:
        return gray.copy()
    stretched = (gray.astype(np.float32) - lo) * (255.0 / (hi - lo))
    return np.clip(stretched, 0, 255).astype(np.uint8)


def adaptive_threshold(
    gray: np.ndarray, *, block_size: Optional[int] = None, c: int = 7, invert: bool = False
) -> np.ndarray:
    """
    Adaptive Gaussian threshold, block size scaled to the region.

    `invert=True` produces white-text-on-dark-background handling.
    """
    gray = _ensure_uint8(gray)
    height, width = gray.shape[:2]
    if block_size is None:
        block_size = max(11, (min(height, width) // 12) | 1)
    if block_size % 2 == 0:
        block_size += 1
    mode = cv2.THRESH_BINARY if invert else cv2.THRESH_BINARY_INV
    # NOTE: OCR engines expect dark text on light background. THRESH_BINARY_INV
    # on dark-on-light input yields white strokes on black, so we flip back.
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, mode, block_size, c
    )
    return cv2.bitwise_not(binary)


def otsu_threshold(gray: np.ndarray, *, invert: bool = False) -> np.ndarray:
    """Global Otsu threshold, returning dark-text-on-light output."""
    gray = _ensure_uint8(gray)
    flag = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
    _thresh, binary = cv2.threshold(gray, 0, 255, flag + cv2.THRESH_OTSU)
    return binary


def upscale(
    gray: np.ndarray, *, factor: float = 2.0, max_dimension: int = 3200
) -> Tuple[np.ndarray, float]:
    """
    Upscale for small text, capped so Tesseract input stays manageable.

    Returns (image, actual_factor_applied).
    """
    gray = _ensure_uint8(gray)
    height, width = gray.shape[:2]
    if factor <= 1.0:
        return gray.copy(), 1.0

    largest = max(height, width)
    allowed = max_dimension / float(largest) if largest else factor
    actual = max(1.0, min(factor, allowed))
    if abs(actual - 1.0) < 1e-3:
        return gray.copy(), 1.0

    resized = cv2.resize(
        gray,
        (max(1, int(round(width * actual))), max(1, int(round(height * actual)))),
        interpolation=cv2.INTER_CUBIC,
    )
    return resized, actual


def select_best_channel(image_bgr: np.ndarray) -> Tuple[np.ndarray, str]:
    """
    Pick the colour channel (or derived plane) with the strongest text contrast.

    Coloured packaging often hides text in one channel while another separates
    it cleanly — e.g. white text on the Bru jar's green label separates far
    better in the red channel than in luminance. Candidates include the BGR
    channels, HSV value, and LAB lightness.

    Returns (single_channel_uint8, channel_name).
    """
    if image_bgr.ndim == 2:
        return image_bgr.copy(), "gray"

    candidates: List[Tuple[str, np.ndarray]] = []
    blue, green, red = cv2.split(image_bgr[:, :, :3])
    candidates.extend([("b", blue), ("g", green), ("r", red)])

    hsv = cv2.cvtColor(image_bgr[:, :, :3], cv2.COLOR_BGR2HSV)
    candidates.append(("v", hsv[:, :, 2]))

    lab = cv2.cvtColor(image_bgr[:, :, :3], cv2.COLOR_BGR2LAB)
    candidates.append(("l", lab[:, :, 0]))

    candidates.append(("gray", _to_gray(image_bgr)))

    best_name = "gray"
    best_plane = candidates[-1][1]
    best_score = -1.0

    for name, plane in candidates:
        blurred = cv2.GaussianBlur(plane, (0, 0), sigmaX=3)
        high_pass = plane.astype(np.float32) - blurred.astype(np.float32)
        score = float(high_pass.std())
        if score > best_score:
            best_score = score
            best_name = name
            best_plane = plane

    return _ensure_uint8(best_plane.copy()), best_name


# ---------------------------------------------------------------------------
# Perspective rectification
# ---------------------------------------------------------------------------


def order_corners(points: np.ndarray) -> np.ndarray:
    """
    Order 4 points as top-left, top-right, bottom-right, bottom-left.

    Uses coordinate sums/differences, which is robust for mild rotation. For
    strongly rotated quads the caller should rely on the OCR orientation pass
    rather than assuming this ordering is semantically "upright".
    """
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    ordered = np.zeros((4, 2), dtype=np.float32)

    total = pts.sum(axis=1)
    ordered[0] = pts[int(np.argmin(total))]
    ordered[2] = pts[int(np.argmax(total))]

    diff = np.diff(pts, axis=1).ravel()
    ordered[1] = pts[int(np.argmin(diff))]
    ordered[3] = pts[int(np.argmax(diff))]
    return ordered


def rectify_perspective(
    image: np.ndarray, corners: Sequence[Sequence[float]]
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Warp a detected planar quadrilateral to a front-facing rectangle.

    Returns (rectified_image, inverse_matrix). The inverse matrix maps a point
    in the rectified image back to original image coordinates, which is
    mandatory for evidence provenance:

        src_pt = cv2.perspectiveTransform(rect_pt.reshape(1,1,2), inverse)

    Only valid for genuinely PLANAR surfaces. Applying this to a cylindrical
    label (Bru jar, Pringles can) straightens the label edges but does not undo
    circumferential foreshortening — text near the silhouette stays compressed.
    Callers must keep such geometry marked as NEAR_CYLINDRICAL/UNKNOWN so the
    engine does not treat derived measurements as VERIFIED.
    """
    ordered = order_corners(np.asarray(corners, dtype=np.float32))
    (tl, tr, br, bl) = ordered

    width_top = float(np.linalg.norm(tr - tl))
    width_bottom = float(np.linalg.norm(br - bl))
    height_left = float(np.linalg.norm(bl - tl))
    height_right = float(np.linalg.norm(br - tr))

    out_w = max(8, int(round(max(width_top, width_bottom))))
    out_h = max(8, int(round(max(height_left, height_right))))

    destination = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype=np.float32,
    )

    matrix = cv2.getPerspectiveTransform(ordered, destination)
    inverse = cv2.getPerspectiveTransform(destination, ordered)
    warped = cv2.warpPerspective(
        image, matrix, (out_w, out_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )
    return warped, inverse


# ---------------------------------------------------------------------------
# Recipe selection
# ---------------------------------------------------------------------------

# Hard cap on how many variants any single call may produce. Fusion cost and
# false-positive risk both grow with variant count, so this stays small.
MAX_VARIANTS = 6

# Cap on the number of names `plan_recipes()` returns. One slot below
# MAX_VARIANTS so that `build_variants()` can always add the selected-channel
# variant for a colour image without silently evicting a planned recipe.
MAX_PLANNED_RECIPES = MAX_VARIANTS - 1


def plan_recipes(signals: QualitySignals, *, purpose: str = "text") -> List[str]:
    """
    Choose a small, relevant set of variant names for the measured conditions.

    Returns ordered variant names (highest expected value first). The names map
    to builders in `build_variants()`. Selection rules follow the masterprompt's
    guidance and are deliberately explainable rather than learned:

        low contrast          -> CLAHE, contrast stretch
        uneven illumination   -> illumination normalisation
        glare                 -> glare suppression (+ recapture guidance)
        blur                  -> ONE bounded sharpening attempt
        tiny text             -> upscale
        light-on-dark text    -> inverted threshold
        colour packaging      -> best-channel selection
        clean image           -> stay minimal (original + light binarisation)

    `purpose` allows a caller to bias the plan: "text" (default) for general
    declaration text, "numeric" for MRP/quantity digits where binarisation
    helps most, "barcode" to skip binarisation entirely (the barcode decoder
    prefers grayscale gradients).
    """
    plan: List[str] = ["grayscale"]

    if purpose == "barcode":
        # Binarising a barcode destroys the module-width information the
        # decoder relies on; keep it to gentle contrast work only.
        if signals.has_contrast_problem or signals.has_uneven_illumination:
            plan.append("illumination")
        if signals.has_glare_problem:
            plan.append("glare_suppressed")
        plan.append("upscaled" if signals.has_tiny_text else "sharpened")
        return plan[:MAX_PLANNED_RECIPES]

    if signals.has_tiny_text:
        plan.append("upscaled")

    if signals.has_uneven_illumination or signals.has_exposure_problem:
        plan.append("illumination")

    if signals.has_contrast_problem:
        plan.append("clahe")
    elif signals.polarity in (TextPolarity.LIGHT_ON_DARK, TextPolarity.MIXED):
        # Light-on-dark labels benefit from CLAHE even at decent contrast.
        plan.append("clahe")

    if signals.has_glare_problem:
        plan.append("glare_suppressed")

    if signals.has_blur_problem:
        # Exactly one bounded attempt. If this does not produce a confident
        # reading, the correct answer is recapture, not more sharpening.
        plan.append("sharpened")

    # Binarisation almost always adds value for dense small print, but choose
    # the polarity that matches the measured text.
    if signals.polarity == TextPolarity.LIGHT_ON_DARK:
        plan.append("adaptive_inverted")
    else:
        plan.append("adaptive")

    if purpose == "numeric" and "otsu" not in plan:
        plan.append("otsu")

    # De-duplicate while preserving order.
    seen: set[str] = set()
    ordered: List[str] = []
    for name in plan:
        if name not in seen:
            seen.add(name)
            ordered.append(name)

    return ordered[:MAX_PLANNED_RECIPES]


def build_variants(
    image: np.ndarray,
    *,
    signals: Optional[QualitySignals] = None,
    purpose: str = "text",
    plan: Optional[Sequence[str]] = None,
) -> List[PreprocessedVariant]:
    """
    Build the selected preprocessing variants for an image or region.

    The input array is never modified. The first returned variant always
    corresponds to the unmodified input (as grayscale) so that downstream
    fusion always has an untransformed baseline to compare against.

    Args:
        image:    BGR or grayscale source (an image or a cropped region).
        signals:  precomputed quality signals; measured if omitted.
        purpose:  "text" | "numeric" | "barcode" — biases the recipe plan.
        plan:     explicit variant names, bypassing automatic selection.
                  Used by tests and by the benchmark harness for determinism.

    Returns:
        Ordered list of `PreprocessedVariant`, highest expected value first.
    """
    if image is None or image.size == 0:
        raise ValueError("build_variants() received an empty image.")

    if signals is None:
        signals = measure_quality(image)

    names = list(plan) if plan is not None else plan_recipes(signals, purpose=purpose)

    # An explicit plan is honoured exactly, so tests and the benchmark harness
    # get a deterministic variant list. Automatic selection is free to add the
    # selected-channel variant below.
    explicit_plan = plan is not None

    is_colour = image.ndim == 3 and image.shape[2] >= 3
    base_gray = _to_gray(image)

    variants: List[PreprocessedVariant] = []

    def add(
        name: str,
        img: np.ndarray,
        recipe: Tuple[RecipeStep, ...],
        params: Optional[Dict[str, object]] = None,
        *,
        scale: float = 1.0,
        is_binary: bool = False,
        priority: int = 50,
    ) -> None:
        variants.append(
            PreprocessedVariant(
                name=name,
                image=img,
                recipe=recipe,
                params=params or {},
                scale_x=scale,
                scale_y=scale,
                is_binary=is_binary,
                priority=priority,
            )
        )

    # Baseline is mandatory and always first: an untransformed reference that
    # fusion can compare every derived reading against.
    add(
        "grayscale",
        base_gray,
        (RecipeStep.GRAYSCALE,),
        {},
        priority=100,
    )

    # Working plane: for coloured packaging pick the most text-contrastive
    # channel, which frequently beats luminance on saturated label colours.
    working = base_gray
    channel_name = "gray"
    if is_colour:
        candidate, channel_name = select_best_channel(image)
        if channel_name != "gray":
            working = candidate
        if channel_name != "gray" and not explicit_plan:
            # The selected channel is offered as its own variant, not merely as
            # the input to later transforms. On the real dataset this mattered:
            # on a white-on-green label the blue plane alone read "MRP ... 420"
            # while luminance read neither, and every other planned variant
            # applied a further transform that lost it again. Keeping the plain
            # channel in the ensemble preserves that reading.
            add(
                f"channel_{channel_name}",
                working.copy(),
                (RecipeStep.CHANNEL_SELECT,),
                {"channel": channel_name},
                priority=95,
            )

    for name in names:
        if name == "grayscale":
            continue

        if name == "upscaled":
            factor = signals.upscale_factor_for_text()
            img, actual = upscale(working, factor=factor)
            if actual > 1.0:
                add(
                    "upscaled",
                    img,
                    (RecipeStep.CHANNEL_SELECT, RecipeStep.UPSCALE)
                    if channel_name != "gray"
                    else (RecipeStep.UPSCALE,),
                    {
                        "factor": round(actual, 3),
                        "channel": channel_name,
                        "measured_text_height_px": signals.estimated_text_height_px,
                        "target_text_height_px": TARGET_TEXT_HEIGHT_PX,
                    },
                    scale=actual,
                    priority=90,
                )

        elif name == "illumination":
            img = normalize_illumination(working)
            add(
                "illumination",
                contrast_stretch(img),
                (RecipeStep.ILLUMINATION_NORMALIZE, RecipeStep.CONTRAST_STRETCH),
                {"sigma": 25.0, "channel": channel_name},
                priority=80,
            )

        elif name == "clahe":
            img = apply_clahe(working)
            add(
                "clahe",
                img,
                (RecipeStep.CHANNEL_SELECT, RecipeStep.CLAHE)
                if channel_name != "gray"
                else (RecipeStep.CLAHE,),
                {"clip_limit": 2.5, "tile": 8, "channel": channel_name},
                priority=85,
            )

        elif name == "glare_suppressed":
            img = suppress_glare(working)
            add(
                "glare_suppressed",
                apply_clahe(img, clip_limit=2.0),
                (RecipeStep.GLARE_SUPPRESS, RecipeStep.CLAHE),
                {
                    "threshold": 245,
                    "channel": channel_name,
                    "warning": (
                        "Highlight pixels carry no information; text under "
                        "glare must remain UNCERTAIN."
                    ),
                },
                priority=70,
            )

        elif name == "sharpened":
            img = unsharp_mask(denoise_light(working))
            add(
                "sharpened",
                img,
                (RecipeStep.DENOISE_LIGHT, RecipeStep.UNSHARP_MASK),
                {
                    "sigma": 1.2,
                    "amount": 1.1,
                    "channel": channel_name,
                    "warning": (
                        "Bounded single sharpening attempt; a still-unreadable "
                        "region must be recaptured, not sharpened further."
                    ),
                },
                priority=65,
            )

        elif name == "adaptive":
            prepared = apply_clahe(working) if signals.has_contrast_problem else working
            img = adaptive_threshold(prepared)
            add(
                "adaptive",
                img,
                (RecipeStep.ADAPTIVE_THRESHOLD,),
                {"c": 7, "channel": channel_name},
                is_binary=True,
                priority=75,
            )

        elif name == "adaptive_inverted":
            prepared = apply_clahe(working)
            img = adaptive_threshold(prepared, invert=True)
            add(
                "adaptive_inverted",
                img,
                (RecipeStep.CLAHE, RecipeStep.ADAPTIVE_THRESHOLD, RecipeStep.INVERT),
                {"c": 7, "channel": channel_name, "polarity": signals.polarity.value},
                is_binary=True,
                priority=78,
            )

        elif name == "otsu":
            invert = signals.polarity == TextPolarity.LIGHT_ON_DARK
            img = otsu_threshold(contrast_stretch(working), invert=invert)
            add(
                "otsu",
                img,
                (RecipeStep.CONTRAST_STRETCH, RecipeStep.OTSU_THRESHOLD),
                {"invert": invert, "channel": channel_name},
                is_binary=True,
                priority=60,
            )

    variants.sort(key=lambda v: -v.priority)
    return variants[:MAX_VARIANTS]


def preprocess_region(
    image: np.ndarray,
    bbox: Tuple[int, int, int, int],
    *,
    purpose: str = "text",
    pad: int = 4,
) -> Tuple[List[PreprocessedVariant], QualitySignals, Tuple[int, int]]:
    """
    Crop a region, measure it, and build region-appropriate variants.

    Region-first preprocessing is the point of this module: the recipe that
    reads a glare-covered MRP is not the recipe that reads a dark nutrition
    panel on the same photograph.

    Returns (variants, region_signals, (offset_x, offset_y)). The offset MUST be
    added to any coordinate found in a variant, after that variant's own
    `map_bbox_to_source()`, to obtain original-image coordinates.
    """
    if image is None or image.size == 0:
        raise ValueError("preprocess_region() received an empty image.")

    height, width = image.shape[:2]
    x, y, w, h = bbox

    x0 = max(0, int(x) - pad)
    y0 = max(0, int(y) - pad)
    x1 = min(width, int(x) + int(w) + pad)
    y1 = min(height, int(y) + int(h) + pad)

    if x1 - x0 < 3 or y1 - y0 < 3:
        raise ValueError(f"Region {bbox} is too small to preprocess.")

    crop = image[y0:y1, x0:x1].copy()
    signals = measure_quality(crop)
    variants = build_variants(crop, signals=signals, purpose=purpose)
    return variants, signals, (x0, y0)


def recapture_guidance(signals: QualitySignals, *, field_label: str = "this region") -> List[str]:
    """
    Actionable, human-readable recapture advice derived from quality signals.

    Deliberately phrased as capture instructions, never as legal conclusions.
    "MRP region affected by glare" is a capture problem; it is NOT evidence
    that the MRP declaration is absent.
    """
    advice: List[str] = []

    if signals.has_glare_problem:
        advice.append(
            f"{field_label} is affected by glare or reflection. "
            "Tilt the package or move the light source, then recapture."
        )
    if signals.has_blur_problem:
        advice.append(
            f"{field_label} is not in sharp focus. Hold steady, let the camera "
            "refocus, and recapture."
        )
    if signals.has_tiny_text:
        advice.append(
            f"Text in {field_label} is too small to read reliably. "
            "Move closer and capture a close-up of this area."
        )
    if signals.has_exposure_problem:
        advice.append(
            f"{field_label} is under- or over-exposed. Improve lighting and "
            "avoid strong backlight, then recapture."
        )
    if signals.has_uneven_illumination:
        advice.append(
            f"Lighting across {field_label} is uneven. Even out the light or "
            "change the angle, then recapture."
        )
    if signals.is_low_resolution:
        advice.append(
            f"{field_label} has insufficient resolution for reliable reading. "
            "Capture a dedicated close-up."
        )

    return advice
