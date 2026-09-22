# Package Integrity Truthful Comparison — Specification

## Problem

The Package Integrity verification subsystem is producing untrustworthy results:

1. Reference images fail to render in the UI despite existing file paths.
2. Reference fields display "Not specified" even though reference images clearly contain the declaration text.
3. Fields with no reference value are incorrectly marked `MATCH`.
4. Bounding boxes and evidence crops do not localize to the actual declaration on the image; generic/fallback bboxes are used.
5. Evidence crops are missing, placeholdered, or generated from arbitrary fallback regions.
6. Generic full-image similarity metrics (Sim 0%, layout analysis) drive statuses without localized evidence.
7. Consumer Care is incorrectly flagged despite semantically matching contact evidence.
8. Comparisons produce random/false matches and do not use the system's real OCR/VLM/canonical-field pipeline.

The subsystem must produce truthful comparisons, driven by actual extracted evidence, never by defaults or fabrication.

## Users

- Inspector / Reviewer: performs a package inspection, uploads reference packaging, clicks View Evidence, and must trust what is shown.
- Senior Officer: reviews integrity comparisons, including persisted history, and relies on bbox-validated evidence.
- Consumer Portal user: uploads a package photo for integrity screening and expects accurate, non-fabricated results.

## Goals

- Rebuild the Package Integrity comparison to flow real OCR/VLM-derived canonical fields + actual bboxes + genuine evidence crops on both the Reference and Inspection sides.
- Guarantee the safety invariant that a field is never marked MATCH without genuine reference evidence supporting that match.
- Ensure every persisted comparison reloads identically (deterministic, no recomputation across refresh).
- Make "View Evidence" open actual crops with real bboxes, real values, and real OCR/VLM confidence.
- Correctly classify fields by behavior (static, variable, version-sensitive) and apply field-aware matching.
- Pass the Hershey's FRONT/BACK reference + inspection acceptance test end to end.

## Non-Goals

- Do not invent a new OCR/VLM engine or rule engine.
- Do not replace Capture Session / OCR extraction / semantic parsing / evidence provenance already implemented elsewhere.
- Do not alter the statutory Rule Engine or FSSAI/Departmental verification pipelines.
- Do not alter package upload capture, preprocessing, orientation, or the scan animation.

## Functional Requirements

### FR1. Reference and Inspection Evidence Extraction

Given a set of Reference face images and a set of Inspection face images (Front, Back, etc.), the integrity module MUST run the real, existing `ocr_extraction.run_ocr` + `classify_fields` / Capture Session canonical field extraction pipeline on each face independently, then aggregate findings across faces to build:

- `reference_declarations: Dict[field_key, value]`
- `reference_bboxes: Dict[field_key, [x,y,w,h]]` in the original source image coordinates
- `reference_face_for_field: Dict[field_key, face_index]`
- `reference_crops: Dict[field_key, data URI]` cropped from the actual source image + real bbox
- `reference_ocr_confidence: Dict[field_key, float]` from the pipeline

Identical extraction MUST occur for `inspection_declarations`, `inspection_bboxes`, `inspection_face_for_field`, `inspection_crops`, `inspection_ocr_confidence`.

No value may be copied from DEMO fixtures or hardcoded dictionaries unless the extraction pipeline genuinely produced no result AND the field is still evaluated as evidence-missing (see FR2).

### FR2. Evidence Provenance and Truthful Status Taxonomy

For every field comparison, the system MUST use exactly one of the following statuses, driven solely by actual evidence present or absent:

- `MATCH`: Both reference and inspection evidence exist; values are equivalent under field-specific rules (see FR4); and at least one strong signal (OCR norm sim ≥ 0.85 OR semantic match for text fields OR canonical numeric equality for price/qty/barcode) confirms the match.
- `EXPECTED TO VARY`: Both values exist; the field classification is VARIABLE (batch_number, manufacturing_date, expiry_date); and values are plausibly different production lot values (e.g., different dates/different batch ids; but chronology is not impossible).
- `REFERENCE_NOT_OBSERVED`: The reference extraction did not produce a value for this field (no DEMO fallback, no hardcoded "Not specified" → MATCH bridge).
- `INSPECTION_NOT_OBSERVED`: The inspection extraction did not produce a value for this field; no default match.
- `REVIEW REQUIRED`: Any ambiguous case: low OCR confidence (< 0.70 for STATIC fields, < 0.55 for VARIABLE), bbox missing or degenerate (< 8 px wide/high), OCR similarity in [0.45, 0.85] for text fields, degraded image quality (blur/glare), OCR_UNCERTAINTY category, or Consumer Care semantic match is weak.
- `POTENTIAL DISCREPANCY`: Strong opposing evidence on a STATIC or VERSION_SENSITIVE field (OCR sim < 0.45 with high confidence on both sides, real bboxes + real crops exist, and version/pricing overlay check does not show legitimate version update for VERSION_SENSITIVE).

Hard invariant (SAFETY RULE):

> If `reference_value` is genuinely absent (not extracted by the pipeline), the status MUST be `REFERENCE_NOT_OBSERVED` or `REVIEW REQUIRED` (if inspection also lacks evidence), and MUST NEVER be `MATCH` or `EXPECTED TO VARY`.

Likewise, when the UI displays "Not specified" as a fallback string for a missing reference_value, that display string MUST NOT participate in equality and MUST NOT produce MATCH. The frontend MAY show "Not specified" only when the status is REFERENCE_NOT_OBSERVED/REVIEW_REQUIRED.

### FR3. Bounding Boxes and Evidence Crops

Every `reference_bbox` and `inspection_bbox` MUST originate from the actual extraction pipeline (`bbox` field returned by `classify_fields` or Capture Session canonical surface evidence).

- If a valid `[x,y,w,h]` with w≥10 and h≥8 is returned by the pipeline, use it verbatim.
- If the pipeline returned no bbox, the comparison MUST store `reference_bbox = null` / `inspection_bbox = null`.
- Under NO circumstances fabricate a fallback bbox such as `[10,10,80,40]`, arbitrary percentile bands (`0.1*rw, 0.35*rh, …`), or generic area guesses.
- An evidence crop MUST be produced only when a genuine bbox exists. If no bbox, crop is `null` and the UI shows "No localized bbox for this field; evidence unavailable."

BBox coordinates MUST be in the original image pixel coordinate system, with no post-hoc scaling unless the crop is generated from the same image the bbox was computed on. For "View Evidence", the crop is rendered as a real image, not a text placeholder.

### FR4. Field-Specific Comparison Logic

Every field comparison MUST combine the following signals (NOT raw string equality alone):

- `ocr_raw_similarity` (SequenceMatcher on light-normalized strings)
- `ocr_normalized_similarity` (with substitution table, punctuation removal, abbreviation expansion)
- `semantic_value_equality` (numeric extraction for MRP/USP/Net Qty/Barcode/FSSAI, date parsing for MFD/EXP, digit-sequence matching for Consumer Care phone numbers, token containment for manufacturer names)
- `ocr_confidence_ref`, `ocr_confidence_insp` (from pipeline)
- `image_quality_ref`, `image_quality_insp` (sharpness, glare from `assess_region_quality` on real crops)
- `field_classification` (STATIC / VARIABLE / VERSION_SENSITIVE)

Status determination rules per field:

**MRP (VERSION_SENSITIVE):**
- Parse numeric values `r_num`, `i_num` from both sides (extracted currency + decimal digits).
- If r_num == i_num → MATCH.
- If r_num is genuinely missing → REFERENCE_NOT_OBSERVED.
- If r_num and i_num both exist and differ:
  - Run sticker overlay detection on the inspection bbox.
  - If sticker overlay confirmed (sticker border detected + high contrast paper patch): POTENTIAL DISCREPANCY / HIGH severity.
  - Otherwise (clean direct print): REVIEW REQUIRED (indicates a pricing version update, not tampering).

