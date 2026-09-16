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
    GeometryType,
    ImageQuality,
    SurfaceObservation,
    SurfaceType,
)
from rule_engine import required_declaration_fields, load_rules

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


def build_surface_observation(
    *,
    image_id: str,
    surface_type: SurfaceType,
    image_quality: ImageQuality,
    coverage: float,
    pdp_bbox_px: Optional[Tuple[float, float, float, float]],
    rotation_index: Optional[int] = None,
) -> SurfaceObservation:
    pdp_bbox = None
    if pdp_bbox_px is not None:
        x, y, w, h = pdp_bbox_px
        try:
            pdp_bbox = BBox(x=x, y=y, width=w, height=h)
        except Exception:
            pdp_bbox = None

    return SurfaceObservation(
        surface_id=f"surf-{uuid.uuid4().hex[:10]}",
        image_id=image_id,
        surface_type=surface_type,
        geometry=GeometryType.UNKNOWN,
        pdp_bbox=pdp_bbox,
        evidence_coverage=max(0.0, min(1.0, coverage)),
        image_quality=image_quality,
        rotation_index=rotation_index,
        notes=list(image_quality.notes),
    )
