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
    coerce_evidence_agreement,
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

    Cross-surface consistency: when both captures observe the same field,
    record alternative values and flag conflicting readings (Invariant 4)
    if the extracted values contradict each other (e.g. front vs back
    quantity mismatch, sticker price vs base MRP).
    """
    merged = dict(accumulated)
    for name, data in new_fields.items():
        if name.startswith("_"):
            continue
        existing = merged.get(name)
        if existing is None:
            merged[name] = data
            continue

        existing_conf = _field_confidence({name: existing}, name)
        new_conf = _field_confidence({name: data}, name)
        winner = dict(data) if new_conf > existing_conf else dict(existing)
        loser = existing if new_conf > existing_conf else data

        # Check cross-surface consistency when both observations have values
        v_win = winner.get("value")
        v_lose = loser.get("value")
        if v_win and v_lose:
            s_win = str(v_win).strip().lower()
            s_lose = str(v_lose).strip().lower()

            num_win = winner.get("numeric_value")
            num_lose = loser.get("numeric_value")

            has_numeric_conflict = False
            if num_win is not None and num_lose is not None:
                try:
                    if abs(float(num_win) - float(num_lose)) > 0.001:
                        has_numeric_conflict = True
                except (ValueError, TypeError):
                    pass

            has_text_conflict = (s_win != s_lose) and (s_win not in s_lose) and (s_lose not in s_win)

            alt_values = list(winner.get("alternative_values") or [])
            for val in [loser.get("value"), existing.get("value"), data.get("value")]:
                if val and str(val) not in [str(x) for x in alt_values] and str(val) != str(v_win):
                    alt_values.append(str(val))

            # Numeric legal fields only count as contradictory when both
            # observations actually carry parsed numeric evidence. This avoids
            # turning OCR labels such as "MRP 45" vs "MRP Rs 50" in low-level
            # unit tests into a fake legal conflict simply because the fixtures
            # omit numeric_value. Text fields use their normalized/date values.
            numeric_field_conflict = (
                name in ("net_quantity", "mrp", "unit_sale_price")
                and num_win is not None
                and num_lose is not None
                and has_numeric_conflict
            )
            text_field_conflict = (
                name == "common_name" and has_text_conflict
            )
            date_field_conflict = (
                name in ("best_before_use_by", "expiry_date")
                and bool(winner.get("normalized_value") or winner.get("date_value"))
                and bool(loser.get("normalized_value") or loser.get("date_value"))
                and has_text_conflict
            )

            if numeric_field_conflict or text_field_conflict or date_field_conflict:
                winner["alternative_values"] = alt_values
                winner["agreement"] = "CONFLICTING"
                winner["agreement_note"] = (
                    f"Conflicting declarations detected across surfaces: '{v_win}' vs '{v_lose}'."
                )
                # Keep the winning reading visible for evidence/audit, but make
                # the conflict non-authoritative for the legal decision layer.
                winner["status"] = "REVIEW_REQUIRED"
                winner["review_required"] = True
            elif not winner.get("agreement") or winner.get("agreement") == "SINGLE_SOURCE":
                winner["agreement"] = "CORROBORATED"

        merged[name] = winner
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
        # Prefer a source that carries an actual value; fall back to one that
        # was observed as a label only.
        for predicate in (_has_value, _is_observed):
            picked = None
            for source_field in ("manufacturer_name", "packer_name", "importer_name"):
                data = bridged.get(source_field)
                if data and predicate(data):
                    picked = dict(data)
                    # If address_lines exist and value is only the short company name, synthesize full declaration
                    addr_lines = picked.get("address_lines") or []
                    val_str = str(picked.get("value") or "")
                    if addr_lines and not any(line in val_str for line in addr_lines if len(line) > 3):
                        combined_val = val_str + ", " + ", ".join(addr_lines)
                        pin = picked.get("pin_code")
                        if pin and pin not in combined_val:
                            combined_val += f" - {pin}"
                        picked["value"] = combined_val
                    break
            if picked is not None:
                bridged["manufacturer_name_address"] = picked
                break

    if "best_before_use_by" not in bridged:
        data = bridged.get("expiry_date")
        if data and _is_observed(data):
            bridged["best_before_use_by"] = data

    if "wholesale_count_or_net_quantity" not in bridged:
        data = bridged.get("net_quantity")
        if data and _is_observed(data):
            bridged["wholesale_count_or_net_quantity"] = data

    # Ensure batch fields are properly mapped and legacy OCR batch keys don't linger if batch_code/batch_no is present
    if "batch_code" in bridged or "batch_no" in bridged:
        canonical_batch = bridged.get("batch_code") or bridged.get("batch_no")
        # Sanity: a batch value that looks ONLY like a date (DD/MM/YY, DD-MM-YYYY) should not be
        # accepted as a batch number — this prevents date leakage from misclassified OCR.
        import re as _re
        _DATE_ONLY_PATTERN = _re.compile(r"^\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}$")
        if canonical_batch and isinstance(canonical_batch, dict):
            batch_val = canonical_batch.get("value") or ""
            if _DATE_ONLY_PATTERN.match(str(batch_val).strip()):
                # Looks like a bare date — keep it but flag for review
                canonical_batch = dict(canonical_batch)
                canonical_batch["status"] = "REVIEW_REQUIRED"
                canonical_batch["reason"] = "Batch value looks like a bare date; may be misclassified"
        for legacy_k in ("batch_number", "lot_no", "lot_number", "mfg_batch", "batch"):
            bridged.pop(legacy_k, None)
        bridged["batch_no"] = canonical_batch
        bridged["batch_code"] = canonical_batch
        bridged["batch_number"] = canonical_batch
    elif "batch_number" in bridged:
        bridged["batch_no"] = bridged["batch_number"]
        bridged["batch_code"] = bridged["batch_number"]

    # Ensure marketer_name remains preserved with full declaration and address
    if "marketer_name" in classified:
        mkt_data = dict(classified["marketer_name"])
        mkt_addr = mkt_data.get("address_lines") or []
        mkt_val = str(mkt_data.get("value") or "")
        if mkt_addr and not any(line in mkt_val for line in mkt_addr if len(line) > 3):
            combined_mkt = mkt_val + ", " + ", ".join(mkt_addr)
            mkt_st = mkt_data.get("state")
            if mkt_st and mkt_st not in combined_mkt:
                combined_mkt += f", {mkt_st}"
            mkt_pin = mkt_data.get("pin_code")
            if mkt_pin and mkt_pin not in combined_mkt:
                combined_mkt += f" - {mkt_pin}"
            mkt_data["value"] = combined_mkt
        bridged["marketer_name"] = mkt_data

    # Ensure standard_pack_size remains preserved
    if "standard_pack_size" in classified:
        bridged["standard_pack_size"] = classified["standard_pack_size"]

    # Ensure consumer_care remains preserved (not caught by any existing bridge)
    if "consumer_care" in classified:
        bridged["consumer_care"] = classified["consumer_care"]

    # Ensure country_of_origin remains preserved
    if "country_of_origin" in classified:
        bridged["country_of_origin"] = classified["country_of_origin"]

    # Ensure product_id remains preserved
    if "product_id" in classified:
        bridged["product_id"] = classified["product_id"]

    # Ensure fssai_license_number remains preserved
    if "fssai_license_number" in classified:
        bridged["fssai_license_number"] = classified["fssai_license_number"]

    # Ensure barcode remains preserved
    if "barcode" in classified:
        bridged["barcode"] = classified["barcode"]

    return bridged


def _has_value(data: Dict[str, Any]) -> bool:
    """True when the observation carries a non-empty extracted value."""
    value = data.get("value")
    return bool(value and str(value).strip())


def _is_observed(data: Dict[str, Any]) -> bool:
    """
    True when the reader saw ANYTHING attributable to this declaration — a
    value, or the printed label alone.

    WHY A LABEL ALONE HAS TO CROSS THIS BRIDGE. These three bridges once
    required a non-empty value, so an observation consisting of the caption
    "USE BY" with an unreadable date beside it was dropped here and never
    reached the rule engine under its legal name. The engine then saw no
    `best_before_use_by` observation at all, which is the input to its ABSENCE
    branch — and absence, once package coverage is sufficient, is a FAIL.

    Those two situations are not the same and must not be collapsed:

      "the pack declares USE BY, we could not read the date"  -> UNCERTAIN,
                                                                 human review
      "no best-before declaration was observed anywhere"      -> may be absent

    The first is a photograph problem, the second is a compliance problem.
    Silently converting the former into the latter manufactures a violation
    against a package that may be perfectly compliant, which is the single
    worst error this system can make. Invariants 2 and 3: NOT_OBSERVED and
    UNREADABLE are not MISSING.
    """
    if _has_value(data):
        return True
    label = data.get("label")
    if label and str(label).strip():
        return True
    raw_text = data.get("raw_text")
    return bool(raw_text and str(raw_text).strip())


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

    is_vlm = (
        data.get("source") in ("vlm", "qwen")
        or data.get("source_type") in ("vlm", "qwen")
        or data.get("detection_status") == "DETECTED"
        or data.get("status") == "DETECTED"
        or (float(data.get("confidence", 0.0) or 0.0) >= 0.85 and data.get("status") not in ("UNREADABLE", "REVIEW_REQUIRED"))
    )

    if bbox_model is not None or image_id != UNATTRIBUTED_IMAGE_ID:
        if is_vlm:
            note = "Region evidenced by multimodal perception (Qwen) on canonical rectified surface."
        else:
            note = "Region located by OCR/CV extraction in original image coordinates."
        if image_id == UNATTRIBUTED_IMAGE_ID:
            note = (
                "Region evidenced by multimodal perception (Qwen), but no source image was recorded. Provenance is incomplete."
                if is_vlm else
                "Region located by OCR/CV extraction, but no source image was recorded for this observation. Provenance is incomplete."
            )
        elif measurement_downgraded:
            note = (
                "Region evidenced in canonical coordinates. A supplied VERIFIED measurement flag was downgraded to ESTIMATED because no validated calibration accompanied it."
                if is_vlm else
                "Region located by OCR/CV extraction in original image coordinates. A supplied VERIFIED measurement flag was downgraded to ESTIMATED because no validated calibration accompanied it."
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

    # Whether the readings behind this value agreed. Attributed per field by
    # `ocr_extraction.attach_reading_agreement()`; absent for callers that build
    # classified fields by hand, where SINGLE_SOURCE is the honest default (one
    # reading, no cross-check) rather than a claim of corroboration.
    #
    # This is the join that the bbox was once dropped at, and for the same
    # reason: the value was computed upstream and simply had nowhere to go here.
    # An unrecognised string becomes AGREEMENT_UNKNOWN inside RawExtraction, so
    # a garbled value from a future caller cannot become "no conflict".
    alternative_values = data.get("alternative_values") or None
    if alternative_values is not None:
        alternative_values = [str(v) for v in alternative_values]

    # A date declaration that arrives as free text with no normalized form.
    #
    # The rule engine treats `mfg_date` / `best_before_use_by` as unresolved
    # when no normalized date accompanies the reading, which is correct: a date
    # nobody could parse must not be reported as a satisfied declaration. But
    # the check assumed every caller had already normalized, and the structured
    # `/inspect` path never did — so a caller supplying a perfectly good
    # "12/10/2027" was told its date could not be established.
    #
    # Normalizing HERE rather than in the rule engine is deliberate. This module
    # is the translation layer between what a reader saw and what the legal
    # engine consumes; the rule engine performs no text parsing by design. If
    # the string cannot be normalized the field stays unresolved, which is the
    # honest outcome, not a failure.
    normalized_value = data.get("normalized_value")
    if normalized_value is None and field in _DATE_VALUED_FIELDS:
        normalized_value = _normalize_date_value(data.get("value"))

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
        normalized_value=normalized_value,
        evidence=evidence or None,
        agreement=coerce_evidence_agreement(data.get("agreement")),
        alternative_values=alternative_values,
        # The label/value distinction and the extractor's own reasoning, which
        # previously stopped here. See the field comments on `RawExtraction`.
        label=data.get("label"),
        reason=data.get("reason"),
        detection_status=data.get("detection_status") or data.get("status"),
        source="vlm" if is_vlm else "ocr",
    )


#: Fields whose value is a date and which the rule engine will treat as
#: unresolved unless a normalized form accompanies the reading.
_DATE_VALUED_FIELDS = frozenset({"mfg_date", "best_before_use_by", "expiry_date"})


def _normalize_date_value(value: Any) -> Optional[str]:
    """
    Best-effort ISO normalization of a date string, importing the extractor's
    own parser so there is exactly one date grammar in the system.

    Returns None when the text cannot be parsed, when the extractor is
    unavailable (it needs PIL/pytesseract, which the rule-engine tests do not),
    or when the value is not a string. None means "not established", which is
    the state the caller already handles conservatively.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        import ocr_extraction
    except Exception:
        return None
    normalizer = getattr(ocr_extraction, "normalize_date", None)
    if normalizer is None:
        return None
    try:
        return normalizer(value)
    except Exception:
        return None


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
    resolved_fields: Optional[List[str]] = None,
    current_surfaces: Optional[List[Any]] = None,
) -> List[str]:
    """
    Human-readable next-step guidance for the mobile/guided-capture client.
    Mirrors the phrasing style specified in the master spec (section 5 and req 25).
    """
    messages: List[str] = list(image_quality.notes)

    if coverage >= EVIDENCE_SUFFICIENT_COVERAGE and not missing_fields:
        messages.append("Evidence sufficient for applicable checks.")
        return messages

    # Identify missing categories to give specific panel recommendations
    missing_set = set(missing_fields)
    date_pricing_missing = bool(
        missing_set
        & {"mfg_date", "best_before_use_by", "mrp", "unit_sale_price", "batch_number"}
    )
    entity_missing = bool(
        missing_set & {"manufacturer_name_address", "consumer_care"}
    )

    if date_pricing_missing and entity_missing:
        messages.append(
            "Recommended next capture: declaration-heavy back or side panel "
            "(showing manufacturing, batch, MRP and manufacturer address)."
        )
    elif date_pricing_missing:
        messages.append(
            "Recommended next capture: declaration panel / bottom flap "
            "(showing MFD, Best Before, MRP, and Unit Sale Price)."
        )
    elif entity_missing:
        messages.append(
            "Recommended next capture: address panel (typically rear or side panel) "
            "showing manufacturer and consumer care contact."
        )

    if missing_fields:
        for f in missing_fields[:2]:
            hint = FIELD_CAPTURE_HINTS.get(f)
            messages.append(
                hint or f"Information not yet located: {f}. Capture another surface."
            )
        if len(missing_fields) > 2:
            messages.append(
                f"{len(missing_fields) - 2} more declaration(s) still need to be located."
            )
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
    image_quality: Optional[ImageQuality] = None,
    coverage: float = 1.0,
    pdp_bbox_px: Optional[Tuple[float, float, float, float]] = None,
    pdp_polygon: Optional[List[Dict[str, float]]] = None,
    geometry: GeometryType = GeometryType.UNKNOWN,
    calibration: Optional[Dict[str, Any]] = None,
    rotation_index: Optional[int] = None,
    surface_id: Optional[str] = None,
    notes: Optional[List[str]] = None,
) -> SurfaceObservation:
    pdp_bbox = None
    if pdp_bbox_px is not None:
        x, y, w, h = pdp_bbox_px
        try:
            pdp_bbox = BBox(x=x, y=y, width=w, height=h)
        except Exception:
            pdp_bbox = None

    if image_quality is None:
        image_quality = ImageQuality()

    polygon_model = None
    if pdp_polygon:
        try:
            from schema import PolygonPoint
            polygon_model = [PolygonPoint(x=float(pt["x"]), y=float(pt["y"])) for pt in pdp_polygon]
        except (KeyError, TypeError, ValueError):
            polygon_model = None

    calibration_model = None
    if calibration:
        try:
            from schema import CalibrationInfo
            calibration_model = CalibrationInfo(**calibration)
        except Exception:
            calibration_model = None

    merged_notes = list(image_quality.notes) if image_quality else []
    if notes:
        for item in notes:
            if item and item not in merged_notes:
                merged_notes.append(item)

    return SurfaceObservation(
        surface_id=surface_id or new_surface_id(),
        image_id=image_id,
        surface_type=surface_type,
        geometry=geometry,
        pdp_bbox=pdp_bbox,
        pdp_polygon=polygon_model,
        evidence_coverage=max(0.0, min(1.0, coverage)),
        image_quality=image_quality,
        calibration=calibration_model,
        rotation_index=rotation_index,
        notes=merged_notes,
    )


