# Workstream 1: Capture & Extraction (multi-surface, detection, multimodal AI)

## Read first
`handoff/00_PROJECT_STATUS_AND_SPLIT.md` — shared ground truth and the
non-negotiable contract. Don't skip it.

## What you're building
Your project needs "upload multiple sides of a product → object detection →
OCR → AI structuring of data." Right now: one photo in, Tesseract OCR +
regex classification out, nothing else. You're closing that gap.

## The one decision that matters most: don't train a detector from scratch

Your pitch says "object detection model CV." The honest engineering answer
for a hackathon team with no GPU cluster and no labeled training set is:
**do not try to train a YOLO-style detector.** You will not have enough
labeled images, and a half-trained detector is worse than an honest
heuristic — it produces confident-looking wrong boxes.

The better fit for your actual constraints, and genuinely the more
defensible "AI Differentiator" for judges, is: **use a multimodal LLM
(Claude, with vision input) as the detection+extraction step**, not a
trained CV model. Concretely: send the package photo to Claude with a
prompt asking for structured JSON — every declaration field's text, its
approximate bounding box (as a fraction of image width/height), and a
confidence/uncertainty note per field. This is:
- Actually "multimodal AI extracts text, fields, spatial information" —
  literally true, not a stretch.
- Buildable by one person in this timeframe.
- Better on messy real photos than regex+Tesseract, based on what we've
  already seen fail (label/value column mixups, degraded print misreads).

`vlm_verifier.py` already has a working Anthropic API integration pattern
(system prompt, JSON-only response contract, fail-closed parsing) — follow
that same shape for a new `vision_extraction.py` module. Don't replace
`ocr_extraction.py` outright; treat it as a fallback/cross-check path (two
independent extraction methods agreeing raises confidence; disagreeing is
itself a useful UNCERTAIN signal).

## Concrete deliverables

1. **`backend/vision_extraction.py`** — Claude-vision-based extraction.
   Input: image bytes. Output: same field dict shape `ocr_extraction.py`'s
   `classify_fields()` produces (`{field: {value, confidence, bbox,
   numeric_value, numeric_unit}}`), so it's a drop-in alternative, not a
   parallel system `main.py` has to special-case. Test against the real
   product photos in `dataset/` and any new ones you get — show the actual
   output, including where it disagrees with the Tesseract path.

2. **Multi-surface capture support.** Change `/scan` (or add `/scan-multi`)
   to accept a **list** of images (`files: List[UploadFile]`), each tagged
   with a `surface_type` (front/back/side/label — see `schema.py`'s
   `SurfaceType` enum, already defined, never used). For each image, build a
   real `SurfaceObservation` (also already defined, never instantiated) and
   populate `ProductInspection.captures`. Merge extracted fields across
   surfaces: if `common_name` is only on the front and `mrp` only on the
   back, the merged result should have both, not report one as missing
   because it looked at the other photo. This directly fixes the
   "common_name missing" false-FAILs you saw throughout earlier testing —
   those weren't extraction bugs, they were single-photo-capture limitations.

3. **Evidence-coverage-aware absence.** `schema.py`'s `ImageQuality`,
   `EvidenceReference`, and `InspectionSummary.evidence_complete` fields
   exist for this: a field should only be marked FAIL-for-absence when the
   captured surfaces plausibly should have shown it and didn't; otherwise
   it's UNCERTAIN ("not evidenced yet," not "confirmed missing"). Check
   `rule_engine.py`'s current mandatory-field logic — confirm whether it
   already does this correctly for single-surface input, and extend it for
   multi-surface.

4. **PDP/declaration-region localization.** If you want visual bounding-box
   overlays for the (separate team's) frontend, the vision-LLM approach in
   (1) already gives you approximate boxes for free. Don't build a second,
   separate detection system for this.

## What to explicitly test and report back

- Run your new extraction against every real photo already in this project
  plus at least 3 new ones your team photographs, and show side-by-side
  output vs. the existing Tesseract path.
- Test multi-surface merging with a real front+back pair — confirm
  `common_name` (front-only) and `mrp` (back-only) both resolve correctly
  in the merged result, and that overall_status doesn't wrongly FAIL for a
  field that was simply on the other photo.
- State plainly which photos your new path handles better/worse than the
  old one. Don't claim uniform improvement without checking.

## Files to upload to this Claude session

From the project zip: `backend/schema.py`, `backend/ocr_extraction.py`,
`backend/main.py`, `backend/vlm_verifier.py` (as the Anthropic-API-usage
pattern to follow), `backend/rule_engine.py` (to see how it reads
`captures`/absence), `handoff/00_PROJECT_STATUS_AND_SPLIT.md`, and 2-3 real
product photos (front+back pairs if possible).
