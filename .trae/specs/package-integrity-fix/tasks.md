# Package Integrity Truthful Comparison — Implementation Tasks

| Field | Value |
|---|---|
| Spec | `.trae/specs/package-integrity-fix/spec.md` |
| Scope | backend `package_integrity.py` + `main.py` routes + `db/persistence.py` + frontend `usp-components.tsx` + `api-client.ts` types + Hershey's acceptance test |
| Start phase | Implement |

---

## Task 1: Eliminate fabricated default values and arbitrary fallback bboxes/crops in reference extraction

**File:** `backend/package_integrity.py`

### Objective
- Stop injecting DEMO fixture declarations as comparison values (locate and disable the `ref_declarations = dict((ref_metadata or {}).get("declarations") or {})` copy pattern in `compare_reference_vs_inspected_package`).
- Stop generating fallback evidence crops with arbitrary `0.1*rw, 0.35*rh` percent bands when no real bbox is available; instead return `null` crop and `null` bbox.
- Stop emitting the default `[10, 10, 80, 40]` bbox in `detected_differences[]` when no real bbox exists; leave bbox null.

### Changes Required
1. In `compare_reference_vs_inspected_package` (around lines 1526–1551):
   - Initialize `ref_decls`, `ref_bboxes`, `ref_crops`, `ref_ocr_conf` empty.
   - For each reference face image, call `extract_declarations_with_bboxes` — and also extract per-field OCR confidence from `classify_fields` extended return (see Task 2).
   - Merge per-face values, preferring faces that produced a bbox + high confidence.
   - NEVER read `ref_metadata["declarations"]`; only use DEMO metadata for path lookup and `is_curved` flag.

2. In `compare_canonical_fields` (around lines 976–987), delete the fallback `fb_box = [max(0, int(rw * 0.1)), ...]` code and its use. If no `ref_bbox` exists, set `ref_bbox = None` and `ref_crop = None`.

3. In the `differences.append(...)` block (around line 1332–1349):
   - Replace `"bbox": insp_bbox or [10, 10, 80, 40]` with `"bbox": insp_bbox` (allow null).

### Test Requirements

| # | TR | Type | Body |
|---|---|---|---|
| T1.1 | rule | `extract_declarations_with_bboxes` run on `Reference Images/Hershey's REFERENCE BACK.png` returns at least one field with a real bbox (w ≥ 20, h ≥ 8) — not null for every field. |
| T1.2 | rule | Grepping the output of `compare_reference_vs_inspected_package` after the change for the literal `[10, 10, 80, 40]` returns 0 matches in bbox/crop-producing code. |
| T1.3 | rule | Synthetic call with no reference bboxes produces `reference_bbox == None` in the field comparison items, never fabricated rects. |

### Status
- [ ] pending
- [ ] in_progress
- [ ] completed

### Completion Evidence
(to be filled during implementation)

---

## Task 2: Enhance reference extraction to return per-field OCR confidence + face attribution

**File:** `backend/package_integrity.py` (functions `extract_declarations_with_bboxes`, `extract_reference_declarations_from_images`)

### Objective
- Extend extraction so each canonical field returns: `value`, `bbox`, `ocr_confidence`, `source_face_index`.
- Aggregate correctly across multi-face reference and inspection sets.

### Changes Required
1. Modify `extract_declarations_with_bboxes(image_path)` signature/return to:
   `Tuple[Dict[str, Any], Dict[str, List[int]], Dict[str, float]]` — the third dict is per-field confidence.
   - Confidence is read from `v.get("confidence")` if `classify_fields` provides it; otherwise fallback derived from `len(value)` / shape match: `0.70` if numeric pattern matches, `0.55` otherwise (documented, never 0.95 blanket).

2. Create a new aggregator `aggregate_face_extractions(per_face: List[Dict]) -> (decls, bboxes, confs, face_index)` that:
   - For each field key, picks the face extract with the highest confidence AND valid bbox.
   - Logs a message when DEMO metadata declarations are ignored.

3. Apply identical extraction to `inspection_declarations`:
   - If `inspection_declarations` (from Capture Session) is provided with embedded bboxes/confidences → prefer it.
   - Otherwise, re-run extraction per inspection face and aggregate.

