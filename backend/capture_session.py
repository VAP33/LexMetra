"""
Multi-surface inspection session orchestration.

Implements the architecture required by the master spec:

    InspectionSession
        |-- SurfaceObservation[]

Each call to add_capture() processes ONE photograph of ONE package surface
(front, back, a rotated view of a curved label, etc.) and folds its OCR
evidence into the session's cumulative field map. The rule engine is only
ever called once, at finalize(), against the UNION of everything observed
across every surface — never against a single image in isolation.

Core invariant (see rule_engine.py / CLAUDE MASTERPROMPT.txt section 4):
    NOT VISIBLE != MISSING.
A required declaration that has not appeared in any capture yet is
UNCERTAIN / "keep capturing", not a violation, until either it is found or
the accumulated evidence coverage is judged sufficient to conclude absence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from schema import (
    BBox,
    EvidenceReference,
    GeometryType,
    ImageQuality,
    MeasurementMode,
    PositionCoordinateSystem,
    SurfaceObservation,
    SurfaceType,
    UNATTRIBUTED_IMAGE_ID as _UNATTRIBUTED_IMAGE_ID,
)
from rule_engine import RawExtraction, required_declaration_fields, load_rules

DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.55
EVIDENCE_SUFFICIENT_COVERAGE = 0.70

# Human-guidance hints per field, shown when that declaration has not yet
# been located anywhere in the session's captures.
FIELD_CAPTURE_HINTS: Dict[str, str] = {
    "manufacturer_name_address": "Capture the panel showing the manufacturer/packer/importer name and address.",
    "common_name": "Capture the panel showing the product's common/generic name.",
    "net_quantity": "Capture the panel showing the net quantity declaration.",
    "wholesale_count_or_net_quantity": "Capture the panel showing the total count or net quantity for the wholesale package.",
    "mrp": "Capture the panel showing the Maximum Retail Price (MRP).",
    "mfg_date": "Capture the panel showing the month and year of manufacture.",
    "best_before_use_by": "Capture the panel showing the best-before / use-by date.",
    "consumer_care": "Capture the panel showing the consumer-care contact details.",
    "unit_sale_price": "Capture the panel showing the unit sale price declaration.",
    "country_of_origin": "Capture the panel showing the country of origin.",
}

SURFACE_TYPE_ALIASES = {t.value.lower(): t for t in SurfaceType}


def parse_surface_type(value: Optional[str]) -> SurfaceType:
    if not value:
        return SurfaceType.UNKNOWN
    return SURFACE_TYPE_ALIASES.get(str(value).strip().lower(), SurfaceType.UNKNOWN)


def _field_confidence(classified: Dict[str, dict], field_name: str) -> float:
    data = classified.get(field_name)
    if not data:
        return 0.0
    try:
        return float(data.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def merge_classified_fields(
    accumulated: Dict[str, dict],
    new_fields: Dict[str, dict],
) -> Dict[str, dict]:
    """
    Fold one capture's classified OCR fields into the session's running
    field map.

    Merge rule: for each field, keep whichever observation (existing or new)
    has the higher extraction confidence. This lets a later, clearer photo
    of the same declaration override an earlier blurry one, while never
    discarding a good earlier reading in favor of a worse new one.
    """
    merged = dict(accumulated)
    for name, data in new_fields.items():
        if name.startswith("_"):
            continue
        existing = merged.get(name)
        if existing is None:
            merged[name] = data
            continue
        if _field_confidence({name: data}, name) > _field_confidence({name: existing}, name):
            merged[name] = data
    return merged


def bridge_classified_fields(classified: Dict[str, dict]) -> Dict[str, dict]:
    """
    Reconcile the OCR vocabulary with the legal-rule vocabulary.

    ocr_extraction.py and rules.json were authored independently and use
    different field names for the same legal facts — e.g. OCR emits
    'manufacturer_name' / 'packer_name' / 'importer_name' as separate
    fields, but Rule 6/Rule 24's combined requirement reads
    'manufacturer_name_address'; OCR emits 'expiry_date', but the rule reads
    'best_before_use_by'. This is the single place that reconciles the two
    vocabularies for BOTH the per-capture coverage estimate (this module)
    and the final rule-engine extraction (main._prepare_extractions), so the
    two can never silently drift out of sync with each other.
    """
    bridged = {k: v for k, v in classified.items() if not k.startswith("_")}

    if "manufacturer_name_address" not in bridged:
        for source_field in ("manufacturer_name", "packer_name", "importer_name"):
            data = bridged.get(source_field)
            if data and data.get("value") and str(data["value"]).strip():
                bridged["manufacturer_name_address"] = data
                break

    if "best_before_use_by" not in bridged:
        data = bridged.get("expiry_date")
        if data and data.get("value") and str(data["value"]).strip():
            bridged["best_before_use_by"] = data

    if "wholesale_count_or_net_quantity" not in bridged:
        data = bridged.get("net_quantity")
        if data and data.get("value") and str(data["value"]).strip():
            bridged["wholesale_count_or_net_quantity"] = data

    return bridged


# ---------------------------------------------------------------------------
# EVIDENCE PROVENANCE (P0-1 EVIDENCE INTEGRITY)
# ---------------------------------------------------------------------------

#: Re-exported from `schema` so callers of this module do not need to reach past
#: it for the sentinel. The canonical definition lives with the evidence
#: contract itself; see `schema.UNATTRIBUTED_IMAGE_ID` for why it is not a
#: plausible filename.
UNATTRIBUTED_IMAGE_ID = _UNATTRIBUTED_IMAGE_ID


def stamp_provenance(
    classified: Dict[str, dict],
    image_id: str,
    surface_id: Optional[str] = None,
) -> Dict[str, dict]:
    """
    Record WHICH photograph each field observation came from.

    WHY THIS EXISTS — A MEASURED TRACEABILITY BREAK.
    `ocr_extraction.classify_fields()` returns a bbox for every field it
    extracts, and those bboxes are already scaled back to ORIGINAL image
    coordinates by `run_ocr()`. The schema has somewhere to put them
    (`ExtractedFact.bbox`, `ExtractedFact.evidence`, `EvidenceReference`), and
    the database has an `evidence_json` column to persist them. But the single
    function that joined OCR output to the rule engine did not pass `bbox` or
    `evidence` at all, so `RawExtraction.bbox` was None for every field in the
    live pipeline, `_evidence_for_extraction()` therefore returned an empty
    list, and EVERY finding produced by the API carried no evidence region
    whatsoever. The geometry was computed, then dropped on the floor one call
    before it was needed.

    WHY A PER-FIELD STAMP RATHER THAN A PER-REQUEST ONE. A multi-surface
    session merges observations from several photographs, and
    `merge_classified_fields()` keeps whichever reading has the higher
    confidence. The winning observation of `mrp` may come from the back panel
    while `net_quantity` came from the front. A single request-level image id
    would therefore attribute some findings to the wrong photograph — which is
    worse than no attribution, because it sends a reviewer to an image that
    does not contain the text. Stamping each field dict means provenance
    travels WITH the observation that wins the merge, and no change to the
    merge rule is required.

    Fields whose names begin with "_" are extractor diagnostics rather than
    declarations (e.g. `_auxiliary_dates`, which is a list, not a dict) and are
    passed through untouched.
    """
    stamped: Dict[str, dict] = {}

    for name, data in classified.items():
        if name.startswith("_") or not isinstance(data, dict):
            stamped[name] = data
            continue

        entry = dict(data)
        # Do not overwrite provenance already recorded by an earlier surface:
        # the observation kept by the merge must keep ITS OWN source image.
        entry.setdefault("image_id", image_id)
        if surface_id is not None:
            entry.setdefault("surface_id", surface_id)
        stamped[name] = entry

    return stamped


def build_raw_extraction(field: str, data: Dict[str, Any]) -> "RawExtraction":
    """
    Translate one classified OCR field into the rule engine's contract.

    This lived in `main.py` as `_field_to_raw_extraction`. It moved here for two
    reasons. First, it is domain logic, not HTTP logic, and it belongs beside
    `bridge_classified_fields()`, whose output it consumes. Second — and this is
    why the bug above survived so long — `main.py` imports FastAPI, which is not
    installed in every environment this project is tested in, so nothing that
    lived in `main.py` could be unit tested here at all. The evidence contract
    is too important to be reachable only through an un-runnable module.

    OCR confidence is EXTRACTION confidence. The rule engine remains solely
    responsible for the legal finding and must not read this as legal
    confidence.
    """
    measurement_mode = data.get("measurement_mode", MeasurementMode.UNCERTAIN)

    if isinstance(measurement_mode, str):
        try:
            measurement_mode = MeasurementMode(measurement_mode)
        except ValueError:
            measurement_mode = MeasurementMode.UNCERTAIN

    # "A client-supplied VERIFIED measurement flag is not proof of
    # verification." VERIFIED is only legitimate when it rests on a validated
    # calibration, and this translation layer has no calibration evidence to
    # inspect. Downgrading to ESTIMATED preserves the fact that a measurement
    # was taken while refusing the unproven claim that it was verified; the
    # rule engine can then treat it as an estimate, which it already does.
    # Geometry/calibration may re-establish VERIFIED later, from evidence.
    measurement_downgraded = False
    if measurement_mode == MeasurementMode.VERIFIED and not _has_validated_calibration(data):
        measurement_mode = MeasurementMode.ESTIMATED
        measurement_downgraded = True

    bbox = data.get("bbox")
    image_id = data.get("image_id") or UNATTRIBUTED_IMAGE_ID
    surface_id = data.get("surface_id")

    evidence: List[EvidenceReference] = []
    bbox_model = _bbox_from_sequence(bbox)

    if bbox_model is not None or image_id != UNATTRIBUTED_IMAGE_ID:
        note = "Region located by OCR/CV extraction in original image coordinates."
        if image_id == UNATTRIBUTED_IMAGE_ID:
            note = (
                "Region located by OCR/CV extraction, but no source image was "
                "recorded for this observation. Provenance is incomplete."
            )
        elif measurement_downgraded:
            note = (
                "Region located by OCR/CV extraction in original image "
                "coordinates. A supplied VERIFIED measurement flag was "
                "downgraded to ESTIMATED because no validated calibration "
                "accompanied it."
            )

        evidence.append(
            EvidenceReference(
                image_id=image_id,
                surface_id=surface_id,
                bbox=bbox_model,
                coordinate_system=PositionCoordinateSystem.IMAGE_PIXELS,
                evidence_note=note,
            )
        )

    return RawExtraction(
        field=field,
        value=data.get("value"),
        confidence=float(data.get("confidence", 0.0) or 0.0),
        bbox=bbox_model,
        measured_height_mm=data.get("measured_height_mm"),
        measurement_mode=measurement_mode,
        numeric_value=data.get("numeric_value"),
        numeric_unit=data.get("numeric_unit"),
        raw_text=data.get("raw_text") or data.get("value"),
        normalized_value=data.get("normalized_value"),
        evidence=evidence or None,
    )


def _has_validated_calibration(data: Dict[str, Any]) -> bool:
    """
    True only when the observation carries a calibration that says of ITSELF
    that it was validated.

    Absence of calibration is not evidence of calibration. A bare
    `pixels_per_mm` is not enough either: a scale factor derived from an
    assumed reference size is exactly the kind of estimate that must not be
    promoted to VERIFIED.
    """
    calibration = data.get("calibration")
    if not isinstance(calibration, dict):
        return False
    return bool(calibration.get("validated")) and bool(calibration.get("pixels_per_mm"))


def _bbox_from_sequence(value: Any) -> Optional[BBox]:
    """
    Build a BBox from OCR's (x, y, w, h) tuple.

    `OcrLine.bbox` is documented and constructed as (x, y, w, h), matching
    BBox's own field order. Corner-style (x0, y0, x1, y1) input would silently
    produce a wrong rectangle, so width/height must be positive: BBox enforces
    gt=0 on both, and a zero-area box is rejected here rather than raising.
    """
    if value is None:
        return None
    if isinstance(value, BBox):
        return value

    if isinstance(value, dict):
        try:
            return BBox(
                x=float(value["x"]),
                y=float(value["y"]),
                width=float(value["width"]),
                height=float(value["height"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            x, y, w, h = (float(v) for v in value)
        except (TypeError, ValueError):
            return None
        if w <= 0 or h <= 0 or x < 0 or y < 0:
            return None
        return BBox(x=x, y=y, width=w, height=h)

    return None


def compute_coverage(
    sale_type: str,
    context: Dict[str, Any],
    merged_fields: Dict[str, dict],
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> Tuple[float, List[str]]:
    """
    Return (coverage_fraction, missing_or_low_confidence_field_names) using
    the SAME applicable-requirement logic the legal rule engine will use at
    finalize() time — so the capture UI's "evidence sufficient" signal
    matches what the deterministic engine will actually decide.
    """
    rules = load_rules()
    required = required_declaration_fields(rules, sale_type, context)
    if not required:
        return 1.0, []

    bridged = bridge_classified_fields(merged_fields)

    satisfied = 0
    missing: List[str] = []
    for f in required:
        data = bridged.get(f)
        value = (data or {}).get("value")
        confidence = _field_confidence(bridged, f) if data else 0.0
        if value and str(value).strip() and confidence >= low_confidence_threshold:
            satisfied += 1
        else:
            missing.append(f)

    return satisfied / len(required), missing


def guidance_messages(
    image_quality: ImageQuality,
    coverage: float,
    missing_fields: List[str],
) -> List[str]:
    """
    Human-readable next-step guidance for the mobile/guided-capture client.
    Mirrors the phrasing style specified in the master spec (section 5).
    """
    messages: List[str] = list(image_quality.notes)

    if coverage >= EVIDENCE_SUFFICIENT_COVERAGE:
        messages.append("Evidence sufficient for applicable checks.")
        return messages

    if missing_fields:
        # Surface at most 2 concrete hints per turn to avoid overwhelming
        # the inspector; the full missing list remains in the API response.
        for f in missing_fields[:2]:
            hint = FIELD_CAPTURE_HINTS.get(f)
            messages.append(hint or f"Information not yet located: {f}. Capture another surface.")
        if len(missing_fields) > 2:
            messages.append(f"{len(missing_fields) - 2} more declaration(s) still need to be located.")
    else:
        messages.append("Capture another surface to improve evidence coverage.")

    return messages


@dataclass
class CaptureResult:
    surface: SurfaceObservation
    classified_fields: Dict[str, dict]
    coverage: float
    missing_fields: List[str]
    guidance: List[str]
    evidence_sufficient: bool


def new_surface_id() -> str:
    """
    Mint a surface id before the SurfaceObservation itself is built.

    Provenance has to be stamped onto the OCR fields BEFORE they are folded into
    the session's running field map, but the surface observation is assembled
    after quality and coverage are known. Minting the id up front lets both
    refer to the same surface without reordering the endpoint.
    """
    return f"surf-{uuid.uuid4().hex[:10]}"


def build_surface_observation(
    *,
    image_id: str,
    surface_type: SurfaceType,
    image_quality: ImageQuality,
    coverage: float,
    pdp_bbox_px: Optional[Tuple[float, float, float, float]],
    rotation_index: Optional[int] = None,
    surface_id: Optional[str] = None,
) -> SurfaceObservation:
    pdp_bbox = None
    if pdp_bbox_px is not None:
        x, y, w, h = pdp_bbox_px
        try:
            pdp_bbox = BBox(x=x, y=y, width=w, height=h)
        except Exception:
            pdp_bbox = None

    return SurfaceObservation(
        surface_id=surface_id or new_surface_id(),
        image_id=image_id,
        surface_type=surface_type,
        geometry=GeometryType.UNKNOWN,
        pdp_bbox=pdp_bbox,
        evidence_coverage=max(0.0, min(1.0, coverage)),
        image_quality=image_quality,
        rotation_index=rotation_index,
        notes=list(image_quality.notes),
    )
