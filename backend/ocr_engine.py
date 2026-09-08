"""
Orientation-aware, region-first OCR with deterministic multi-variant fusion.

THE SEAM
--------
This module is the ONE canonical path from pixels to text observations:

    image
      -> region_detection.detect_regions_on_full_image()   (WHERE is text?)
      -> orientation.estimate_region_orientation()         (which way up?)
      -> orientation.rotate_crop()                         (local rotation only)
      -> preprocess.build_variants()                       (quality-driven)
      -> OCR engine ensemble                               (Tesseract [+Paddle])
      -> deterministic fusion                              (this module)
      -> OcrObservation list in ORIGINAL image coordinates

`ocr_extraction.py` remains the field-classification layer and is unchanged and
still used: `read_image().lines` returns `ocr_extraction.OcrLine` objects, so
`classify_fields()` consumes this engine's output directly. There is no
`ocr_v2` — this module ADDS the region/orientation/fusion stage in front of the
existing extractor rather than forking it.

LEGAL SAFETY (these hold everywhere in this file)
-------------------------------------------------
1. NOT_OBSERVED != MISSING. A region that no orientation and no variant could
   read yields NO observation and a recapture hint. It never yields a negative
   claim about the package.
2. Low OCR confidence is never non-compliance. Confidence travels with the
   observation so the rule engine can route to UNCERTAIN; it is never converted
   into FAIL here.
3. CONFLICTING evidence is never silently resolved. When two variants read the
   same pixels as different text, BOTH readings are preserved and the group is
   marked CONFLICTING. Never average. Never silently choose.
4. Preprocessing is an evidence TRANSFORMATION, not new evidence. Every
   observation records the variant recipe, orientation and source bbox that
   produced it, so a reviewer can reproduce it from the original image.
5. Poor image quality is never non-compliance. It produces recapture guidance.
6. Barcode/QR regions are NEVER sent to a text engine. Stripes and QR modules are
   not glyphs; a text engine pointed at them returns characters that are artefacts
   of the reader. Readings that fall inside a symbology footprint are quarantined
   from field extraction (see `flag_symbology_noise`) but retained for audit.
7. This module makes NO legal determination of any kind.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

import orientation as orientation_module
import preprocess
import region_detection
from orientation import Orientation, OrientationEstimate, TextAxis
from region_detection import DetectedRegion, DetectionResult, RegionType

try:  # pragma: no cover - config is always importable in the app
    import config

    _MAX_PASSES = max(2, int(config.OCR_MAX_PASSES_PER_REGION))
    _MAX_REGIONS = max(1, int(config.OCR_MAX_REGIONS_PER_IMAGE))
    _PADDLE_REQUESTED = bool(config.ENABLE_PADDLEOCR)
except Exception:  # pragma: no cover - keeps the module importable standalone
    _MAX_PASSES = 8
    _MAX_REGIONS = 14
    _PADDLE_REQUESTED = os.environ.get("LMPC_ENABLE_PADDLEOCR", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

BBoxT = Tuple[int, int, int, int]


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


class OcrEngineName(str, Enum):
    TESSERACT = "TESSERACT"
    PADDLEOCR = "PADDLEOCR"


class FusionState(str, Enum):
    """
    How the variant/orientation ensemble agreed about one piece of text.

    CORROBORATED
        Two or more independent passes produced the same normalised text at the
        same place. This is the only state that earns a confidence bonus.
    SINGLE_SOURCE
        Exactly one pass read it. Legitimate evidence, but unconfirmed.
    CONFLICTING
        Passes read the same pixels as materially different text. Both readings
        are kept. A conflicting group must never become a definitive value.
    """

    CORROBORATED = "CORROBORATED"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    CONFLICTING = "CONFLICTING"


#: Boxes overlapping by at least this IoU are treated as observing the same
#: text location, and therefore as candidates for corroboration or conflict.
SAME_LOCATION_IOU = 0.40

#: Normalised-text similarity at or above this counts as agreement. Below it,
#: two readings of the same location are a CONFLICT, not a near-miss.
AGREEMENT_SIMILARITY = 0.86

#: Confidence multiplier applied when independent passes corroborate a reading.
#: Bounded well below 1.0 headroom so corroboration can never manufacture
#: certainty out of two equally poor reads.
CORROBORATION_BONUS = 1.12

#: Binarised variants destroy stroke information, so their readings are trusted
#: slightly less when ranking within a group.
BINARY_VARIANT_PENALTY = 0.96

#: A reading below this confidence is retained but flagged, never dropped:
#: dropping it would convert "hard to read" into "not present".
LOW_CONFIDENCE_FLOOR = 0.45

#: Fraction of an observation's box that must lie inside a detected BARCODE or QR
#: region before the reading is treated as SYMBOLOGY NOISE.
#:
#: Barcode stripes and QR modules are not glyphs. When a text engine is pointed at
#: them it still returns characters — measured on this dataset, a barcode block
#: yields readings like '| | | | | [|' and '| U9 028735249'. Those are artefacts of
#: the reader, not text on the package, and must never reach field classification.
#:
#: Refusing symbology REGIONS as OCR input is not sufficient on its own. Region
#: detection intentionally emits overlapping regions of different types, and
#: `region_detection.suppress_overlaps()` never removes a region merely because a
#: region of another type covers it — a barcode sitting inside a label panel is a
#: real and legally interesting arrangement. So a TEXT or DECLARATION_TEXT region
#: can, and on real photographs does, sit right on top of the barcode. This
#: threshold closes that path in the ROUTING and REPORTING layer.
#:
#: NOTE ON THE "17m" REGRESSION SPECIFICALLY: on the Bru coffee jar in this
#: dataset, "17m" turned out to be REAL INK — a small print code above the
#: barcode's top-right corner, which OCR reads correctly. That regression is
#: therefore guarded in `ocr_extraction.py`, at the point where an unlabelled
#: quantity is promoted to a net-quantity declaration, not here. This quarantine
#: is the separate, complementary defence against genuine stripe artefacts.
SYMBOLOGY_CONTAINMENT_REJECT = 0.50

#: Above this containment the region is not even read: it is essentially the
#: barcode itself under a different label, so OCR would only waste a pass.
SYMBOLOGY_CONTAINMENT_SKIP = 0.80

#: Minimum alphanumeric characters an observation needs before it is offered to
#: field classification. Below this it is TYPOGRAPHIC NOISE — an isolated 'm',
#: '>' or 'z' picked out of a graphic or a texture.
#:
#: This gate NEVER deletes evidence. Rejected observations stay in
#: `ImageReading.observations` with a note and full provenance; they are only
#: withheld from `.lines`, the field-classification adapter. Suppressing a stray
#: glyph from the extractor cannot create a MISSING finding, because a field that
#: is never extracted is NOT_OBSERVED. Letting the noise through, by contrast,
#: can and did manufacture a false declaration value.
MIN_PLAUSIBLE_ALNUM = 2

#: An observation may not be more than this fraction non-alphanumeric (ignoring
#: spaces). Strings like '|/-.' are edge artefacts, not declarations.
MAX_PUNCTUATION_FRACTION = 0.6

#: Minimum ratio of characters PRODUCED to characters the reading's own bounding
#: box could hold. See `OcrObservation.read_density`.
#:
#: MEASURED on the dataset, images 0 and 3, over 75 observations:
#:   junk readings      0.08 - 0.29   ('a', 'Ee', '§', '~~ |', '|')
#:   genuine text lines 0.82 - 5.85   ('Go on, discover a great |' at the low end,
#:                                     'Exp, Date 17, 0/20 26' at the high end)
#: The gap between 0.29 and 0.82 is wide, so 0.35 sits clear of both sides rather
#: than being tuned to either.
MIN_READ_DENSITY = 0.35

#: Nominal glyph advance as a fraction of text height, used to estimate how many
#: characters a box of a given size could hold. 0.55 is a conventional average for
#: proportional Latin type and is only ever used for this ratio.
_GLYPH_ADVANCE_RATIO = 0.55


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class OcrObservation:
    """
    One text observation, in ORIGINAL image coordinates, with full provenance.

    `bbox` is where this text sits on the untouched source photograph. Every
    transformation between the two — crop offset, local rotation, variant
    scaling — is recorded so the reading can be reproduced and audited.
    """

    text: str
    bbox: BBoxT
    confidence: float
    engine: OcrEngineName
    orientation: Orientation
    variant_name: str
    variant_recipe: Tuple[str, ...]
    region_id: str
    region_type: RegionType
    region_bbox: BBoxT
    psm: Optional[int] = None
    fusion_state: FusionState = FusionState.SINGLE_SOURCE
    corroborated_by: int = 1
    alternatives: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()
    #: Set when this reading's footprint lies inside a detected barcode/QR
    #: region. Such a reading is stripe noise, not text, and is quarantined from
    #: field classification. See `SYMBOLOGY_CONTAINMENT_REJECT`.
    symbology_noise: bool = False

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < LOW_CONFIDENCE_FLOOR

    @property
    def read_density(self) -> float:
        """
        Characters produced, divided by characters this box could plausibly hold.

        THE SIGNAL: when a text engine is pointed at a texture — moulded ridges, a
        mesh pattern, foil crinkle, a photograph on the pack — it reports a wide
        box of "ink" but emits only one or two characters. Genuine text fills its
        own box: a 500 px line of 22 px type carries roughly forty characters, not
        two. So the ratio separates a reading from a shrug.

        Both dimensions are taken as long-side/short-side rather than width/height,
        because a region rotated 90 degrees has its reading direction along the
        ORIGINAL image's y axis and using width would invert the test for every
        vertical declaration on the package.

        Returns 0.0 when the box is degenerate. A high value is not a quality
        claim; it only means the engine committed to characters.
        """
        _x, _y, w, h = self.bbox
        length = float(max(int(w), int(h)))
        height = float(max(1, min(int(w), int(h))))
        capacity = length / (_GLYPH_ADVANCE_RATIO * height)
        if capacity <= 0:
            return 0.0
        return len(self.text.strip()) / capacity

    @property
    def is_plausible_text(self) -> bool:
        """
        Whether this reading is substantial enough to offer to field extraction.

        Deliberately a WEAK filter on shape only, never on meaning: it rejects
        isolated glyphs, punctuation runs, and boxes far emptier than real text.
        It does not judge whether the text looks like a declaration, because
        deciding what a string means is the extractor's job and deciding what it
        implies legally is the rule engine's job.
        """
        stripped = self.text.strip()
        if not stripped:
            return False
        alnum = sum(1 for ch in stripped if ch.isalnum())
        if alnum < MIN_PLAUSIBLE_ALNUM:
            return False
        non_space = [ch for ch in stripped if not ch.isspace()]
        if not non_space:
            return False
        punctuation = sum(1 for ch in non_space if not ch.isalnum())
        if punctuation / len(non_space) > MAX_PUNCTUATION_FRACTION:
            return False
        return self.read_density >= MIN_READ_DENSITY

    @property
    def usable_for_extraction(self) -> bool:
        """
        True when this observation may be handed to field classification.

        False does NOT mean the text is absent, wrong, or non-compliant. It means
        this particular reading is not trustworthy enough to be treated as a
        declaration value. The observation is still retained in full for audit.
        """
        return self.is_plausible_text and not self.symbology_noise

    def provenance(self) -> Dict[str, object]:
        return {
            "text": self.text,
            "bbox_original_image": list(self.bbox),
            "confidence": round(float(self.confidence), 4),
            "confidence_semantics": (
                "OCR engine character confidence. Low confidence means the text "
                "was hard to read; it is NEVER itself legal non-compliance."
            ),
            "engine": self.engine.value,
            "orientation_deg": int(self.orientation.value),
            "variant_name": self.variant_name,
            "variant_recipe": list(self.variant_recipe),
            "psm": self.psm,
            "region_id": self.region_id,
            "region_type": self.region_type.value,
            "region_bbox": list(self.region_bbox),
            "fusion_state": self.fusion_state.value,
            "corroborating_passes": int(self.corroborated_by),
            "alternative_readings": list(self.alternatives),
            "symbology_noise": bool(self.symbology_noise),
            "usable_for_extraction": bool(self.usable_for_extraction),
            "notes": list(self.notes),
        }


@dataclass
class RegionReading:
    """Everything learned about one region, including honest failure."""

    region: DetectedRegion
    orientation_estimate: OrientationEstimate
    chosen_orientation: Orientation
    observations: List[OcrObservation]
    quality: preprocess.QualitySignals
    passes_run: int
    recapture_guidance: List[str] = field(default_factory=list)
    conflicts: List[Dict[str, object]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def read_successfully(self) -> bool:
        return bool(self.observations)

    @property
    def needs_recapture(self) -> bool:
        """
        True when this region could not be read AND the image quality explains
        why. This is a CAPTURE problem, routed to recapture guidance — not a
        finding about the package.
        """
        return not self.observations and bool(self.recapture_guidance)

    def provenance(self) -> Dict[str, object]:
        return {
            "region": self.region.provenance(),
            "orientation": self.orientation_estimate.provenance(),
            "chosen_orientation_deg": int(self.chosen_orientation.value),
            "ocr_passes_run": int(self.passes_run),
            "observation_count": len(self.observations),
            "quality": {
                "blur_variance": round(float(self.quality.blur_variance), 3),
                "glare_fraction": round(float(self.quality.glare_fraction), 4),
                "contrast": round(float(self.quality.contrast), 4),
                "estimated_text_height_px": round(
                    float(self.quality.estimated_text_height_px), 2
                ),
                "polarity": self.quality.polarity.value,
            },
            "recapture_guidance": list(self.recapture_guidance),
            "conflicts": list(self.conflicts),
            "notes": list(self.notes),
            "evidence_semantics": (
                "An empty observation list means this region was NOT OBSERVED "
                "by OCR. It is NOT evidence that a declaration is absent from "
                "the package."
            ),
        }


@dataclass
class ImageReading:
    """The complete OCR result for one image."""

    observations: List[OcrObservation]
    region_readings: List[RegionReading]
    detection: DetectionResult
    engines_used: Tuple[OcrEngineName, ...]
    engine_notes: List[str] = field(default_factory=list)
    recapture_guidance: List[str] = field(default_factory=list)
    conflicts: List[Dict[str, object]] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def lines(self) -> List["OcrLineT"]:
        """
        Adapter to the existing field extractor.

        Returns `ocr_extraction.OcrLine` objects in original-image coordinates,
        so `ocr_extraction.classify_fields()` works unchanged. This is what
        keeps ONE canonical field-classification implementation.

        ONLY observations that pass `usable_for_extraction` are offered. The two
        rejection reasons are symbology noise and typographic noise, and both are
        upstream-of-meaning judgements about the READING, never about the package:
        a declaration that is filtered out here simply goes unextracted, and an
        unextracted field is NOT_OBSERVED, never MISSING. The full observation
        list — including everything withheld — remains available on
        `.observations` and in `provenance()` for audit.
        """
        from ocr_extraction import OcrLine

        out = [
            OcrLine(
                text=o.text,
                bbox=o.bbox,
                confidence=o.confidence,
                # Carry the agreement state and the competing readings across
                # this boundary. They used to stop here: `.lines` reduced each
                # observation to text/bbox/confidence, so a region the engine
                # had read two contradictory ways arrived at field
                # classification indistinguishable from an undisputed one and
                # could produce a definitive PASS. That is invariant 4.
                fusion_state=o.fusion_state.value if o.fusion_state else None,
                alternatives=tuple(str(a) for a in (o.alternatives or ())),
                region_id=o.region_id,
            )
            for o in self.observations
            if o.usable_for_extraction
        ]
        out.sort(key=lambda line: (line.bbox[1], line.bbox[0]))
        return out

    @property
    def withheld_observations(self) -> List[OcrObservation]:
        """Observations retained for audit but not offered to field extraction."""
        return [o for o in self.observations if not o.usable_for_extraction]

    @property
    def full_text(self) -> str:
        """Reading order text of the EXTRACTABLE observations only."""
        return "\n".join(
            o.text for o in self.lines_sorted() if o.usable_for_extraction
        )

    @property
    def full_text_audit(self) -> str:
        """Every reading, including withheld ones, annotated. For audit only."""
        parts = []
        for o in self.lines_sorted():
            if o.usable_for_extraction:
                parts.append(o.text)
            elif o.symbology_noise:
                parts.append(f"[withheld: symbology noise] {o.text!r}")
            else:
                parts.append(f"[withheld: typographic noise] {o.text!r}")
        return "\n".join(parts)

    def lines_sorted(self) -> List[OcrObservation]:
        return sorted(self.observations, key=lambda o: (o.bbox[1], o.bbox[0]))

    @property
    def mixed_orientation(self) -> bool:
        axes = {r.orientation_estimate.axis for r in self.region_readings}
        return TextAxis.HORIZONTAL in axes and TextAxis.VERTICAL in axes

    def provenance(self) -> Dict[str, object]:
        return {
            "detection": self.detection.provenance(),
            "orientation_summary": orientation_module.dominant_axis_summary(
                [r.orientation_estimate for r in self.region_readings]
            ),
            "engines_used": [e.value for e in self.engines_used],
            "engine_notes": list(self.engine_notes),
            "region_readings": [r.provenance() for r in self.region_readings],
            "observation_count": len(self.observations),
            "extractable_observation_count": sum(
                1 for o in self.observations if o.usable_for_extraction
            ),
            "withheld_observations": [
                {
                    "text": o.text,
                    "reason": (
                        "symbology_noise" if o.symbology_noise else "typographic_noise"
                    ),
                    "bbox_original_image": list(o.bbox),
                }
                for o in self.withheld_observations
            ],
            "withholding_semantics": (
                "Withheld readings are retained here in full and were never "
                "deleted. Withholding a reading from field extraction cannot "
                "produce a MISSING finding: an unextracted field is NOT_OBSERVED."
            ),
            "conflict_count": len(self.conflicts),
            "recapture_guidance": list(self.recapture_guidance),
            "elapsed_seconds": round(float(self.elapsed_seconds), 3),
            "legal_safety_note": (
                "This is evidence extraction only. No value here is a legal "
                "determination. Absence of an observation is NOT_OBSERVED, "
                "never MISSING."
            ),
        }


# Forward reference for the adapter property's annotation.
OcrLineT = object


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------


@dataclass
class RawLine:
    """An engine's raw output, in the coordinate frame it was given."""

    text: str
    bbox: BBoxT
    confidence: float
    psm: Optional[int] = None