### Test Requirements

| # | TR | Type | Body |
|---|---|---|---|
| T2.1 | rule | Aggregation across Hershey's 2 reference faces returns, for MRP or Net Qty, a non-null source_face_index and confidence between 0.50 and 1.00. |
| T2.2 | rule | When Capture Session inspection_declarations contains a real bboxed field, it takes precedence over re-extracted value (verified with a mock override). |

### Status
- [ ] pending
- [ ] in_progress
- [ ] completed

### Completion Evidence
(to be filled)

---

## Task 3: Rewrite the per-field comparison logic in `compare_canonical_fields` for truthful statuses

**File:** `backend/package_integrity.py`

### Objective
- Implement FR2 status taxonomy plus FR4 field rules end-to-end.
- Remove every branch that produces `status = "MATCH"` when `not ref_str`.
- Add the new statuses `REFERENCE_NOT_OBSERVED` and `INSPECTION_NOT_OBSERVED`.
- Combine the full signal mix: OCR similarity + numeric/semantic equality + OCR confidence + image quality.

### Changes Required
1. Introduce new canonical status constants at the top of the file:
   ```
   STATUS_MATCH = "MATCH"
   STATUS_EXPECTED_VARY = "EXPECTED TO VARY"
   STATUS_REVIEW = "REVIEW REQUIRED"
   STATUS_DISCREPANCY = "POTENTIAL DISCREPANCY"
   STATUS_REF_MISSING = "REFERENCE_NOT_OBSERVED"
   STATUS_INSP_MISSING = "INSPECTION_NOT_OBSERVED"
   ```

2. In the field loop:
   - Replace the default block (lines 990–997) which always defaults to MATCH with:
     - if `not ref_str` and `not insp_str` → skip.
     - if `not ref_str` and `insp_str` → status = REFERENCE_NOT_OBSERVED.
     - if `ref_str` and `not insp_str` → status = INSPECTION_NOT_OBSERVED.
   - MRP branch: implement numeric extraction + sticker overlay per FR4.
   - Net Qty branch: numeric + unit.
   - Manufacturer / FSSAI / Barcode / Product / Consumer Care branches: implement per FR4.
   - Batch / MFD / EXP: implement EXPECTED TO VARY + impossible chronology check.

3. For every field, at the end of the loop, only build `FieldComparisonItem` and `DifferenceItem` with:
   - `reference_value = ref_str if ref_str else ""` (never literal "Not specified").
   - `inspection_value = insp_str if insp_str else ""`.
   - `reference_bbox`, `inspection_bbox` null if none.
   - Per-field `ocr_confidence_ref`, `ocr_confidence_insp`, `image_quality_ref`, `image_quality_insp` fields added to `FieldComparisonItem`.

4. Add `source_face_ref` and `source_face_insp` to `FieldComparisonItem` (both optional integers).

### Test Requirements

| # | TR | Type | Body |
|---|---|---|---|
| T3.1 | rule | A unit scenario where ref_str = "" and insp_str = "₹99" for MRP yields status exactly `REFERENCE_NOT_OBSERVED` and never MATCH. |
| T3.2 | rule | A unit scenario where ref_str = "HM10526" and insp_str = "HM20526" for `batch_number` yields status exactly `EXPECTED TO VARY`. |
| T3.3 | rule | A unit scenario where `manufacturing_date = "12/2027"` and `expiry_date = "06/2025"` yields status `POTENTIAL DISCREPANCY` on at least one date field with severity HIGH and finding_category `ACTUAL_DIFFERENCE`. |
| T3.4 | rule | Consumer Care with reference `1800-425-2882, consumercare@hersheys.com` and inspection `1800 425 2882` (spacing difference) yields status ∈ {MATCH, REVIEW REQUIRED} and never POTENTIAL DISCREPANCY. |
| T3.5 | rubric (0–2, ≥ 2) | Signal fusion quality: for 5 synthetic case pairs (close match / ambiguous / clear mismatch / no ref / no insp), correct final status is assigned in all 5 cases. 0 = ≤ 2 correct; 1 = 3–4 correct; 2 = all 5 correct. |