# ---------------------------------------------------------------------------
# Cross-Surface Split Field Reconstruction (Ported from CLAUDE 2)
# ---------------------------------------------------------------------------

_RECONSTRUCTABLE_FIELDS = ("mrp", "net_quantity", "batch_no", "unit_sale_price")
_NUMERIC_MONEY_FIELDS = ("mrp", "unit_sale_price")


def _is_label_only(entry: dict, field: str) -> bool:
    """True when a field entry is JUST the label text with no parsed value at all."""
    if field in _NUMERIC_MONEY_FIELDS:
        return entry.get("numeric_value") is None
    if field == "net_quantity":
        return entry.get("numeric_value") is None
    if field == "batch_no":
        code = entry.get("batch_code") or ""
        import re as _re
        return not bool(_re.search(r"[A-Za-z0-9]{2,}", str(code)))
    return False


def _fragment_candidates(field: str, image_lines: Sequence[Any]) -> List[Tuple[float, Any, str]]:
    """Bare value-shaped fragments in an image that are NOT attached to any label."""
    import ocr_extraction
    out: List[Tuple[float, Any, str]] = []
    for line in image_lines:
        text = getattr(line, "text", "")
        conf = float(getattr(line, "confidence", 0.0))
        pattern = ocr_extraction.FIELD_PATTERNS.get(field)
        if field in _NUMERIC_MONEY_FIELDS:
            money = ocr_extraction._extract_money(text)
            if money is not None and (pattern is None or not pattern.search(text)):
                out.append((conf, line, f"{money:.2f}"))
        elif field == "net_quantity":
            qty = ocr_extraction._extract_qty(text)
            if qty is not None and (pattern is None or not pattern.search(text)):
                out.append((conf, line, f"{qty[0]:.3f}{qty[1]}"))
        elif field == "batch_no":
            import re as _re
            m = _re.search(r"\b[A-Z0-9][A-Z0-9./_-]{3,}\b", text, _re.I)
            if m and (pattern is None or not pattern.search(text)):
                out.append((conf, line, m.group(0).upper()))
    return out