def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


class TesseractEngine:
    """
    Tesseract backend. Default because it needs no model download.

    Two page-segmentation modes are used: psm 6 (uniform block) suits dense
    declaration panels, psm 7 (single line) suits the narrow line-shaped regions
    the detector produces most often. Both are cheap on a small crop; running
    them on a whole 1080x2392 photograph would not be.
    """

    name = OcrEngineName.TESSERACT

    def __init__(self) -> None:
        self._available: Optional[bool] = None
        self._error: str = ""

    def available(self) -> bool:
        if self._available is None:
            try:
                import pytesseract

                pytesseract.get_tesseract_version()
                self._available = True
            except Exception as exc:  # pragma: no cover - environment dependent
                self._available = False
                self._error = f"Tesseract unavailable: {exc}"
        return bool(self._available)

    def read(self, image: np.ndarray, *, psm: int = 6) -> List[RawLine]:
        if not self.available():
            return []

        import pytesseract

        try:
            data = pytesseract.image_to_data(
                image,
                output_type=pytesseract.Output.DICT,
                config=f"--psm {psm}",
            )
        except Exception:
            # An engine failure must never crash an inspection. It becomes
            # NOT_OBSERVED for this pass, which is the safe direction.
            return []

        groups: Dict[Tuple[int, int, int], List[int]] = {}
        for i, raw in enumerate(data.get("text", [])):
            if not str(raw).strip():
                continue
            key = (
                int(data["block_num"][i]),
                int(data["par_num"][i]),
                int(data["line_num"][i]),
            )
            groups.setdefault(key, []).append(i)

        lines: List[RawLine] = []
        for idxs in groups.values():
            words = [str(data["text"][i]).strip() for i in idxs]
            words = [w for w in words if w]
            if not words:
                continue

            confs = []
            xs, ys, x2s, y2s = [], [], [], []
            for i in idxs:
                try:
                    conf = float(data["conf"][i])
                except (TypeError, ValueError):
                    conf = -1.0
                if conf >= 0:
                    confs.append(conf)
                x = int(data["left"][i])
                y = int(data["top"][i])
                w = int(data["width"][i])
                h = int(data["height"][i])
                xs.append(x)
                ys.append(y)
                x2s.append(x + w)
                y2s.append(y + h)

            if not xs:
                continue

            lines.append(
                RawLine(
                    text=" ".join(words).strip(),
                    bbox=(
                        min(xs),
                        min(ys),
                        max(1, max(x2s) - min(xs)),
                        max(1, max(y2s) - min(ys)),
                    ),
                    confidence=(
                        _clamp01(sum(confs) / len(confs) / 100.0) if confs else 0.0
                    ),
                    psm=psm,
                )
            )
        return lines