### Status
- [ ] pending
- [ ] in_progress
- [ ] completed

### Completion Evidence
(to be filled)

---

## Task 4: Fix summary_counts and overall report status rollup to include new statuses

**File:** `backend/package_integrity.py`

### Objective
- `summary_counts` includes buckets for `expected_to_vary`, `ref_not_observed`, `insp_not_observed`.
- Overall IntegrityReport status never becomes `NO_SIGNIFICANT_DIFFERENCE_DETECTED` solely due to MATCH-by-default when evidence is missing.

### Changes Required
1. In `compare_reference_vs_inspected_package` after building `canonical_items`:
   - Count properly:
     - `consistent = MATCH + EXPECTED_TO_VARY`
     - `review_required = REVIEW_REQUIRED + REFERENCE_NOT_OBSERVED + INSPECTION_NOT_OBSERVED`
     - `potential_discrepancy = POTENTIAL_DISCREPANCY`
     - Add new integer counts for `expected_to_vary`, `ref_not_observed`, `insp_not_observed`.

2. Overall status logic (around lines 1585–1633):
   - If 2+ POTENTIAL_DISCREPANCY fields or 1 HIGH-severity STATIC POTENTIAL_DISCREPANCY → `STATUS_POTENTIAL_ALT`.
   - Else if all fields are NOT_OBSERVED → `STATUS_UNABLE_TO_VERIFY`.
   - Else if any REVIEW_REQUIRED or NOT_OBSERVED remain → `STATUS_NO_DIFF` with an explanation that lists unreviewed fields.
   - Else → `STATUS_NO_DIFF`.

### Test Requirements

| # | TR | Type | Body |
|---|---|---|---|
| T4.1 | rule | A case with only REFERENCE_NOT_OBSERVED and INSPECTION_NOT_OBSERVED fields produces `UNABLE_TO_VERIFY`, not `NO_SIGNIFICANT_DIFFERENCE_DETECTED`. |
| T4.2 | rule | `summary_counts.consistent` never counts NOT_OBSERVED as consistent. |

### Status
- [ ] pending
- [ ] in_progress
- [ ] completed

### Completion Evidence
(to be filled)

---

## Task 5: Verify persistence load/save roundtrips all new fields; extend serializer

**Files:** `backend/package_integrity.py`, `backend/db/persistence.py`, `backend/main.py`

### Objective
- `FieldComparisonItem.to_dict()` / `IntegrityReport.to_dict()` serialize all new fields (`ocr_confidence_ref`, `ocr_confidence_insp`, `image_quality_ref`, `image_quality_insp`, `source_face_ref`, `source_face_insp`, new statuses).
- DB persistence saves/reloads the full `field_comparisons` JSON unchanged.
- `/integrity/:id` never re-runs OCR or comparison; it only loads the persisted record.

### Changes Required
1. Add the new dataclass fields to `FieldComparisonItem` and `IntegrityReport`.

2. In `main.py` routes `get_inspection_integrity` and `get_integrity_direct`:
   - Read from `db.get_latest_package_integrity_comparison` FIRST.
   - If found → return it directly.
   - Only if NOT found AND auto-compute is enabled (legacy behavior) → run the comparison once and then save.
   - Log explicitly when a persisted record is returned.

3. In `db/persistence.py`:
   - Review `save_package_integrity_comparison` / `get_latest_package_integrity_comparison` / `list_package_integrity_history` and ensure no JSON field truncation or serialization mismatch for the new larger `field_comparisons[]` payload (up to 2 MB allowed).

### Test Requirements

| # | TR | Type | Body |
|---|---|---|---|
| T5.1 | rule | Roundtrip: build a report with `REFERENCE_NOT_OBSERVED` status in one field and `source_face_ref = 1` in another → save → reload → JSON fields equal (dumped with sort_keys → identical strings). |
| T5.2 | rule | Calling `/integrity/:id` twice (via direct function call) after first save performs zero additional `run_ocr` calls (verified via logging level or monkeypatch counter). |

### Status
- [ ] pending
- [ ] in_progress
- [ ] completed

### Completion Evidence
(to be filled)