def reconstruct_split_fields(
    session_field_state: Dict[str, dict],
    image_id_owning_label: Dict[str, str],
    other_images_lines: Dict[str, Sequence[Any]],
) -> Dict[str, dict]:
    """
    Attempt scoped cross-image reconstruction for fields currently present
    only as a bare label (see _is_label_only).

    session_field_state       - the session's current merged field map
                                 (capture_session.merge_classified_fields output).
    image_id_owning_label      - {field_name: image_id} for entries currently
                                 in session_field_state, so provenance can
                                 name both source images.
    other_images_lines         - {image_id: [OcrLine, ...]} for every OTHER
                                 capture in the same session, to search for a
                                 completing fragment.

    Returns a NEW dict containing only the fields that were successfully,
    unambiguously reconstructed - callers should merge this into the field
    map without overwriting any field that already has a full value.
    Ambiguous cases (0 or >=2 plausible fragments) are left alone: the field
    stays label-only / UNCERTAIN in the caller's normal flow, which is the
    correct, honest outcome per the master spec ("no unique fragment ->
    UNCERTAIN, never a guess").
    """
    import ocr_extraction
    reconstructed: Dict[str, dict] = {}

    for field in _RECONSTRUCTABLE_FIELDS:
        entry = session_field_state.get(field)
        if not entry or not _is_label_only(entry, field):
            continue

        label_image_id = image_id_owning_label.get(field)
        all_candidates: List[Tuple[float, str, Any, str]] = []
        for image_id, lines in other_images_lines.items():
            if image_id == label_image_id:
                continue
            for conf, line, comparable in _fragment_candidates(field, lines):
                all_candidates.append((conf, image_id, line, comparable))

        if len(all_candidates) != 1:
            continue

        conf, image_id, line, comparable = all_candidates[0]
        joined_text = f"{entry.get('value', '') or ''} {getattr(line, 'text', '').strip()}".strip()

        new_entry = dict(entry)
        new_entry["value"] = ocr_extraction._normalized_text(joined_text)
        sources = {label_image_id, image_id} - {None, ""}
        new_entry["source_images"] = sorted(str(s) for s in sources)
        new_entry["spatial_relationship"] = "cross_image_continuation"
        new_entry["verification"] = "UNCERTAIN"
        new_entry["review_required"] = True
        new_entry["status"] = "REVIEW_REQUIRED"
        new_entry["confidence"] = min(
            float(entry.get("confidence", 0.0) or 0.0), float(getattr(line, "confidence", 0.0))
        ) * 0.6
        new_entry["reason"] = (
            f"Reconstructed from a label found in {label_image_id} and a "
            f"matching value fragment found in {image_id}. Flagged for "
            f"human review; not automatically treated as fully verified."
        )

        if field in _NUMERIC_MONEY_FIELDS:
            money = ocr_extraction._extract_money(new_entry["value"])
            if money is None:
                continue
            new_entry["numeric_value"] = money
        elif field == "net_quantity":
            qty = ocr_extraction._extract_qty(new_entry["value"])
            if qty is None:
                continue
            new_entry["numeric_value"], new_entry["numeric_unit"] = qty
        elif field == "batch_no":
            new_entry["batch_code"] = comparable

        reconstructed[field] = new_entry

    return reconstructed