**Net Quantity (STATIC):**
- Extract numeric value + unit.
- Numeric equality AND unit compatibility → MATCH.
- If numeric value differs or is indeterminate with high confidence real bboxes on both sides AND quality is not degraded → POTENTIAL DISCREPANCY.
- Otherwise → REVIEW REQUIRED.

**Manufacturer / Marketer (STATIC):**
- Token containment match + OCR normalized similarity.
- Similarity ≥ 0.75 OR either side is a substring of the other (after ltd/pvt abbreviation expansion) → MATCH.
- Similarity in [0.45, 0.75) with degraded quality or low OCR conf → REVIEW REQUIRED.
- Below with strong opposing evidence → POTENTIAL DISCREPANCY.

**Consumer Care (STATIC):**
- Match primarily by digit-sequence inclusion in phone numbers (first ≥6 digit long runs).
- Secondary: email domain match.
- Tertiary: brand-word containment ("hershey", "unilever", "nestle", etc.) if present in both.
- If any one of these signals is strong → MATCH.
- If none strong but OCR similarity ≥ 0.45 → REVIEW REQUIRED.
- Must never be POTENTIAL DISCREPANCY on brittle raw-string differences alone.

**FSSAI License (STATIC):**
- Digit-only normalized comparison of 14-digit sequences.
- Equality or OCR-confusion-repaired equality → MATCH.
- Otherwise with quality degradation → REVIEW REQUIRED.

**Barcode / GTIN (STATIC):**
- Digit-only normalized equality (allowing 0↔O, 1↔I glyph repair).
- Clean direct print mismatch → POTENTIAL DISCREPANCY.

**Batch / MFG / EXP (VARIABLE):**
- If chronologically impossible (MFD later than EXP on inspection): POTENTIAL DISCREPANCY regardless.
- Otherwise, if both values exist and differ naturally: EXPECTED TO VARY.
- If reference missing and inspection exists: REFERENCE_NOT_OBSERVED.

### FR5. Comparison Record Persistence

Every comparison run MUST persist a record with:

```
comparison_id: uuid hex
inspection_id: string
reference_id?: string (or uploaded reference set identifier)
reference_image_ids: list of source filenames/paths
inspection_image_ids: list of source filenames/paths
field_comparisons: [
  {
    field_key, field_name, field_classification,
    reference_value, inspection_value,
    reference_bbox, inspection_bbox,
    reference_crop_ref (or base64 when under size limit),
    inspection_crop_ref,
    ocr_confidence_ref, ocr_confidence_insp,
    image_quality_ref, image_quality_insp,
    ocr_raw_similarity, ocr_normalized_similarity,
    status, reason, observation_note, severity,
    source_face_ref, source_face_insp
  }
]
summary_counts: {consistent, review_required, potential_discrepancy, total_evaluated, expected_to_vary, ref_not_observed, insp_not_observed}
status: NO_SIGNIFICANT_DIFFERENCE_DETECTED | POTENTIAL_ALTERATION_DETECTED | UNABLE_TO_VERIFY
confidence_score: float
timestamp: ISO 8601 UTC
pipeline_version: string (e.g., "canonical_extract_v1 + ocr_extract_v2")
reference_type: TRUSTED | DEMO | UNVERIFIED
reference_name: string
```

On reload (`GET /integrity/:id` or `GET /inspections/:id/integrity`), the latest persisted record MUST be returned byte-for-byte identical. No recomputation unless the caller explicitly POSTs `/integrity/compare` with new files.

Persistence MUST use the existing `db.save_package_integrity_comparison` / `db.get_latest_package_integrity_comparison` / `db.list_package_integrity_history`, with JSON fields guaranteed to roundtrip.

### FR6. Truthful Frontend Rendering

The frontend `PackageIntegrityCard` in `usp-components.tsx` MUST:

1. Show every field with truthful labels:
   ```
   MRP
   Reference: ₹99     (or "Reference not observed" when genuinely absent)
   Inspection: ₹99
   ✓ MATCH
   ```