---

## Task 6: Update API route `/integrity/compare` in `main.py` to accept multi-face inspection paths, run reference + inspection extraction, prefer Capture Session declarations

**File:** `backend/main.py` (routes `compare_package_integrity`, `get_inspection_integrity`)

### Objective
- `/integrity/compare` upload handler always runs the real extraction for BOTH reference and inspection; never DEMO values in the comparison.
- Existing `inspection_declarations` from the stored inspection take precedence when present (enriched with bboxes if missing; re-extract per-face otherwise).

### Changes Required
1. In `compare_package_integrity` route (around lines 2718–2791):
   - Collect all saved inspection image paths for this inspection_id (lookup stored surfaces from detail; fall back to inspecting the UPLOAD_DIR for inspection id-prefixed files).
   - Call `evaluate_package_integrity(inspected_image_paths=..., custom_reference_paths=..., inspection_declarations=detail.get("declarations_surfaces") or detail.get("raw_declarations") or [])`.
   - Persist the result.
   - Attach to `detail["package_integrity"]` and return.

2. Add structured logger output: `pipeline_version = "canonical_extract_v1 + ocr_extract_v2"` on each comparison.

### Test Requirements

| # | TR | Type | Body |
|---|---|---|---|
| T6.1 | rule | Running the compare handler with Hershey's real paths returns a report where the first extracted reference field has a real bbox AND `pipeline_version` is present in the saved record. |
| T6.2 | rule | When `detail` has existing `declarations_surfaces` with a bboxed mrp field, its `value` is preserved (not replaced by a fresh OCR extract); verified with a fake value seeded in `declarations_surfaces`. |

### Status
- [ ] pending
- [ ] in_progress
- [ ] completed

### Completion Evidence
(to be filled)

---

## Task 7: Frontend — truthful display (status pills; never "Not specified" + MATCH; View Evidence modal shows real crops with bbox overlays)

**Files:** `frontend/react-app/src/components/usp-components.tsx`, `frontend/react-app/src/lib/api-client.ts`

### Objective
- Match FR6 display rules.
- Extend `FieldComparisonData` with new status taxonomy and new fields.
- Render crops with actual bbox overlays.

### Changes Required
1. `api-client.ts` `FieldComparisonData`:
   - Add `status` union to include `"REFERENCE_NOT_OBSERVED"` and `"INSPECTION_NOT_OBSERVED"`.
   - Add `ocr_confidence_ref?: number`, `ocr_confidence_insp?: number`, `image_quality_ref?: number`, `image_quality_insp?: number`, `source_face_ref?: number`, `source_face_insp?: number`, `normalized_similarity?: number`, `raw_similarity?: number`.

2. `usp-components.tsx` PackageIntegrityCard:
   - In Reference/Inspection value cells, show an amber "Reference not observed" / "Inspection not observed" string when the value is empty/null, but NEVER green-MATCH alongside these strings.
   - Add status pill color + label for REFERENCE_NOT_OBSERVED and INSPECTION_NOT_OBSERVED (amber, border-amber-500/30).
   - Summary counts: `summaryReviews = summary_counts.review_required + summary_counts.ref_not_observed + summary_counts.insp_not_observed` (or fallback field filter if not present).
   - In the "View Evidence" modal:
     - If a crop base64 exists, render it. Draw a semi-transparent rectangle overlay (purple) on the crop using bbox coordinates. If bbox is null, show "BBox unavailable" badge.
     - Below each crop, show: value + bbox numeric + ocr_confidence + image_quality.
     - Also render the raw/normalized similarity score and reason block.
   - Technical Evidence section is intact (advisory only), but explicitly call out "does not drive per-field status".

### Test Requirements

| # | TR | Type | Body |
|---|---|---|---|
| T7.1 | rule | `tsc --noEmit` passes cleanly after changes (run before accepting the task). |
| T7.2 | rule | Synthetic card render where `reference_value == ""` and `status == "REFERENCE_NOT_OBSERVED"` does not show the green MATCH pill; shows amber REFERENCE NOT OBSERVED; Reference column displays "Reference not observed" and not "Not specified". |
| T7.3 | rubric (0–2, ≥ 2) | Visual fidelity: for a real Hershey's field with crop and bbox, the modal displays reference crop on left, inspection crop on right, bbox overlay visible, and values readable. 0 = missing element; 1 = present but layout issues; 2 = correct. |

