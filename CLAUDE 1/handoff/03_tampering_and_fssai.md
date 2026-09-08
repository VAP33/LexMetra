# Workstream 3: Tampering Detection + FSSAI Cross-Verification (USP 1 & 2)

## Read first
`handoff/00_PROJECT_STATUS_AND_SPLIT.md` — shared ground truth and the
non-negotiable contract. Don't skip it.

## What already exists — and why it's NOT your USP yet

Two modules sound related but solve different problems:
- `sticker_detection.py` — classical CV, looks for suspicious edges/texture
  *within a single photo*. No reference image involved at all.
- `product_similarity.py` — perceptual hash + histogram nearest-neighbor
  against **your own scan history**. If you've never scanned this SKU
  before, there's nothing to compare against.

Your USP is specifically: "comparing current packaging with **trusted
reference images**" — a per-SKU ground-truth photo (supplied by the
manufacturer, or captured and verified by an authority/your team) that
every future scan of that SKU gets compared against. That registry and
that comparison do not exist. This is what you're building.

## Part A: Reference-image tampering detection

1. **A reference image registry.** A new table (add to `backend/db/schema.sql`
   — coordinate with whoever else touches that file, check git-style diffs
   before you overwrite it): `reference_images(product_id, image_path,
   uploaded_by, verified_by_authority BOOLEAN, mrp_at_capture, uploaded_at)`.
   A product can have one or more trusted reference images.

2. **Comparison logic.** For a new scan of a known `product_id`: fetch its
   reference image(s), align/compare the declaration region specifically
   (not the whole package — lighting, angle, and background will differ
   innocently; the printed declaration text/price is what must not
   silently differ). Concretely:
   - Reuse `product_similarity.py`'s `embed_image()` for a coarse
     "is this even the same product" check first (cheap, already built).
   - For the actual tamper check, OCR/extract the reference image's fields
     once (using Workstream 1's extraction) and store them alongside the
     reference. Compare the new scan's extracted MRP/net-quantity/etc.
     against the reference's stored values, not pixel-by-pixel — pixel
     diffing across different photos of the same box is unreliable; field-
     level comparison is what «Packaging Tampering Detection» actually
     needs to mean.
   - A genuine MRP increase between reference and current scan should be
     flagged distinctly from "current label doesn't match ANY known
     reference" (former = legitimate price update needing confirmation;
     latter = higher suspicion, could be a re-sticker).

3. **Never auto-fail.** Like every other AI signal in this project, a
   tampering flag raises `review_required=True` and produces an
   `ExtractedFact`/finding — it does not by itself set `overall_status =
   FAIL`. Only the deterministic rule engine's own legal findings do that.
   State this constraint back to me in your own words when you report
   progress, so I know it was actually understood, not just copy-pasted.

## Part B: FSSAI cross-verification

1. **Get real data or say clearly that you don't have it.** FSSAI publishes
   a public license search (FoSCoS) but there is no bulk public API handed
   to you here — you'll need to either scope this to a small manually-
   curated sample dataset of real FSSAI license numbers + registered
   product categories for your demo, or scrape/request access properly.
   **Do not fabricate FSSAI license numbers or product records** — for a
   government-facing compliance tool, presenting invented regulatory data
   as real would be a serious credibility (and honesty) failure if a judge
   checks. If you can't get real data in time, build the cross-check logic
   against a clearly-labeled `sample_fssai_data.json` and say so explicitly
   in your demo — same discipline as the "synthetic dataset" disclosure
   already used elsewhere in this project.

2. **What to actually cross-check**, once you have real or honestly-labeled
   sample data: FSSAI license number format/presence for food products,
   category consistency (does the declared common_name match what's
   registered under that license), and manufacturer name consistency.
   This is a new `ExtractedFact`/finding type, not a rule_engine.py rule —
   it's evidence-comparison, not legal-threshold evaluation, so it belongs
   alongside the tampering check as an advisory signal, same non-negotiable
   constraint as above: never auto-fail, always flag for review.

## What to test and report back

- A real before/after pair if you can get one (photograph the same product
  twice, ideally with something deliberately different the second time —
  a different sticker, a manually edited price on a printout — to confirm
  the field-level comparison actually catches it).
- At least 3 products run against your FSSAI sample/reference data, with
  output shown, and an explicit statement of whether the underlying FSSAI
  data is real or a disclosed sample.

## Files to upload to this Claude session

`backend/sticker_detection.py`, `backend/product_similarity.py`,
`backend/schema.py`, `backend/db/schema.sql`, `backend/db/persistence.py`,
`handoff/00_PROJECT_STATUS_AND_SPLIT.md`.