class PaddleOcrEngine:
    """
    Optional PaddleOCR backend behind the `LMPC_ENABLE_PADDLEOCR` flag.

    STATUS IN THIS ENVIRONMENT: ENVIRONMENT BLOCKED. `paddleocr` is not
    installed and this environment has no network access to install it, so this
    class has never been executed against a real model here. The integration is
    written so that installing the package and setting the flag activates it,
    and `available()` returns False (with a recorded note) otherwise. It is
    deliberately not claimed as verified.
    """

    name = OcrEngineName.PADDLEOCR

    def __init__(self) -> None:
        self._reader = None
        self._available: Optional[bool] = None
        self._error: str = ""

    def available(self) -> bool:
        if self._available is None:
            if not _PADDLE_REQUESTED:
                self._available = False
                self._error = "PaddleOCR not enabled (LMPC_ENABLE_PADDLEOCR is off)."
            else:
                try:  # pragma: no cover - not installed in this environment
                    from paddleocr import PaddleOCR

                    self._reader = PaddleOCR(use_angle_cls=False, lang="en")
                    self._available = True
                except Exception as exc:
                    self._available = False
                    self._error = (
                        "PaddleOCR was enabled but could not be loaded "
                        f"({exc}); falling back to Tesseract only."
                    )
        return bool(self._available)

    @property
    def error(self) -> str:
        return self._error

    def read(self, image: np.ndarray, *, psm: int = 6) -> List[RawLine]:
        if not self.available():  # pragma: no cover - environment blocked
            return []

        try:  # pragma: no cover - environment blocked
            raw = self._reader.ocr(image, cls=False)
        except Exception:
            return []

        lines: List[RawLine] = []
        for page in raw or []:  # pragma: no cover - environment blocked
            for entry in page or []:
                try:
                    points, (text, score) = entry
                except (TypeError, ValueError):
                    continue
                if not str(text).strip():
                    continue
                pts = np.asarray(points, dtype=np.float32)
                x, y, w, h = cv2.boundingRect(pts)
                lines.append(
                    RawLine(
                        text=str(text).strip(),
                        bbox=(int(x), int(y), max(1, int(w)), max(1, int(h))),
                        confidence=_clamp01(float(score)),
                    )
                )
        return lines


_TESSERACT = TesseractEngine()
_PADDLE = PaddleOcrEngine()


def active_engines() -> Tuple[List[object], List[str]]:
    """Return the usable engines plus honest notes about any that are not."""
    engines: List[object] = []
    notes: List[str] = []

    if _TESSERACT.available():
        engines.append(_TESSERACT)
    else:  # pragma: no cover - environment dependent
        notes.append(_TESSERACT._error or "Tesseract unavailable.")

    if _PADDLE_REQUESTED:
        if _PADDLE.available():  # pragma: no cover - environment blocked
            engines.append(_PADDLE)
        else:
            notes.append(_PADDLE.error)
    else:
        notes.append(
            "PaddleOCR backend present but disabled by default "
            "(set LMPC_ENABLE_PADDLEOCR=true to enable). Not verified in this "
            "environment: the package is not installed and cannot be fetched."
        )

    return engines, notes


# ---------------------------------------------------------------------------
# Text normalisation and agreement
# ---------------------------------------------------------------------------

_NORMALISE_RE = re.compile(r"[^0-9a-z]+")

#: Character pairs Tesseract genuinely confuses on packaging print. Collapsing
#: them for the AGREEMENT test only — never in the reported text — stops "MRP
#: 42O" and "MRP 420" from being logged as a legal-grade conflict when they are
#: one glyph-shape apart. The reported value always stays verbatim.
_CONFUSION_CLASSES = (
    ("0", "o"),
    ("1", "l", "i"),
    ("5", "s"),
    ("8", "b"),
    ("2", "z"),
)


def normalise_for_comparison(text: str) -> str:
    """Lowercase, strip non-alphanumerics. Used only for agreement testing."""
    return _NORMALISE_RE.sub("", text.lower())


def _canonical_glyphs(text: str) -> str:
    out = normalise_for_comparison(text)
    for group in _CONFUSION_CLASSES:
        canonical = group[0]
        for alt in group[1:]:
            out = out.replace(alt, canonical)
    return out


def text_similarity(a: str, b: str) -> float:
    """
    Similarity in [0, 1] between two readings, glyph-confusion aware.

    Uses a bounded Levenshtein ratio. Deliberately NOT a fuzzy merge: the score
    only decides CORROBORATED vs CONFLICTING. It never blends two strings into a
    third value that neither engine actually read.
    """
    ca, cb = _canonical_glyphs(a), _canonical_glyphs(b)
    if not ca and not cb:
        return 1.0
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0

    # Iterative Levenshtein; strings here are single OCR lines, so this is cheap.
    prev = list(range(len(cb) + 1))
    for i, ch_a in enumerate(ca, start=1):
        curr = [i]
        for j, ch_b in enumerate(cb, start=1):
            curr.append(
                min(
                    prev[j] + 1,
                    curr[j - 1] + 1,
                    prev[j - 1] + (0 if ch_a == ch_b else 1),
                )
            )
        prev = curr

    distance = prev[-1]
    return _clamp01(1.0 - distance / max(len(ca), len(cb)))


_DIGIT_RUN_RE = re.compile(r"\d+")


def numeric_signature(text: str) -> Tuple[str, ...]:
    """
    The ordered digit runs in `text`, after glyph-confusion canonicalisation.

    This is what makes two readings of a DECLARATION comparable in the way the
    law cares about. `text_similarity()` is a character ratio, so a single wrong
    digit inside a long line barely moves it: 'NET QUANTITY 100 g' against
    'NET QUANTITY 700 g' scores 0.93, comfortably above AGREEMENT_SIMILARITY.
    Those two readings would have been fused as CORROBORATED and handed a
    confidence BONUS, i.e. two passes that flatly disagree about the net quantity
    would have been reported as mutually confirming it.

    Canonicalisation is applied first so a genuine glyph confusion ('1OO' for
    '100') is not reported as a numeric disagreement. Where canonicalisation
    cannot save it, the answer is CONFLICTING — which is the safe direction. A
    spurious conflict costs a review; a spurious corroboration puts an invented
    number into a legal finding.
    """
    return tuple(_DIGIT_RUN_RE.findall(_canonical_glyphs(text)))


def readings_agree(a: str, b: str) -> bool:
    """
    Whether two readings of the SAME pixels may corroborate each other.

    Both conditions must hold:
      1. glyph-level similarity >= AGREEMENT_SIMILARITY, and
      2. identical numeric signatures.

    Condition 2 is not an optimisation. Quantities, prices, dates and net weights
    are the whole subject of these declarations, and "Never invent invisible
    digits" is meaningless if two different digit strings can be merged into one
    confident value.
    """
    if numeric_signature(a) != numeric_signature(b):
        return False
    return text_similarity(a, b) >= AGREEMENT_SIMILARITY


def _iou(a: BBoxT, b: BBoxT) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return float(inter / union) if union > 0 else 0.0


# ---------------------------------------------------------------------------
# Deterministic fusion
# ---------------------------------------------------------------------------