2. For each field status, map:
   - `REFERENCE_NOT_OBSERVED` → amber pill with label "REFERENCE NOT OBSERVED" + show "No reference evidence" in the Reference value column.
   - `INSPECTION_NOT_OBSERVED` → amber pill with label "INSPECTION NOT OBSERVED".
   - `REVIEW REQUIRED` → amber pill.
   - `EXPECTED TO VARY` → purple pill.
   - `POTENTIAL DISCREPANCY` → red pill.
   - `MATCH` → green pill.
3. Never show "Not specified" alongside `MATCH`.
4. "View Evidence" modal MUST render:
   - Left column: REFERENCE crop (real image; real bbox overlay drawn on the crop; reference value below; reference bbox numeric; OCR conf; quality).
   - Right column: INSPECTION crop (real image; real bbox overlay; inspection value; bbox numeric; OCR conf; quality).
   - Bottom: Forensic Evaluation with status + reason + observation note.
   - If crop/bbox is missing: show "Evidence unavailable for this field (no localized bbox)."
5. Summary counts 3-pillar display MUST count:
   - consistent = MATCH count + EXPECTED TO VARY count
   - review_required = REVIEW_REQUIRED count + REFERENCE_NOT_OBSERVED count + INSPECTION_NOT_OBSERVED count
   - potential_discrepancy = POTENTIAL_DISCREPANCY count
6. Generic Technical Evidence metrics (layout sim, global fidelity) remain under the collapsed section but must not be referenced by or drive the per-field status (they are advisory only).

### FR7. API Contract

`POST /integrity/compare` (in `main.py`) MUST:

- Accept `inspection_id`, `reference_type`, and multipart `reference_files[]`.
- Also accept optional `inspection_files[]` for re-processing inspection faces (otherwise reuse existing persisted scan surfaces).
- Resolve actual source image paths on disk, run the canonical extraction on both reference and inspection independently.
- Build the IntegrityReport according to FR1–FR5.
- Persist via `save_package_integrity_comparison`.
- Return the full report including complete `field_comparisons[]` with bboxes, crop data references, confidences, and statuses.

`GET /integrity/:id` and `GET /integrity/:id/history` MUST return persisted data without re-running OCR or comparison.

### FR8. Acceptance Test — Hershey's

Using the files already present in the workspace:

Reference: `Reference Images/Hershey's REFERENCE FRONT.png` and `Reference Images/Hershey's REFERENCE BACK.png`

Inspection: `images new/Hershey's FRONT.jpeg` and `images new/Hershey's Back.jpeg`

Before the fix is accepted, verify ALL of:

1. Reference images render in the Reference Faces gallery.
2. Inspection images render in face_matches.
3. Reference OCR genuinely extracts values from the reference images (not DEMO fixtures) for MRP, Net Qty, Manufacturer, Consumer Care, FSSAI, and dates where present.
4. Inspection OCR genuinely extracts values from the inspection images.
5. Every field in `field_comparisons` that has a status also has either valid bboxes + crops OR `REFERENCE_NOT_OBSERVED` / `INSPECTION_NOT_OBSERVED` / `REVIEW_REQUIRED` status, never MATCH with missing evidence.
6. BBox coordinates actually point to the text region on their source face (e.g., MRP bbox on the Hershey's back contains the price, not arbitrary coordinates).
7. Clicking "View Evidence" for MRP, Net Qty, Manufacturer, and Consumer Care shows real, correctly localized crops, not placeholders.
8. There is zero occurrence of `reference_value: "Not specified"` combined with `status: "MATCH"` in any persisted record (verified via grep of JSON record + in-memory assertion).
9. No generic "packaging layout variation" discrepancy is produced unless at least one STATIC field has genuine bbox-level mismatch.
10. Consumer Care comparison returns MATCH or REVIEW_REQUIRED when phone number digits match (it must never return POTENTIAL DISCREPANCY due to punctuation/formatting differences alone).
11. MRP, batch, dates, and net quantity each respect their field behavior rules (VARIABLE fields differ → EXPECTED TO VARY; STATIC mismatch with clean print → POTENTIAL DISCREPANCY or REVIEW REQUIRED; VERSION_SENSITIVE price diff with clean print → REVIEW REQUIRED).
12. Refreshing the frontend page after comparison produces the EXACT same `comparison_id`, same `field_comparisons[]` array, same statuses, same values, same bboxes (deterministic reload from persistence, not recomputation).

## Non-Functional Requirements

### NFR1. Performance
Comparison with 2 reference faces + 2 inspection faces must complete in ≤ 15 seconds (excluding network VLM calls). Heavy Gemini escalation runs only on genuinely ambiguous fields and is skipped during tests.

### NFR2. Determinism
Identical inputs (same files, same timestamp, same random seed for ORB) must produce identical `field_comparisons[]` outputs (within bbox integer rounding).

### NFR3. Security / No Fabrication
Code-level invariant: The word `fabricat` / `placeholder` / generic fallback rect `[10,10,80,40]` and the arbitrary `0.1*rw, 0.35*rh` bands MUST NOT appear anywhere in the comparison extraction or crop-generation path (only in comments explaining why they are forbidden). Grep rule added in CI-style task to verify.

### NFR4. Observability
`logger` entries are produced at INFO for each field comparison decision, including all contributing signals and the chosen status. WARNINGs are emitted when an evidence crop cannot be produced due to missing bbox.

## Constraints

- Reuse only: `ocr_extraction.run_ocr`, `ocr_extraction.classify_fields`, `capture_session` surface/field extraction, `barcode_decode`, `compute_ocr_similarity`, `normalize_ocr_text`, `parse_commodity_date`, `detect_sticker_overlay`, `assess_region_quality` — all already present in the codebase.
- DEMO reference fixtures may be used ONLY to locate reference image paths; their `declarations` dicts MUST NOT be injected into the comparison as values. They must be replaced by actual OCR runs on the referenced paths.
- No new pip install; no new npm install.
- Frontend types in `api-client.ts` are extended but not broken. Backward-compatible serialization.

## Dependencies

- Python 3.11 environment in `backend/` with existing `requirements.txt`.
- React + Vite + TypeScript frontend in `frontend/react-app/`.
- PostgreSQL (or JSON fallback) persistence via `backend/db/persistence.py`.
- Real image files in `Reference Images/` and `images new/`.

## Assumptions

- Capture Session already produces, for the inspected package, canonical declarations with bboxes via its own OCR/VLM pipeline (`inspection_declarations`). If this data is present, it takes precedence over re-running OCR; otherwise OCR is re-run from the stored image files.
- `/uploads/*` URLs correctly serve files from `config.UPLOAD_DIR` or an equivalent static route.

## Open Questions

(O1) — In `main.py /integrity/compare`, when inspection_declarations are already persisted in the detail object, should the comparison consume them as-is (preferred) or force a fresh OCR run? **Answer in task:** Prefer persisted inspection_declarations when available; otherwise re-extract and persist the derived data, but log a WARNING.

---

## Acceptance Criteria

Every AC below is either `rule` (objective pass/fail) or `rubric` (scored evaluative):

| # | AC | Type | Rule / Rubric Body |
|---|---|---|---|
| A1 | No `MATCH` without reference evidence | rule | In the persisted comparison JSON record, no object in `field_comparisons[]` may have `status == "MATCH"` AND `reference_value == "" or null or "Not specified"`. Grep + JSON assertion in test must pass. |
| A2 | Genuine extraction from reference images | rule | For the Hershey's acceptance test run, at least 3 STATIC fields (from: MRP, Net Qty, Manufacturer, FSSAI, Consumer Care, Barcode) must have non-empty `reference_value`, non-null `reference_bbox` with w≥20 and h≥10, and non-null `reference_crop_base64`. |
| A3 | Genuine extraction from inspection images | rule | Same as A2 but for the inspection side: matching 3+ fields with non-empty `inspection_value`, valid bbox, valid crop. |
| A4 | No fabricated bboxes | rule | Grep the entire comparison code path (`compare_canonical_fields`, `_make_evidence_crop` callers, `extract_declarations_with_bboxes`, and the Hershey's persisted output JSON). The literal `[10, 10, 80, 40]` and the `0.1*rw, 0.35*rh` arbitrary-band pattern must not produce any output bbox or crop. All bboxes must have been returned by the OCR/classify pipeline or Capture Session surface evidence. |
| A5 | Status taxonomy correctness | rule | For every field in the persisted Hershey's comparison, status ∈ {MATCH, EXPECTED TO VARY, REVIEW REQUIRED, POTENTIAL DISCREPANCY, REFERENCE_NOT_OBSERVED, INSPECTION_NOT_OBSERVED}. If `reference_value` is empty → status ≠ MATCH and ≠ EXPECTED TO VARY. |
| A6 | Persistence determinism | rule | After running the Hershey's comparison once and saving, reload via `db.get_latest_package_integrity_comparison(inspection_id)` twice in a row and verify that `json.dumps(rec1, sort_keys=True) == json.dumps(rec2, sort_keys=True)` and that no additional OCR work is performed (no `run_ocr` calls on reload path; assert via logging mocks). |
| A7 | Frontend truthful display | rubric (0-2, threshold ≥ 2) | Frontend `PackageIntegrityCard` — when fed the persisted Hershey's record — displays: (a) no MATCH card with "Not specified" in Reference column, (b) status pills use the correct color per FR6, (c) View Evidence modal for MRP and Consumer Care opens and displays reference and inspection crops that are genuine (not text placeholders). 0 = any failure; 1 = mostly correct with minor cosmetic; 2 = fully correct. |
| A8 | Consumer Care semantic correctness | rule | For the Hershey's record, if the extracted reference and inspection consumer care values share ≥ 6 contiguous digits in their phone numbers, the status MUST be ∈ {MATCH, REVIEW REQUIRED} and MUST NOT be POTENTIAL DISCREPANCY. |
| A9 | Variable fields classification | rule | Batch, MFG date, and EXP date in Hershey's record — if both sides have values and they differ legitimately — MUST have status `EXPECTED TO VARY` (not POTENTIAL DISCREPANCY or MATCH-by-default). |
| A10 | Version-sensitive MRP handling | rule | If MRP values differ but there is no sticker overlay (clean direct print), status MUST be `REVIEW REQUIRED` and MUST NOT be `POTENTIAL DISCREPANCY`. Conversely, if sticker overlay is detected and MRP differs, status MUST be `POTENTIAL DISCREPANCY` with severity HIGH. |
| A11 | View Evidence crops and bboxes valid | rule | For each of the 3+ fields that have crops (from A2/A3), the reference_crop_base64 and inspection_crop_base64 MUST decode as valid JPEG/PNG (imread succeeds) and have non-empty pixel content (average color not uniform pure black/white). |
| A12 | Reference and Inspection images render | rule | In the Technical Evidence gallery section for Hershey's, `reference_image_urls` all load 200 OK and frontend `<img>` tags show the images (verified by checking the persisted report includes reachable URLs and that loading them through the static file server succeeds). |
| A13 | No generic layout discrepancy | rule | In the Hershey's persisted record `detected_differences[]`, there is no entry whose `difference_type` mentions generic layout or "Sim: 0%" without a corresponding STATIC field mismatch supported by real bboxes and crops. |
| A14 | Reload produces identical comparison_id | rule | Frontend reload (refresh page) after comparison → the `data.comparison_id` from the second `getPackageIntegrity()` call equals the first one exactly, and `data.field_comparisons.map(f => [f.field_key, f.status])` arrays are byte-equal (same ordering and values). |
| A15 | Safety invariant unit tests | rule | Run `backend/tests/test_hersheys_and_bru_real.py` (or add a focused assertion test inside it) that asserts for a synthetic record with missing `reference_value` that the produced status is never MATCH and that the persisted JSON passes the A1 grep rule. |
