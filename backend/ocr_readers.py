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
    _MAX_REGIONS = 24
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
            # NOTE: these keys must exist on preprocess.QualitySignals. Two of
            # them previously did not -- `blur_variance` (the field is named
            # `sharpness`) and an unguarded `estimated_text_height_px`, which is
            # Optional and is None for any region where text height could not be
            # estimated. Either one raised AttributeError/TypeError, and because
            # every caller of the region-first read is wrapped in a broad
            # `except Exception` (see ocr_extraction.run_ocr), the failure was
            # silent: the region-level audit trail simply never materialized.
            # Keep this dict in sync with QualitySignals by hand -- there is no
            # test that would catch a renamed field here.
            "quality": {
                "sharpness": round(float(self.quality.sharpness), 3),
                "glare_fraction": round(float(self.quality.glare_fraction), 4),
                "contrast": round(float(self.quality.contrast), 4),
                "estimated_text_height_px": (
                    round(float(self.quality.estimated_text_height_px), 2)
                    if self.quality.estimated_text_height_px is not None
                    else None
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

                    try:
                        import torch
                    except Exception:
                        pass

                    try:
                        import paddle.inference as pi

                        if not getattr(pi.Config, "_lmpc_patched", False):
                            orig_create = pi.create_predictor

                            def _patched_create(cfg):
                                if hasattr(cfg, "disable_onednn"):
                                    cfg.disable_onednn()
                                if hasattr(cfg, "disable_mkldnn"):
                                    cfg.disable_mkldnn()
                                return orig_create(cfg)

                            pi.create_predictor = _patched_create
                            pi.Config._lmpc_patched = True
                    except Exception:
                        pass

                    from localization.sanskruti.paddle_detector import PaddleTextDetector
                    detector = PaddleTextDetector.get_instance()
                    if detector._init_engine() and detector._engine is not None:
                        self._reader = detector._engine
                        self._available = True
                    else:
                        from paddleocr import PaddleOCR
                        self._reader = PaddleOCR(lang="en")
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

        try:
            if hasattr(self._reader, "predict"):
                raw = self._reader.predict(image)
            else:
                raw = self._reader.ocr(image)
        except Exception:
            try:
                raw = self._reader.ocr(image)
            except Exception:
                return []

        lines: List[RawLine] = []
        for page in raw or []:
            if isinstance(page, dict):
                # PaddleOCR 3.x / paddlex format
                rec_texts = page.get("rec_texts") or page.get("rec_text") or []
                rec_scores = page.get("rec_scores") or page.get("rec_score") or []
                rec_boxes = (
                    page.get("rec_boxes")
                    or page.get("dt_polys")
                    or page.get("rec_polys")
                    or []
                )
                for i, text in enumerate(rec_texts):
                    if not str(text).strip():
                        continue
                    score = float(rec_scores[i]) if i < len(rec_scores) else 0.8
                    if i < len(rec_boxes):
                        pts = np.asarray(rec_boxes[i], dtype=np.float32)
                        x, y, w, h = cv2.boundingRect(pts)
                    else:
                        x, y, w, h = 0, 0, 10, 10
                    lines.append(
                        RawLine(
                            text=str(text).strip(),
                            bbox=(int(x), int(y), max(1, int(w)), max(1, int(h))),
                            confidence=_clamp01(score),
                        )
                    )
            elif isinstance(page, list):
                # PaddleOCR 2.x legacy format
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