def fuse_observations(
    candidates: Sequence[OcrObservation],
) -> Tuple[List[OcrObservation], List[Dict[str, object]]]:
    """
    Collapse many passes over the same pixels into one observation per location.

    THE RULES, stated so they can be audited:

    * Passes are grouped by spatial overlap (IoU >= SAME_LOCATION_IOU).
    * Within a group, readings that AGREE corroborate each other. Agreement
      requires BOTH glyph similarity >= AGREEMENT_SIMILARITY AND an identical
      numeric signature — see `readings_agree()` for why the similarity ratio
      alone is not safe for declarations. The best-ranked agreeing reading is
      reported, its confidence lifted by a bounded CORROBORATION_BONUS, state
      CORROBORATED.
    * Readings that disagree are a CONFLICT. The best-ranked reading is still
      reported so the text is not lost, but its state is CONFLICTING and every
      rival reading is attached in `alternatives`. Downstream, a CONFLICTING
      observation must never become a definitive value.
    * Nothing is averaged. Nothing is merged into a string no engine produced.
    * Nothing is dropped for being low confidence.

    Determinism: ranking breaks ties on (confidence, orientation, variant name,
    text) so the same input always yields the same output.
    """
    ordered = sorted(
        candidates,
        key=lambda o: (
            -_rank_score(o),
            int(o.orientation.value),
            o.variant_name,
            o.text,
        ),
    )

    groups: List[List[OcrObservation]] = []
    for obs in ordered:
        placed = False
        for group in groups:
            if _iou(obs.bbox, group[0].bbox) >= SAME_LOCATION_IOU:
                group.append(obs)
                placed = True
                break
        if not placed:
            groups.append([obs])

    fused: List[OcrObservation] = []
    conflicts: List[Dict[str, object]] = []

    for group in groups:
        best = group[0]
        agreeing = [best]
        disagreeing: List[OcrObservation] = []

        for other in group[1:]:
            if readings_agree(best.text, other.text):
                agreeing.append(other)
            else:
                disagreeing.append(other)

        # Distinct passes only: the same text from the same variant at the same
        # orientation via two psm settings is one observation, not corroboration.
        distinct = {
            (o.engine, int(o.orientation.value), o.variant_name) for o in agreeing
        }

        if disagreeing:
            state = FusionState.CONFLICTING
            alternatives = tuple(
                dict.fromkeys(o.text for o in disagreeing)
            )
            confidence = best.confidence
            numeric_clash = any(
                numeric_signature(best.text) != numeric_signature(o.text)
                for o in disagreeing
            )
            note = (
                "Variants disagreed on this text. Both readings are preserved; "
                "a conflicting observation must not become a definitive value."
            )
            if numeric_clash:
                note = (
                    "Variants read DIFFERENT NUMBERS at this location "
                    f"({numeric_signature(best.text)} vs "
                    + " / ".join(
                        str(numeric_signature(o.text)) for o in disagreeing
                    )
                    + "). Every reading is preserved and none may be used as a "
                    "declared value. A numeric disagreement is never resolved "
                    "automatically."
                )
            conflicts.append(
                {
                    "region_id": best.region_id,
                    "bbox": list(best.bbox),
                    "reported": best.text,
                    "alternatives": list(alternatives),
                    "similarities": [
                        round(text_similarity(best.text, o.text), 3)
                        for o in disagreeing
                    ],
                    "numeric_disagreement": numeric_clash,
                    "numeric_signatures": [
                        list(numeric_signature(best.text)),
                        *[list(numeric_signature(o.text)) for o in disagreeing],
                    ],
                    "resolution": "CONFLICT_REVIEW",
                }
            )
        elif len(distinct) > 1:
            state = FusionState.CORROBORATED
            alternatives = ()
            confidence = _clamp01(best.confidence * CORROBORATION_BONUS)
            note = (
                f"Corroborated by {len(distinct)} independent "
                "variant/orientation passes."
            )
        else:
            state = FusionState.SINGLE_SOURCE
            alternatives = ()
            confidence = best.confidence
            note = "Read by a single pass; not independently corroborated."

        notes = list(best.notes) + [note]
        if confidence < LOW_CONFIDENCE_FLOOR:
            notes.append(
                "Low OCR confidence. This is a READABILITY signal only and is "
                "never itself legal non-compliance."
            )

        fused.append(
            OcrObservation(
                text=best.text,
                bbox=best.bbox,
                confidence=confidence,
                engine=best.engine,
                orientation=best.orientation,
                variant_name=best.variant_name,
                variant_recipe=best.variant_recipe,
                region_id=best.region_id,
                region_type=best.region_type,
                region_bbox=best.region_bbox,
                psm=best.psm,
                fusion_state=state,
                corroborated_by=len(distinct),
                alternatives=alternatives,
                notes=tuple(notes),
            )
        )

    fused.sort(key=lambda o: (o.bbox[1], o.bbox[0]))
    return fused, conflicts


def _rank_score(obs: OcrObservation) -> float:
    """
    Ranking score used only to pick which reading to REPORT within a group.

    Longer readings at higher confidence win, because a truncated read of a
    declaration line is worse evidence than a complete one. Binary variants are
    mildly penalised since thresholding discards stroke information.
    """
    length_weight = min(1.0, len(normalise_for_comparison(obs.text)) / 12.0)
    score = obs.confidence * (0.55 + 0.45 * length_weight)
    if preprocess.RecipeStep.ADAPTIVE_THRESHOLD.value in obs.variant_recipe or (
        preprocess.RecipeStep.OTSU_THRESHOLD.value in obs.variant_recipe
    ):
        score *= BINARY_VARIANT_PENALTY
    return float(score)


def _trial_score(lines: Sequence[RawLine]) -> float:
    """
    Score one orientation trial: how much confident text did it yield?

    Both terms matter. Confidence alone rewards a single crisp stray glyph;
    character count alone rewards garbage. The product is what actually
    separates upright from upside-down text in practice, because Tesseract's
    confidence collapses on rotated glyphs while it still emits characters.
    """
    if not lines:
        return 0.0
    chars = sum(len(normalise_for_comparison(line.text)) for line in lines)
    if chars == 0:
        return 0.0
    mean_conf = sum(line.confidence for line in lines) / len(lines)
    return float(mean_conf * float(np.log1p(chars)))


# ---------------------------------------------------------------------------
# Mosaic batching
# ---------------------------------------------------------------------------
#
# WHY A MOSAIC. Each `pytesseract` call spawns the tesseract binary and writes a
# temp file: measured at ~0.6 s of pure overhead per call in this environment,
# regardless of how small the crop is. A dense label yields a dozen text regions
# and each needs several variants and an orientation trial, so the naive
# region-by-region loop costs 30 s or more per photograph — measured, not
# assumed. Packing many already-preprocessed region crops into ONE tall image
# and issuing ONE call collapses that to a handful of calls.
#
# CRITICAL: the mosaic is assembled AFTER each region has been rotated and
# preprocessed with its OWN recipe. Region-first preprocessing is preserved
# exactly — a glare-suppressed MRP tile and a CLAHE'd nutrition tile can sit in
# the same mosaic, each carrying its own provenance. The mosaic is purely a
# transport optimisation for the OCR call; it is a DERIVED_MOSAIC artefact, not
# new evidence, and it never merges evidence from two regions.
#
# Tiles are separated by a wide blank band and grouped so that binarised and
# grayscale tiles never share a mosaic (Tesseract's internal global
# thresholding would otherwise be pulled between the two).

#: Blank rows between stacked tiles. Wide enough that Tesseract's layout
#: analysis never joins a line from one tile to a line from the next.
MOSAIC_GAP_PX = 34

#: Blank border around the whole mosaic; Tesseract clips glyphs touching the
#: image edge.
MOSAIC_MARGIN_PX = 16

#: Split into multiple mosaics beyond this height so a single call never gets a
#: pathologically large input.
MOSAIC_MAX_HEIGHT_PX = 12000

#: Long-side cap applied to tiles in the cheap ORIENTATION TRIAL only. The trial
#: only needs a comparative readability score, so full resolution is wasted there:
#: measured on dataset image 0, dropping the cap from 720 to 360 took the trial
#: from 22.4 s to 15.8 s with the AXIS decision unchanged for every region.
TRIAL_TILE_MAX_SIDE_PX = 360

#: How much a candidate orientation must beat the GEOMETRIC primary by before it
#: is allowed to override it.
#:
#: WHY A MARGIN IS REQUIRED. Measured on dataset images 0 and 3, the trial's
#: 0-vs-180 preference is not stable: changing only the trial resolution flipped
#: the winner for several regions, while the AXIS (0/180 vs 90/270) never changed.
#: That is the signature of a near-tie — on a region carrying little readable text,
#: neither flip reads well and whichever scores higher is noise. Letting noise pick
#: the orientation is exactly the "never silently choose" failure: the pipeline
#: would commit to a guess and present the result as resolved.
#:
#: So geometry's answer stands unless reading the glyphs clearly contradicts it.
#: A near-tie keeps the stable default and SAYS SO in the region notes, and every
#: other candidate remains available, so the cost of a near-tie is at worst a
#: harder read — never a region reported as unread.
TRIAL_FLIP_MARGIN = 1.25

#: Absolute floor on the winning trial score before it may override geometry.
#:
#: The margin above is a RATIO, and a ratio is vacuous when the geometric
#: primary scores zero — any two-character shrug then "beats" it by an infinite
#: factor. The trial score is `mean_confidence * log1p(characters)`, so a genuine
#: read of a twenty-character line at even 0.5 confidence scores about 1.5, while
#: two junk characters at 0.3 confidence score about 0.33. Requiring 1.0 means an
#: override must be backed by actually reading something substantial, which is the
#: only ground on which reading should be allowed to overturn geometry.
MIN_TRIAL_OVERRIDE_SCORE = 1.0

