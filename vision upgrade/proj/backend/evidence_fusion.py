"""
Cross-engine and cross-image evidence fusion.

Two responsibilities, kept in one module because both feed the same
provenance fields on ExtractedFact (see schema.py):

1. classify_multi_engine()   - Part 5/6 of the master spec: compare what
   Tesseract and (optionally) PaddleOCR each read for the same field on the
   SAME image, and derive an EvidenceVerification state from their agreement.
   Never silently pick "whichever engine has higher confidence" - agreement
   or disagreement is itself evidence.

2. reconstruct_split_fields() - Part 9 of the master spec: a deliberately
   SCOPED split-declaration reconstruction across two captures of the same
   surface/session. This is NOT general image mosaicking or homography
   stitching (see PROJECT_STATE.md "Known limitations" - that remains future
   work). It only joins a label-only fragment (e.g. "MRP (Rs)" with no digits
   at all) in one capture to a syntactically valid value fragment in another
   capture of the SAME session, and only when:
     - the field has no already-confident value from a single image,
     - the join produces a value that satisfies that field's own pattern
       validator (money / date / quantity),
     - there is no competing candidate fragment that would make the join
       ambiguous.
   Any doubt -> UNCERTAIN, not a guess. This directly implements the master
   spec's worked examples: "MRP ₹" + "149.00" -> reconstruct (flagged);
   "MRP ₹1" + unrelated region -> reject (a label entry that already has a
   numeric_value is never touched).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from ocr_extraction import (
    FIELD_PATTERNS,
    OcrLine,
    _extract_date,
    _extract_money,
    _extract_qty,
    _normalized_text,
    classify_fields,
)
from schema import EvidenceVerification

# Fields for which we can meaningfully compare a *normalized* value across
# engines/images. Free-text fields (manufacturer address, consumer care) are
# compared as normalized strings; numeric/date fields are compared on their
# parsed value so that "Rs 420/-" and "₹420.00" are recognised as agreeing.
_NUMERIC_MONEY_FIELDS = {"mrp", "unit_sale_price"}
_DATE_FIELDS = {"mfg_date", "expiry_date"}

# Fields eligible for scoped cross-image fragment reconstruction. Kept small
# and explicit on purpose - see module docstring.
_RECONSTRUCTABLE_FIELDS = {"mrp", "net_quantity", "batch_no"}

LOW_QUALITY_VERIFICATION_CAP = EvidenceVerification.UNCERTAIN


def _comparable_value(field: str, entry: dict) -> Optional[str]:
    """A normalized representation used ONLY to test agreement, not displayed."""
    if field in _NUMERIC_MONEY_FIELDS:
        val = entry.get("numeric_value")
        return f"{float(val):.2f}" if val is not None else None
    if field in _DATE_FIELDS:
        val = entry.get("date_value")
        return str(val) if val else None
    if field == "net_quantity":
        v, u = entry.get("numeric_value"), entry.get("numeric_unit")
        return f"{float(v):.3f}{u}" if v is not None and u else None
    if field == "batch_no":
        val = entry.get("batch_code") or entry.get("value")
        return _normalized_text(str(val)).upper() if val else None
    val = entry.get("value")
    return _normalized_text(str(val)).lower() if val else None


def classify_multi_engine(
    lines_by_engine: Dict[str, List[OcrLine]],
    region_quality_by_field: Optional[Dict[str, "ImageQualityLike"]] = None,
) -> Dict[str, dict]:
    """
    Run classify_fields() independently per engine, then fuse per field.

    `region_quality_by_field` (optional) lets a caller pass in
    image_quality.assess_region_quality() results keyed by field name; a
    LOW_QUALITY region caps that field's verification at UNCERTAIN even if
    engines agree, per the master spec's "corroborated OCR but heavy glare
    must still reduce confidence" rule.

    Output shape is backward-compatible with classify_fields()'s per-field
    dict, with these keys ADDED to every entry:
        ocr_engines         -> list[str]
        verification        -> EvidenceVerification value (string)
        conflicting_values   -> list[str] (only when engines disagreed)
    """
    per_engine: Dict[str, Dict[str, dict]] = {
        engine: classify_fields(lines) for engine, lines in lines_by_engine.items()
        if lines is not None
    }

    all_fields = set()
    for fields in per_engine.values():
        all_fields.update(k for k in fields if not k.startswith("_"))

    fused: Dict[str, dict] = {}
    for field in all_fields:
        contributions: List[Tuple[str, dict]] = [
            (engine, fields[field])
            for engine, fields in per_engine.items()
            if field in fields
        ]
        if not contributions:
            continue

        engines_found = [e for e, _ in contributions]
        comparable = [(e, entry, _comparable_value(field, entry)) for e, entry in contributions]
        known = [c for c in comparable if c[2] is not None]

        # Pick the highest-confidence entry as the displayed value; agreement
        # logic below only changes `verification`/`confidence`, never invents
        # a value that no engine actually produced.
        best_engine, best_entry = max(
            contributions, key=lambda item: float(item[1].get("confidence", 0.0) or 0.0)
        )
        merged = dict(best_entry)
        merged["ocr_engines"] = engines_found

        if len(known) >= 2:
            values = {v for _, _, v in known}
            if len(values) == 1:
                merged["verification"] = EvidenceVerification.CORROBORATED.value
                merged["confidence"] = min(1.0, float(merged.get("confidence", 0.0)) + 0.08)
            else:
                merged["verification"] = EvidenceVerification.CONFLICTING.value
                merged["conflicting_values"] = [f"{e}:{v}" for e, _, v in known]
                merged["confidence"] = min(
                    float(a.get("confidence", 0.0)) for _, a, _ in known
                ) * 0.5
        elif len(engines_found) >= 1:
            merged["verification"] = EvidenceVerification.VERIFIED.value
        else:  # pragma: no cover - unreachable, contributions is non-empty here
            merged["verification"] = EvidenceVerification.NOT_OBSERVED.value

        region_q = (region_quality_by_field or {}).get(field)
        if region_q is not None and getattr(region_q, "status", None) == "LOW_QUALITY":
            if merged["verification"] in (
                EvidenceVerification.CORROBORATED.value,
                EvidenceVerification.VERIFIED.value,
            ):
                merged["verification"] = LOW_QUALITY_VERIFICATION_CAP.value
                merged["confidence"] = min(float(merged.get("confidence", 0.0)), 0.55)
                merged.setdefault("notes", []).append(
                    "Corroborating OCR agreement was capped to UNCERTAIN because this region's "
                    "image quality was assessed as LOW_QUALITY."
                )

        fused[field] = merged

    return fused


def _is_label_only(entry: dict, field: str) -> bool:
    """True when a field entry is JUST the label text with no parsed value at
    all - e.g. OCR read "MRP" or "MRP (Rs)" but no digits followed. This is
    the ONLY situation cross-image reconstruction is allowed to fill in,
    because a label-only entry cannot itself be a wrong/partial number that
    fusion would silently "correct"."""
    if field in _NUMERIC_MONEY_FIELDS:
        return entry.get("numeric_value") is None
    if field == "net_quantity":
        return entry.get("numeric_value") is None
    if field == "batch_no":
        code = entry.get("batch_code") or ""
        # A batch entry that already has an alphanumeric code (even a short
        # one) is not label-only; do not touch it.
        import re as _re
        return not _re.search(r"[A-Za-z0-9]{2,}", str(code))
    return False


def _fragment_candidates(field: str, image_lines: Sequence[OcrLine]) -> List[Tuple[float, OcrLine, str]]:
    """Bare value-shaped fragments in an image that are NOT attached to any
    label (i.e. standalone numbers that could plausibly complete a label
    found in a different image)."""
    out: List[Tuple[float, OcrLine, str]] = []
    for line in image_lines:
        text = line.text
        if field in _NUMERIC_MONEY_FIELDS:
            money = _extract_money(text)
            if money is not None and not FIELD_PATTERNS[field].search(text):
                out.append((line.confidence, line, f"{money:.2f}"))
        elif field == "net_quantity":
            qty = _extract_qty(text)
            if qty is not None and not FIELD_PATTERNS[field].search(text):
                out.append((line.confidence, line, f"{qty[0]:.3f}{qty[1]}"))
        elif field == "batch_no":
            import re as _re
            m = _re.search(r"\b[A-Z0-9][A-Z0-9./_-]{3,}\b", text, _re.I)
            if m and not FIELD_PATTERNS[field].search(text):
                out.append((line.confidence, line, m.group(0).upper()))
    return out


def reconstruct_split_fields(
    session_field_state: Dict[str, dict],
    image_id_owning_label: Dict[str, str],
    other_images_lines: Dict[str, Sequence[OcrLine]],
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
    reconstructed: Dict[str, dict] = {}

    for field in _RECONSTRUCTABLE_FIELDS:
        entry = session_field_state.get(field)
        if not entry or not _is_label_only(entry, field):
            continue

        label_image_id = image_id_owning_label.get(field)
        all_candidates: List[Tuple[float, str, OcrLine, str]] = []
        for image_id, lines in other_images_lines.items():
            if image_id == label_image_id:
                continue
            for conf, line, comparable in _fragment_candidates(field, lines):
                all_candidates.append((conf, image_id, line, comparable))

        if len(all_candidates) != 1:
            # Zero fragments -> nothing to join. More than one plausible,
            # unrelated fragment -> genuinely ambiguous; per spec, reject
            # rather than guess which one is "correct".
            continue

        conf, image_id, line, comparable = all_candidates[0]
        joined_text = f"{entry.get('value', '').strip()} {line.text.strip()}".strip()

        new_entry = dict(entry)
        new_entry["value"] = _normalized_text(joined_text)
        new_entry["source_images"] = sorted({label_image_id, image_id} - {None})
        new_entry["spatial_relationship"] = "cross_image_continuation"
        new_entry["verification"] = EvidenceVerification.UNCERTAIN.value
        new_entry["review_required"] = True
        new_entry["confidence"] = min(
            float(entry.get("confidence", 0.0)), float(line.confidence)
        ) * 0.6
        new_entry["reason"] = (
            f"Reconstructed from a label found in {label_image_id} and a "
            f"matching value fragment found in {image_id}. Flagged for "
            f"human review; not automatically treated as fully verified."
        )

        if field in _NUMERIC_MONEY_FIELDS:
            money = _extract_money(new_entry["value"])
            if money is None:
                continue  # joined text still doesn't parse - do not force it
            new_entry["numeric_value"] = money
        elif field == "net_quantity":
            qty = _extract_qty(new_entry["value"])
            if qty is None:
                continue
            new_entry["numeric_value"], new_entry["numeric_unit"] = qty
        elif field == "batch_no":
            new_entry["batch_code"] = comparable

        reconstructed[field] = new_entry

    return reconstructed