### Status
- [ ] pending
- [ ] in_progress
- [ ] completed

### Completion Evidence
(to be filled)

---

## Task 8: Hershey's end-to-end acceptance test

**Files:** `backend/tests/test_hersheys_and_bru_real.py` (extend or create a dedicated section) and manual reload in frontend dev server.

### Objective
Satisfy every rule/rubric AC in spec FR8.

### Changes Required
1. Add to `backend/tests/test_hersheys_and_bru_real.py` a test block `test_hersheys_package_integrity_truthful_comparison` that:
   - Seeds a synthetic inspection_id `test_hersheys_insp_e2e`.
   - Runs `evaluate_package_integrity` with the real Hershey's reference and inspection images from the workspace.
   - Saves to DB.
   - Asserts all ACs A1–A12 and A14–A15 programmatically:
     - A1 grep pattern against the saved JSON.
     - A2/A3 counts fields with valid bboxes/crops.
     - A4 no fabricated bboxes pattern search.
     - A5 status taxonomy + reference_missing invariant.
     - A6 roundtrip equality.
     - A8 Consumer Care status allowed set.
     - A9 variable fields status.
     - A10 MRP sticker/no-sticker branches (seeded scenario tests for both).
     - A11 crops decode as valid.
     - A12 URLs resolve.
     - A15 synthetic no-reference scenario must never yield MATCH.

2. Manual frontend verification (documented as completion evidence):
   - Run the backend and frontend.
   - Create an inspection for Hershey's.
   - Upload the two reference images via PackageIntegrityCard.
   - Capture the rendered `field_comparisons[]` and verify AC7 (no "Not specified" alongside MATCH), then hard-refresh the page and verify AC14 (same comparison_id, same field array).

### Test Requirements

| # | TR | Type | Body |
|---|---|---|---|
| T8.1 | rule | `pytest backend/tests/test_hersheys_and_bru_real.py -k hersheys_package_integrity_truthful_comparison` exits with code 0. |
| T8.2 | rule | Manual evidence: two screenshots (before refresh and after refresh) showing same `comparison_id` and same field summary counts, plus a View Evidence modal with real crops. |
| T8.3 | rule | The persisted JSON file (or DB record) for Hershey's E2E passes A1 grep: `jq '.field_comparisons[] | select(.status == "MATCH" and (.reference_value == "" or .reference_value == "Not specified"))'` returns 0 entries. |

### Status
- [ ] pending
- [ ] in_progress
- [ ] completed

### Completion Evidence
(to be filled)

---

## Task 9: Gated regression guard — remove "Not specified" + MATCH display possibility in both backend and frontend (belt-and-suspenders)

**Files:** `backend/package_integrity.py`, `frontend/react-app/src/components/usp-components.tsx`

### Objective
- Defensive code guards so the safety invariant cannot regress.

### Changes Required
1. Backend: Right before `IntegrityReport` is returned, add a validation sweep:
   ```python
   for fc in field_comparisons_dicts:
       if fc.get("status") == "MATCH":
           assert fc.get("reference_value"), f"MATCH without ref_value: {fc.get('field_key')}"
   ```
   (Production safe: convert to warning log + set status to REVIEW_REQUIRED if violated instead of raising; tests raise.)

2. Frontend: In the field card render, add a guard condition:
   - If status MATCH but `!item.reference_value` → override status display to `REVIEW REQUIRED` amber pill + console.warn.

### Test Requirements

| # | TR | Type | Body |
|---|---|---|---|
| T9.1 | rule | Backend guard: in test mode, a seed scenario with synthetic `status=MATCH, reference_value=""` triggers status override to REVIEW REQUIRED. |
| T9.2 | rule | Frontend guard: render a synthetic item with status MATCH and reference_value empty; the visible pill is not MATCH-green. |

### Status
- [ ] pending
- [ ] in_progress
- [ ] completed

### Completion Evidence
(to be filled)