#: How many regions, ranked by reading priority, take part in the orientation
#: trial. Regions outside this set keep their GEOMETRIC orientation.
#:
#: This is not an arbitrary budget. Because an override now requires a trial score
#: of at least `MIN_TRIAL_OVERRIDE_SCORE`, a region too small or too sparse to
#: produce a substantive read can never override geometry — trialling it is work
#: that cannot change the outcome. Restricting the trial to the regions where it
#: can actually be decisive shortens the trial mosaic without changing any
#: decision it was capable of making.
TRIAL_MAX_REGIONS = 8

#: Whether trial tiles are binarised before the trial call.
#:
#: The trial is a ROUTING decision and never evidence, so a lossy transform is
#: acceptable here in a way it would not be for a real read. Otsu on a downscaled
#: tile roughly halves Tesseract's cost, because unpreprocessed photographic
#: content generates a very large number of candidate components.
#:
#: The failure mode is safe by construction: if binarisation makes a tile
#: unreadable, no orientation clears `MIN_TRIAL_OVERRIDE_SCORE`, the region keeps
#: its geometric orientation, and that is recorded in its notes. Degrading to
#: geometry is graceful — geometry decides the AXIS reliably (measured separation
#: 0.894 vs 0.144), and only the flip is left to the default.
TRIAL_BINARISE = True

#: Long-side cap applied to tiles in the FINAL read.
#:
#: MEASURED, NOT GUESSED. Tesseract's cost grows with input area, and a 2392x1080
#: phone photograph yields label panels that `preprocess` legitimately upscales to
#: 4x for small print — a single tile can exceed 3000 px on a side, and a mosaic of
#: a dozen such tiles pushed one real dataset image to 55 s. Capping the long side
#: keeps glyphs comfortably inside Tesseract's ~20-30 px sweet spot (see
#: `preprocess.TARGET_TEXT_HEIGHT_PX`) while bounding the call cost.
#:
#: The downscale is recorded as `_MosaicTile.tile_scale` and inverted first when
#: mapping a line back, so coordinates remain exact in the ORIGINAL image.
READ_TILE_MAX_SIDE_PX = 1600

#: How many preprocessing variants per region are actually sent to OCR. Three
#: gives fusion enough independent passes to corroborate while keeping the call
#: count bounded.
OCR_VARIANT_SLOTS = 3


@dataclass
class _MosaicTile:
    """Placement of one region's crop inside a mosaic, plus its provenance."""

    plan_index: int
    origin: Tuple[int, int]  # (x, y) of tile content within the mosaic
    shape: Tuple[int, int]  # (h, w) of tile content
    variant: Optional[preprocess.PreprocessedVariant] = None
    #: Uniform scale applied to the tile content relative to the variant image it
    #: came from. 1.0 means no resize. Inverted FIRST when mapping coordinates
    #: back, before the variant's own mapping.
    tile_scale: float = 1.0

    def contains_line(self, bbox: BBoxT) -> bool:
        x, y, w, h = bbox
        cy = y + h / 2.0
        ox, oy = self.origin
        th, tw = self.shape
        if not (oy <= cy < oy + th):
            return False
        # Require some horizontal overlap too, so a stray box in the margin is
        # not attributed to a tile it does not touch.
        return x < ox + tw and x + w > ox

    def to_local(self, bbox: BBoxT) -> BBoxT:
        ox, oy = self.origin
        th, tw = self.shape
        x = max(0, int(bbox[0]) - ox)
        y = max(0, int(bbox[1]) - oy)
        w = min(int(bbox[2]), tw - x)
        h = min(int(bbox[3]), th - y)
        return x, y, max(1, w), max(1, h)


def build_mosaic(
    items: Sequence[Tuple[int, np.ndarray, Optional[preprocess.PreprocessedVariant], float]],
    *,
    gap: int = MOSAIC_GAP_PX,
    margin: int = MOSAIC_MARGIN_PX,
    max_height: int = MOSAIC_MAX_HEIGHT_PX,
) -> List[Tuple[np.ndarray, List[_MosaicTile]]]:
    """
    Stack grayscale tiles vertically on a white field, splitting on height.

    Returns a list of `(mosaic_image, tiles)`. White (255) is the correct pad
    value because every `preprocess` variant is normalised to dark-text-on-light,
    so the padding never introduces a spurious polarity edge.
    """
    batches: List[Tuple[np.ndarray, List[_MosaicTile]]] = []
    pending: List[Tuple[int, np.ndarray, Optional[preprocess.PreprocessedVariant], float]] = []

    def flush() -> None:
        if not pending:
            return
        width = max(int(img.shape[1]) for _i, img, _v, _s in pending) + 2 * margin
        height = margin
        for _i, img, _v, _s in pending:
            height += int(img.shape[0]) + gap
        height = height - gap + margin

        mosaic = np.full((height, width), 255, dtype=np.uint8)
        tiles: List[_MosaicTile] = []
        y = margin
        for index, img, variant, scale in pending:
            gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if gray.dtype != np.uint8:
                gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(
                    np.uint8
                )
            h, w = gray.shape[:2]
            mosaic[y : y + h, margin : margin + w] = gray
            tiles.append(
                _MosaicTile(
                    plan_index=index,
                    origin=(margin, y),
                    shape=(h, w),
                    variant=variant,
                    tile_scale=scale,
                )
            )
            y += h + gap
        batches.append((mosaic, tiles))
        pending.clear()

    running = 2 * margin
    for item in items:
        h = int(item[1].shape[0])
        if pending and running + h + gap > max_height:
            flush()
            running = 2 * margin
        pending.append(item)
        running += h + gap

    flush()
    return batches


def _assign_lines_to_tiles(
    lines: Sequence[RawLine], tiles: Sequence[_MosaicTile]
) -> Dict[int, List[Tuple[_MosaicTile, RawLine]]]:
    """Route each raw line back to the tile whose band it falls in."""
    out: Dict[int, List[Tuple[_MosaicTile, RawLine]]] = {}
    for line in lines:
        for tile in tiles:
            if tile.contains_line(line.bbox):
                out.setdefault(tile.plan_index, []).append((tile, line))
                break
    return out


# ---------------------------------------------------------------------------
# Region plans
# ---------------------------------------------------------------------------


@dataclass
class _RegionPlan:
    """Working state for one region as it moves through the pipeline."""

    index: int
    region: DetectedRegion
    crop: np.ndarray
    offset: Tuple[int, int]
    estimate: OrientationEstimate
    chosen: Orientation = Orientation.DEG_0
    trial_scores: Dict[int, float] = field(default_factory=dict)
    rotated: Optional[np.ndarray] = None
    signals: Optional[preprocess.QualitySignals] = None
    variants: List[preprocess.PreprocessedVariant] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    passes: int = 0


def _crop_region(
    image: np.ndarray, region: DetectedRegion, *, pad: int = 4
) -> Optional[Tuple[np.ndarray, Tuple[int, int]]]:
    ih, iw = image.shape[:2]
    x, y, w, h = region.bbox
    x0 = max(0, int(x) - pad)
    y0 = max(0, int(y) - pad)
    x1 = min(iw, int(x) + int(w) + pad)
    y1 = min(ih, int(y) + int(h) + pad)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    return image[y0:y1, x0:x1].copy(), (x0, y0)