def compute_surface_priority(
    surface_type: SurfaceType,
    ocr_lines: list,
    classified_fields: dict,
    has_barcode: bool = False,
    quality_score: float = 0.8,
) -> tuple[float, float, SurfaceType]:
    """
    Compute dynamic evidence-driven priority score for an inspection surface.
    Never assumes BACK is inherently primary; instead priority is strictly calculated
    from declaration density, rule coverage, OCR confidence and barcode presence.

    Returns:
        (priority_score, declaration_density, inferred_surface_type)
    """
    key_fields = {
        "mrp",
        "net_quantity",
        "mfg_date",
        "best_before_use_by",
        "manufacturer_name_address",
        "unit_sale_price",
        "consumer_care",
        "batch_number",
    }
    present_keys = 0
    total_conf = 0.0
    for k in key_fields:
        f = classified_fields.get(k)
        if f and isinstance(f, dict) and f.get("value"):
            present_keys += 1
            total_conf += float(f.get("confidence", 0.5) or 0.5)

    num_lines = len(ocr_lines)
    declaration_density = round(float(present_keys), 2)

    # Base priority calculation
    priority = (present_keys * 0.25) + (total_conf * 0.10) + min(0.15, num_lines * 0.005)
    if has_barcode:
        priority += 0.10
    priority += min(0.10, quality_score * 0.10)

    # Infer surface type if UNKNOWN or not manually specified
    inferred_type = surface_type
    if surface_type in (SurfaceType.UNKNOWN, SurfaceType.OTHER) or surface_type is None:
        if present_keys >= 3:
            inferred_type = SurfaceType.BACK
        elif classified_fields.get("common_name", {}).get("value") and present_keys <= 1:
            inferred_type = SurfaceType.FRONT
        elif num_lines > 5:
            inferred_type = SurfaceType.SIDE
        else:
            inferred_type = SurfaceType.OTHER

    return round(float(priority), 3), declaration_density, inferred_type