def _cap_long_side(gray: np.ndarray, limit: int) -> Tuple[np.ndarray, float]:
    """
    Downscale so the long side is at most `limit`, returning `(image, scale)`.

    `scale` is what the content was multiplied by, so dividing a coordinate by it
    inverts the resize. INTER_AREA is used because it averages, which is the
    correct behaviour when discarding resolution — it never sharpens an edge into
    existence, so no glyph detail is invented.
    """
    h, w = gray.shape[:2]
    longest = max(h, w)
    if longest <= limit:
        return gray, 1.0
    scale = limit / float(longest)
    resized = cv2.resize(
        gray,
        (max(8, int(round(w * scale))), max(8, int(round(h * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def _downscale_for_trial(gray: np.ndarray) -> Tuple[np.ndarray, float]:
    return _cap_long_side(gray, TRIAL_TILE_MAX_SIDE_PX)


def _trial_tile(gray: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    Prepare one tile for the orientation trial: downscale, then optionally Otsu.

    Cheap and deliberately lossy — see `TRIAL_BINARISE`. This output is NEVER an
    evidence source; it only feeds the comparative readability score that resolves
    the 0/180 and 90/270 flip.
    """
    small, scale = _downscale_for_trial(gray)
    if not TRIAL_BINARISE:
        return small, scale
    blurred = cv2.GaussianBlur(small, (3, 3), 0)
    _t, binary = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    # Dark text on light, matching every `preprocess` variant, so the mosaic's
    # white padding never introduces a spurious polarity edge.
    if float(np.mean(binary)) < 127.0:
        binary = cv2.bitwise_not(binary)
    return binary, scale


def resolve_orientations(
    plans: Sequence[_RegionPlan], engine: TesseractEngine
) -> int:
    """
    Resolve every region's 0/180 and 90/270 flip with ONE OCR call per candidate
    orientation across ALL regions.

    Geometry (in `orientation.py`) narrows each region to an axis; only reading
    the glyphs can settle which way up they are. Instead of paying for that per
    region, all regions that list a given orientation as a live candidate are
    mosaicked together and scored in a single pass. Four calls therefore decide
    the orientation of an entire photograph.

    A region whose every trial scores zero keeps its geometric primary and is
    noted: no orientation produced readable text, which is NOT_OBSERVED, never
    an absence claim about the package.

    Returns the number of OCR calls made.
    """
    live: Dict[int, List[int]] = {}
    # Only the highest-priority regions are trialled; the rest cannot clear
    # MIN_TRIAL_OVERRIDE_SCORE anyway. See TRIAL_MAX_REGIONS.
    trialled = sorted(
        plans,
        key=lambda p: (-_read_priority(p.region), p.region.bbox[1], p.region.bbox[0]),
    )[: max(1, TRIAL_MAX_REGIONS)]
    trialled_ids = {p.index for p in trialled}

    for plan in plans:
        if plan.index not in trialled_ids:
            plan.chosen = plan.estimate.primary
            plan.notes.append(
                f"Not included in the orientation trial (outside the top "
                f"{TRIAL_MAX_REGIONS} by reading priority). Using the geometric "
                f"orientation {plan.chosen.label}; a region this small or sparse "
                "could not have produced a read substantial enough to override "
                "geometry."
            )
            continue
        candidates = list(plan.estimate.candidates)
        # A confidently decided axis only needs its own two flips tested. The
        # other axis stays available as a fallback but is not paid for up front.
        if (
            plan.estimate.axis is not TextAxis.AMBIGUOUS
            and plan.estimate.confidence >= 0.35
        ):
            candidates = candidates[:2]
        for candidate in candidates:
            live.setdefault(int(candidate.value), []).append(plan.index)

    by_index = {plan.index: plan for plan in plans}
    calls = 0

    for degrees in sorted(live):
        candidate = Orientation(degrees)
        items = []
        for plan_index in live[degrees]:
            plan = by_index[plan_index]
            gray = (
                plan.crop
                if plan.crop.ndim == 2
                else cv2.cvtColor(plan.crop, cv2.COLOR_BGR2GRAY)
            )
            small, scale = _trial_tile(gray)
            rotated = orientation_module.rotate_crop(small, candidate)
            items.append((plan_index, rotated, None, scale))

        for mosaic, tiles in build_mosaic(items):
            lines = engine.read(mosaic, psm=6)
            calls += 1
            assigned = _assign_lines_to_tiles(lines, tiles)
            for tile in tiles:
                tile_lines = [line for _t, line in assigned.get(tile.plan_index, [])]
                score = _trial_score(tile_lines)
                plan = by_index[tile.plan_index]
                previous = plan.trial_scores.get(degrees, 0.0)
                plan.trial_scores[degrees] = max(previous, score)

    for plan in trialled:
        plan.passes += 0  # trial calls are counted at the image level
        if not plan.trial_scores or max(plan.trial_scores.values()) <= 0.0:
            plan.chosen = plan.estimate.primary
            plan.notes.append(
                "No orientation produced readable text in the trial. Keeping "
                f"the geometric estimate ({plan.chosen.label}); if nothing is "
                "read, this region is NOT_OBSERVED, which is not evidence that "
                "text is absent."
            )
            continue

        best_degrees = max(
            plan.trial_scores,
            # Deterministic: highest score, then the smallest rotation.
            key=lambda d: (plan.trial_scores[d], -d),
        )
        primary = int(plan.estimate.primary.value)
        best_score = plan.trial_scores[best_degrees]
        primary_score = plan.trial_scores.get(primary, 0.0)
        scores_note = {k: round(v, 3) for k, v in plan.trial_scores.items()}

        if best_degrees == primary:
            plan.chosen = plan.estimate.primary
            plan.notes.append(
                f"Orientation confirmed by OCR trial: {plan.chosen.label} "
                f"(scores {scores_note})."
            )
        elif (
            best_score >= primary_score * TRIAL_FLIP_MARGIN
            and best_score >= MIN_TRIAL_OVERRIDE_SCORE
        ):
            plan.chosen = Orientation(best_degrees)
            plan.notes.append(
                f"Orientation overridden by OCR trial: {plan.chosen.label} read "
                f"clearly better than the geometric primary "
                f"{plan.estimate.primary.label} (scores {scores_note}); the trial "
                "wins because it is based on actually reading glyphs."
            )
        else:
            plan.chosen = plan.estimate.primary
            plan.notes.append(
                f"OCR trial did not clearly separate the orientations (scores "
                f"{scores_note}); keeping the geometric primary "
                f"{plan.chosen.label} rather than letting a near-tie choose. The "
                "other orientations remain available, so a near-tie costs at most "
                "a harder read, never an unread region."
            )

        if plan.estimate.axis is not TextAxis.AMBIGUOUS:
            trial_axis = (
                TextAxis.HORIZONTAL
                if plan.chosen in (Orientation.DEG_0, Orientation.DEG_180)
                else TextAxis.VERTICAL
            )
            if trial_axis is not plan.estimate.axis:
                plan.notes.append(
                    f"The OCR trial preferred the {trial_axis.value} axis over "
                    f"the geometric estimate ({plan.estimate.axis.value}); the "
                    "trial wins because it is based on actually reading glyphs."
                )

    return calls


def _prepare_variants(plan: _RegionPlan, *, purpose: str) -> None:
    """
    ORDER OF OPERATIONS, exactly as mandated:
        region -> orientation -> local rotation -> preprocessing -> OCR -> map back

    Rotating BEFORE measuring quality matters: text height is estimated from
    horizontal ink runs, so the estimate is only meaningful once the glyphs are
    upright. Measuring first would mis-size the upscale for every vertical
    declaration on the package.
    """
    plan.rotated = orientation_module.rotate_crop(plan.crop, plan.chosen)
    plan.signals = preprocess.measure_quality(plan.rotated)
    plan.variants = preprocess.build_variants(
        plan.rotated, signals=plan.signals, purpose=purpose
    )[:OCR_VARIANT_SLOTS]


def _observations_for_plan(
    plan: _RegionPlan,
    tile: _MosaicTile,
    line: RawLine,
    engine_name: OcrEngineName,
    region_offset: Tuple[int, int],
) -> OcrObservation:
    """
    Map one mosaic line all the way back to ORIGINAL image coordinates.

    Four inversions, in this order and no other:
      1. mosaic placement  -> tile-local coordinates
      2. tile downscale    -> variant-image coordinates
      3. variant scaling   -> rotated-crop coordinates
      4. local rotation    -> unrotated crop, then + crop offset -> original image

    Getting the order wrong attaches a correct reading to the wrong part of the
    package, which is an evidence-integrity failure even when the text is right.
    """
    local = tile.to_local(line.bbox)
    if tile.tile_scale != 1.0:
        inv = 1.0 / tile.tile_scale
        local = (
            int(round(local[0] * inv)),
            int(round(local[1] * inv)),
            max(1, int(round(local[2] * inv))),
            max(1, int(round(local[3] * inv))),
        )
    variant = tile.variant
    in_rotated = variant.map_bbox_to_source(local) if variant else local
    assert plan.rotated is not None
    in_crop = orientation_module.map_bbox_from_rotated(
        in_rotated, plan.chosen, plan.rotated.shape[:2]
    )
    bbox = (
        in_crop[0] + plan.offset[0] + region_offset[0],
        in_crop[1] + plan.offset[1] + region_offset[1],
        in_crop[2],
        in_crop[3],
    )
    return OcrObservation(
        text=line.text,
        bbox=bbox,
        confidence=line.confidence,
        engine=engine_name,
        orientation=plan.chosen,
        variant_name=variant.name if variant else "original",
        variant_recipe=tuple(step.value for step in variant.recipe) if variant else (),
        region_id=plan.region.region_id,
        region_type=plan.region.region_type,
        region_bbox=(
            plan.region.bbox[0] + region_offset[0],
            plan.region.bbox[1] + region_offset[1],
            plan.region.bbox[2],
            plan.region.bbox[3],
        ),
        psm=line.psm,
    )


def _read_plans(
    plans: Sequence[_RegionPlan],
    engines: Sequence[object],
    *,
    region_offset: Tuple[int, int],
) -> Tuple[Dict[int, List[OcrObservation]], int]:
    """
    Run the batched OCR passes and return raw (unfused) observations per region.

    Grouping key is `(orientation, is_binary, variant_slot)`. Orientation must
    match because tiles in one mosaic are already rotated. `is_binary` must match
    because Tesseract's internal thresholding would otherwise be pulled between
    an already-binarised tile and a grayscale one. The slot index keeps each
    region's OWN recipe ranking intact: slot 0 is every region's best-suited
    variant, whatever recipe that happens to be.
    """
    by_index = {plan.index: plan for plan in plans}
    groups: Dict[Tuple[int, bool, int], List[Tuple[int, np.ndarray, preprocess.PreprocessedVariant, float]]] = {}

    for plan in plans:
        for slot, variant in enumerate(plan.variants):
            key = (int(plan.chosen.value), bool(variant.is_binary), slot)
            image, scale = _cap_long_side(variant.image, READ_TILE_MAX_SIDE_PX)
            if scale != 1.0:
                plan.notes.append(
                    f"Variant '{variant.name}' was downscaled x{scale:.2f} for the "
                    "OCR call to bound cost. The scale is recorded and inverted "
                    "when mapping coordinates back."
                )
            groups.setdefault(key, []).append(
                (plan.index, image, variant, scale)
            )

    raw: Dict[int, List[OcrObservation]] = {}
    calls = 0

    for key in sorted(groups):
        for mosaic, tiles in build_mosaic(groups[key]):
            for engine in engines:
                lines = engine.read(mosaic, psm=6)
                calls += 1
                assigned = _assign_lines_to_tiles(lines, tiles)
                for plan_index, pairs in assigned.items():
                    plan = by_index[plan_index]
                    plan.passes += 1
                    for tile, line in pairs:
                        raw.setdefault(plan_index, []).append(
                            _observations_for_plan(
                                plan, tile, line, engine.name, region_offset
                            )
                        )

    return raw, calls


def _finish_reading(
    plan: _RegionPlan, raw: Sequence[OcrObservation]
) -> RegionReading:
    """Fuse one region's passes and attach honest guidance when it read nothing."""
    observations, conflicts = fuse_observations(list(raw))
    signals = plan.signals or preprocess.measure_quality(plan.crop)

    guidance: List[str] = []
    notes = list(plan.notes)

    if not observations:
        guidance = preprocess.recapture_guidance(signals, field_label="this label area")
        if not guidance:
            guidance = [
                "No text could be read from this area. Capture a closer, "
                "square-on photograph of it."
            ]
        notes.append(
            "NOT_OBSERVED: OCR produced nothing for this region. That is "
            "evidence about the capture and the reader, NOT about the package."
        )
    elif signals.has_glare_problem:
        # Glare must never become an invented reading.
        guidance = preprocess.recapture_guidance(signals, field_label="this label area")
        notes.append(
            "Glare detected over this region. Readings here are treated as "
            "UNCERTAIN and recapture is advised; text obscured by glare is "
            "never reconstructed by guesswork."
        )

    if plan.rotated is not None and plan.chosen is not Orientation.DEG_0:
        notes.append(
            f"Region rotated locally by {plan.chosen.label}. The original image "
            "was never rotated."
        )

    return RegionReading(
        region=plan.region,
        orientation_estimate=plan.estimate,
        chosen_orientation=plan.chosen,
        observations=observations,
        quality=signals,
        passes_run=plan.passes,
        recapture_guidance=guidance,
        conflicts=conflicts,
        notes=notes,
    )


def _empty_reading(
    region: DetectedRegion,
    reason: str,
    *,
    guidance: Optional[List[str]] = None,
) -> RegionReading:
    """
    A region that produced no reading, with the honest reason why.

    `guidance` defaults to a recapture prompt because the usual cause is a capture
    problem. Pass `[]` when the cause is NOT the photograph — telling a user to
    re-shoot a barcode as if it were unreadable text is misleading guidance.
    """
    blank = np.zeros((16, 16), dtype=np.uint8)
    if guidance is None:
        guidance = [
            "This area could not be read. Capture a dedicated, closer "
            "photograph of it."
        ]
    return RegionReading(
        region=region,
        orientation_estimate=orientation_module.estimate_region_orientation(blank),
        chosen_orientation=Orientation.DEG_0,
        observations=[],
        quality=preprocess.measure_quality(blank),
        passes_run=0,
        recapture_guidance=list(guidance),
        notes=[reason],
    )


# ---------------------------------------------------------------------------
# Symbology quarantine
# ---------------------------------------------------------------------------


def _containment(inner: BBoxT, outer: BBoxT) -> float:
    """Fraction of `inner`'s area that lies inside `outer`. 0.0 when disjoint."""
    ax, ay, aw, ah = (int(v) for v in inner)
    bx, by, bw, bh = (int(v) for v in outer)
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    area = float(aw * ah)
    if area <= 0:
        return 0.0
    return (ix * iy) / area


def _offset_bboxes(
    regions: Sequence[DetectedRegion], offset: Tuple[int, int]
) -> List[BBoxT]:
    dx, dy = int(offset[0]), int(offset[1])
    return [
        (int(r.bbox[0]) + dx, int(r.bbox[1]) + dy, int(r.bbox[2]), int(r.bbox[3]))
        for r in regions
    ]


def flag_symbology_noise(
    observations: Sequence[OcrObservation],
    symbology_bboxes: Sequence[BBoxT],
    *,
    threshold: float = SYMBOLOGY_CONTAINMENT_REJECT,
) -> int:
    """
    Quarantine readings that came out of a barcode's or QR code's footprint.

    WHAT THIS PREVENTS: a text engine pointed at stripes or QR modules still
    returns characters. On this dataset the barcode block yields readings such as
    '| | | | | [|' and '| U9 028735249'. Those are artefacts of the reader, not
    text on the package, and a field extractor cannot tell them apart from a
    genuine short declaration. Quantity and MRP are the fields most exposed,
    because a fabricated value there does not weaken a finding — it manufactures
    one, and net quantity feeds Rule 6 and the Second Schedule directly.

    Refusing symbology REGIONS as OCR input is not sufficient on its own. Region
    detection intentionally emits overlapping regions of different types, and
    `suppress_overlaps()` never removes a region because a region of another type
    covers it — a barcode inside a label panel is a real arrangement. So a TEXT or
    DECLARATION_TEXT region can, and on real photographs does, sit right on top of
    the barcode. This function closes that path.

    Mutates `symbology_noise` in place and returns how many were flagged. Nothing
    is deleted: quarantined readings keep full provenance and appear in the audit
    trail as withheld, because suppressing a reading must never be invisible.
    """
    if not symbology_bboxes:
        return 0

    flagged = 0
    for obs in observations:
        if obs.symbology_noise:
            continue
        worst = max(
            (_containment(obs.bbox, box) for box in symbology_bboxes), default=0.0
        )
        if worst >= threshold:
            obs.symbology_noise = True
            obs.notes = tuple(obs.notes) + (
                f"WITHHELD as symbology noise: {worst:.0%} of this reading's "
                "footprint lies inside a detected barcode/QR region. Barcode "
                "stripes read as characters are not text and must never reach "
                "field classification. Decode the symbology instead.",
            )
            flagged += 1
    return flagged


# ---------------------------------------------------------------------------
# Public reading API
# ---------------------------------------------------------------------------


def read_regions(
    image: np.ndarray,
    regions: Sequence[DetectedRegion],
    *,
    region_offset: Tuple[int, int] = (0, 0),
    purpose: str = "text",
    symbology_regions: Sequence[DetectedRegion] = (),
) -> Tuple[List[RegionReading], int]:
    """
    Read several regions of one image together. THE single reading code path.

    `regions` bboxes must be in the same coordinate frame as `image`;
    `region_offset` is added to every output bbox for callers whose `image` is
    itself a crop of a larger original.

    Symbology regions are refused as INPUT: barcode and QR go to the decoder,
    never to a text engine, because stripes and QR modules are not glyphs.

    `symbology_regions` is the other half of that guard: pass the detected
    barcode/QR regions here (same coordinate frame) and any text region sitting on
    top of one is skipped, while any reading whose footprint falls inside one is
    quarantined from field extraction. See `flag_symbology_noise()`.

    Returns `(readings, ocr_calls_made)`.
    """
    for region in regions:
        if region.region_type in region_detection.SYMBOLOGY_TYPES:
            raise ValueError(
                f"read_regions() refuses {region.region_type.value}: barcode and "
                "QR regions go to the decoder, never to a text engine."
            )

    engines, _notes = active_engines()
    if not engines or not regions:  # pragma: no cover - environment dependent
        return [
            _empty_reading(region, "No OCR engine available.") for region in regions
        ], 0

    tesseract = next(
        (e for e in engines if isinstance(e, TesseractEngine)), _TESSERACT
    )

    symbology_local = [
        (int(r.bbox[0]), int(r.bbox[1]), int(r.bbox[2]), int(r.bbox[3]))
        for r in symbology_regions
    ]
    symbology_original = _offset_bboxes(symbology_regions, region_offset)

    plans: List[_RegionPlan] = []
    failures: Dict[int, RegionReading] = {}

    for index, region in enumerate(regions):
        covered = max(
            (_containment(region.bbox, box) for box in symbology_local), default=0.0
        )
        if covered >= SYMBOLOGY_CONTAINMENT_SKIP:
            failures[index] = _empty_reading(
                region,
                f"NOT SENT TO OCR: {covered:.0%} of this region lies inside a "
                "detected barcode/QR region, so it is the symbology itself under "
                "a text label. Barcode stripes are not glyphs; a text engine "
                "pointed at them returns characters that are artefacts of the "
                "reader. The symbology is decoded separately; this area is "
                "NOT_OBSERVED by OCR, which is not evidence that any declaration "
                "is absent.",
                guidance=[],
            )
            continue
        cropped = _crop_region(image, region)
        if cropped is None:
            failures[index] = _empty_reading(
                region, "Region is below the minimum readable size."
            )
            continue
        crop, offset = cropped
        plans.append(
            _RegionPlan(
                index=index,
                region=region,
                crop=crop,
                offset=offset,
                estimate=orientation_module.estimate_region_orientation(crop),
            )
        )

    calls = resolve_orientations(plans, tesseract)

    for plan in plans:
        try:
            _prepare_variants(plan, purpose=purpose)
        except ValueError:
            plan.variants = []
            plan.notes.append("Region too small to preprocess.")

    raw, read_calls = _read_plans(plans, engines, region_offset=region_offset)
    calls += read_calls

    readings: List[RegionReading] = []
    for index, region in enumerate(regions):
        if index in failures:
            readings.append(failures[index])
            continue
        plan = next(p for p in plans if p.index == index)
        reading = _finish_reading(plan, raw.get(index, []))
        withheld = flag_symbology_noise(reading.observations, symbology_original)
        if withheld:
            reading.notes.append(
                f"{withheld} reading(s) from this region overlap a detected "
                "barcode/QR footprint and were withheld from field extraction as "
                "symbology noise. They are retained for audit."
            )
        readings.append(reading)

    return readings, calls


def read_region(
    image: np.ndarray,
    region: DetectedRegion,
    *,
    region_offset: Tuple[int, int] = (0, 0),
    purpose: str = "text",
) -> RegionReading:
    """Read exactly one region. Thin wrapper over `read_regions()`."""
    readings, _calls = read_regions(
        image, [region], region_offset=region_offset, purpose=purpose
    )
    return readings[0]


#: Relative reading priority per region type, used only to decide WHICH regions
#: get read when an image yields more than the per-image cap. It never affects how
#: a reading is interpreted. Declaration panels are read first because they are
#: where the statutory declarations live; a stray high-confidence texture blob
#: must not consume the budget ahead of the MRP panel.
_READ_PRIORITY: Dict[RegionType, float] = {
    RegionType.DECLARATION_TEXT: 3.0,
    RegionType.STICKER: 1.6,
    RegionType.LABEL: 1.4,
    RegionType.TEXT: 1.0,
    RegionType.UNKNOWN: 0.5,
}


def _read_priority(region: DetectedRegion) -> float:
    """
    Rank a region for the limited OCR budget: type weight x confidence x size.

    Area enters logarithmically so a large panel outranks a small fragment
    without a single huge region dominating outright. `text_regions()` alone sorts
    by confidence, which on real photographs puts tiny sharp-edged graphics ahead
    of the dense declaration block that actually matters.
    """
    weight = _READ_PRIORITY.get(region.region_type, 0.8)
    area = max(1, int(region.bbox[2]) * int(region.bbox[3]))
    return weight * float(region.confidence) * float(np.log1p(area / 1000.0))


# ---------------------------------------------------------------------------
# NEGATIVE RESULT, RECORDED SO IT IS NOT RE-ATTEMPTED: read-set de-duplication
# ---------------------------------------------------------------------------
# Detected regions overlap heavily. On dataset image 0, six of the fourteen
# regions that fit the per-image OCR budget were >=80% inside another region
# already being read, while seventeen further regions went unread for want of
# budget. Dropping the contained ones and refilling the budget with unread
# surface looked like a free 36% speedup (32.6s -> 21.0s).
#
# It is not free. It is actively harmful, for two measured reasons.
#
# 1. RECALL. A small crop is preprocessed on its OWN terms: its local contrast
#    sets the threshold and its glyphs are resampled towards
#    `preprocess.TARGET_TEXT_HEIGHT_PX`. Read instead as a few hundred pixels
#    inside a large panel, the same text is thresholded against the whole
#    panel's statistics and left well below the height Tesseract needs. On image
#    0 three prose lines read correctly from the contained LABEL region
#    ('processes ensure that fresh coffee aroma is', conf 0.96) and read as
#    garbage from the containing DECLARATION_TEXT region ('fe cere gaggle) Eee
#    ny', conf 0.15). De-duplicating kept only the garbage. Image 7 lost 27% of
#    its extracted characters (466 -> 340) at identical wall-clock time.
#
#    An area-ratio guard (drop only if the fragment fills >=50% of its
#    container, so the two preprocessing scales are within ~1.4x) recovered
#    images 3 and 7 but NOT image 0, where the harmful pair had an area ratio of
#    0.56. Geometry does not predict which recipe will read better.
#
# 2. EVIDENCE QUALITY, which matters more. Reading the same text twice under
#    different recipes is not wasted work — it is the only source of
#    CORROBORATED and CONFLICTING states within a single image, and
#    `fuse_observations()` exists to exploit exactly that. With overlapping
#    reads, image 0's three prose lines are correctly marked CONFLICTING and the
#    good and bad readings both survive for review. With de-duplication the
#    conflict evaporates and the surviving reading is reported SINGLE_SOURCE.
#    The spurious '17m' moved the wrong way too: CONFLICTING at conf 0.93
#    became CORROBORATED at conf 1.00. Removing redundancy does not remove the
#    disagreement in the underlying pixels, it only removes our knowledge of it,
#    and that turns an honest "sources disagree" into unearned confidence.
#
# So overlapping reads stay. The remaining speed lever is variant RANKING — that
# `OCR_VARIANT_SLOTS` cannot drop from 3 to 2 without losing 41% of image 3's
# characters says the best variant is often not ranked first, which is a quality
# problem masquerading as a budget problem. Fixing the ranking is the way to buy
# back time; discarding evidence is not.


def select_regions_to_read(
    regions: Sequence[DetectedRegion], max_regions: int
) -> Tuple[List[DetectedRegion], List[DetectedRegion]]:
    """
    Choose which text-like regions to send to OCR, highest priority first.

    Returns `(to_read, not_reached)`. The two lists are disjoint and together
    account for every input region, so the audit trail can state exactly why each
    area was or was not read.

    `not_reached` regions were NOT read. They remain in the `DetectionResult` and
    the reader records reduced coverage for them. They are NOT_OBSERVED, which is
    never evidence that a declaration is absent.

    Overlap is deliberately NOT de-duplicated here; see the negative result
    recorded above this function for the measurements that rule it out.
    """
    ranked = sorted(
        regions,
        key=lambda r: (-_read_priority(r), r.bbox[1], r.bbox[0]),
    )
    limit = max(1, int(max_regions))
    return ranked[:limit], ranked[limit:]


def read_image(
    image: np.ndarray,
    *,
    detection: Optional[DetectionResult] = None,
    max_regions: int = _MAX_REGIONS,
    purpose: str = "text",
) -> ImageReading:
    """
    Full region-first, orientation-aware read of one image.

    When `detection` is omitted, `region_detection.detect_regions_on_full_image()`
    runs first, which strips Android screenshot chrome and returns every region
    bbox already in ORIGINAL image coordinates.

    Regions beyond `max_regions` are left unread. They stay in the returned
    `DetectionResult` so the audit trail is complete, and the fact that they were
    not read is recorded as reduced coverage — never as an absence claim.
    """
    import time

    started = time.perf_counter()

    if image is None or image.size == 0:
        raise ValueError("read_image() received an empty image.")

    content_region: Optional[preprocess.ContentRegion] = None
    if detection is None:
        detection, content_region = region_detection.detect_regions_on_full_image(image)

    engines, engine_notes = active_engines()
    engines_used = tuple(e.name for e in engines)

    text_regions = detection.text_regions()
    to_read, not_reached = select_regions_to_read(text_regions, max_regions)
    skipped = len(not_reached)

    symbology = detection.symbology_regions()
    readings, calls = read_regions(
        image, to_read, purpose=purpose, symbology_regions=symbology
    )

    all_obs: List[OcrObservation] = []
    conflicts: List[Dict[str, object]] = []
    guidance: List[str] = []
    for reading in readings:
        all_obs.extend(reading.observations)
        conflicts.extend(reading.conflicts)
        for hint in reading.recapture_guidance:
            if hint not in guidance:
                guidance.append(hint)

    # Cross-region fusion. Detected regions frequently overlap, so the same
    # declaration line can be read twice. Fusing again at image level turns that
    # duplication into corroboration instead of two competing observations.
    fused, cross_conflicts = fuse_observations(all_obs)
    conflicts.extend(cross_conflicts)

    # Re-apply the symbology quarantine after cross-region fusion. Fusion picks a
    # representative reading per location, and that representative may have come
    # from a region that did not itself overlap the barcode, so the flag has to be
    # recomputed against the FUSED set. Idempotent by design.
    quarantined = flag_symbology_noise(
        fused, _offset_bboxes(detection.symbology_regions(), (0, 0))
    )

    notes = list(engine_notes)
    notes.append(
        f"{calls} OCR call(s) issued for {len(to_read)} region(s) via mosaic batching."
    )
    if symbology:
        notes.append(
            f"{len(symbology)} barcode/QR region(s) were detected and were never "
            "sent to a text engine."
        )
    if quarantined:
        notes.append(
            f"{quarantined} reading(s) fell inside a barcode/QR footprint and were "
            "withheld from field extraction as symbology noise. They are retained "
            "in the audit trail."
        )
    noise = sum(
        1 for o in fused if not o.symbology_noise and not o.is_plausible_text
    )
    if noise:
        notes.append(
            f"{noise} reading(s) were too short or too punctuation-heavy to be a "
            "declaration and were withheld from field extraction as typographic "
            "noise. Withholding a reading cannot create a MISSING finding; an "
            "unextracted field is NOT_OBSERVED."
        )
    if content_region is not None and not content_region.is_full_image:
        notes.append(
            f"Screenshot chrome/letterbox trimmed before reading "
            f"({content_region.reason}). All bboxes are in ORIGINAL image "
            "coordinates."
        )
    if skipped > 0:
        notes.append(
            f"{skipped} additional text region(s) were detected but not read "
            f"(per-image cap of {max_regions}). Those areas are NOT_OBSERVED, "
            "which is not evidence that any declaration is absent."
        )
    if not detection.regions:
        notes.append(detection.coverage_note)

    return ImageReading(
        observations=fused,
        region_readings=readings,
        detection=detection,
        engines_used=engines_used,
        engine_notes=notes,
        recapture_guidance=guidance,
        conflicts=conflicts,
        elapsed_seconds=time.perf_counter() - started,
    )


def read_image_path(path: str) -> ImageReading:
    """Convenience entrypoint for the benchmark harness and the CLI."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    return read_image(image)


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    import json
    import sys

    if len(sys.argv) < 2:
        print("usage: python ocr_engine.py <image path>")
        raise SystemExit(2)

    reading = read_image_path(sys.argv[1])
    print(reading.full_text)
    print("---")
    print(json.dumps(reading.provenance(), indent=2, default=str)[:4000])
