# Project status — what's real, what isn't, and how the work is split

Read this before opening any of the 4 workstream briefs. It's the shared
ground truth all four Claude sessions must work from, so nobody duplicates
work or builds on top of a false assumption.

## What is actually built and verified (as of this handoff)

Verified means: I ran it, not just read it — against real product photos and
a real Postgres database, over real HTTP.

- **Core LMPC declaration engine**: `exemption.py` (Rule 3 scope, Rule 26
  small-pack exemption), `unit_price.py` (Rule 6(11), including the real
  per-gram-below-1kg/per-kg-at-or-above-1kg threshold switch), `rule_engine.py`
  (ties them together, produces PASS/FAIL/UNCERTAIN/EXEMPT with evidence
  references). Tested against real photos and edge cases — correct.
- **OCR + regex-based field classification** (`ocr_extraction.py`) — real
  Tesseract OCR, not a mock. Correctly extracts most fields on a clean photo;
  has known, disclosed weaknesses on a lower-quality photo (MRP/manufacturer
  mixup) and is architecturally a regex/heuristic classifier, not the
  "multimodal AI" your USP language describes (see Workstream 1).
- **Postgres persistence** (`db/persistence.py`, `db/schema.sql`) — 3 tables,
  real save/list/detail/review round-trips confirmed.
- **FastAPI backend** (`main.py`) — `/scan`, `/inspect`, `/inspections`,
  `/inspections/{id}`, `/inspections/{id}/review`, `/products/{id}/history`.
  All confirmed working over real HTTP.
- **Sticker/alteration heuristic** (`sticker_detection.py`) — classical CV,
  looks for suspicious regions *within a single photo*. Correctly flags for
  human review only, never fails a product by itself.
- **Scan-history similarity** (`product_similarity.py`) — perceptual hash +
  color histogram nearest-neighbor against your *own past scans*. Confirmed
  working (correctly matched a rescan at similarity 1.000, correctly flagged
  a simulated price change as "history flag, not violation").
- **VLM ambiguity checker** (`vlm_verifier.py`) — advisory-only wording check,
  fails closed, tested offline (needs a live `ANTHROPIC_API_KEY` to actually
  call the API — not yet tested live).
- A capture-calibration tool (`frontend/capture.html`) and a working demo
  dashboard (`frontend/dashboard.html`) — you said another team owns frontend,
  so these are starting points, not final UI.

## What is NOT built — confirmed by grep, not by memory

1. **No amendment/effective-date versioning.** `rules.json` has
   `effective_from`/`effective_to` fields on every rule, but
   `rule_engine.py` never reads them — `grep -c "effective_from" rule_engine.py`
   returns 0. Every rule is always treated as currently in force, regardless
   of which date you're inspecting for. Your "multi-versioned rule engine to
   adapt to amendments" does not exist yet. → **Workstream 2**.

2. **No multi-surface capture.** `schema.py` has a `SurfaceObservation` model
   and a `captures: List[SurfaceObservation]` field on `ProductInspection`,
   but nothing anywhere ever constructs one (`grep -rn "SurfaceObservation("`
   returns nothing outside its own definition). `/scan` takes exactly one
   `file: UploadFile`. "Upload multiple sides of a product" does not work
   today — one photo in, one photo's worth of evidence out. → **Workstream 1**.

3. **No trained object detector.** Field locations come from Tesseract's own
   text boxes plus regex classification, not a detection model that
   localizes the PDP, understands packaging geometry, or detects visual
   tampering patterns. See Workstream 1 for why training one from scratch is
   probably the wrong move for your team and what to do instead.

4. **No packaging tampering detection against a trusted reference.** What
   exists (`sticker_detection.py`, `product_similarity.py`) is not this
   USP: one looks for suspicious regions in isolation, the other compares
   against your own scan history. Your USP as stated — "comparing current
   packaging with trusted reference images" — needs a reference-image
   registry per SKU, which does not exist. → **Workstream 3**.

5. **No FSSAI cross-verification.** Zero FSSAI data, zero integration,
   zero cross-check logic anywhere in the codebase. → **Workstream 3**.

6. **No consumer-to-authority reporting.** No data model, no endpoint, no
   workflow. → **Workstream 4**.

7. **No PDF generation.** Explicitly deprioritized earlier in this project;
   folded into Workstream 4 now that it's back in scope.

## The 4-way split

| # | Workstream | Owns |
|---|---|---|
| 1 | Capture & Extraction | Multi-surface upload, the CV/detection question, upgrading OCR to real multimodal extraction |
| 2 | Legal Engine Versioning | Amendment-aware, effective-dated, multi-versioned rule engine |
| 3 | Tampering + FSSAI (USP 1 & 2) | Reference-image tampering detection, FSSAI cross-verification |
| 4 | Reporting + PDF (USP 3) | Consumer report capture/submission workflow, PDF report generation |

## Non-negotiable shared contract — every workstream must preserve this

All four sessions are editing the same codebase. To avoid four incompatible
versions of the same file:

- **`schema.py`'s `ProductInspection`/`ExtractedFact`/`SurfaceObservation`
  shapes are the interface.** Extend them (add fields) freely. Don't rename
  or remove existing fields without flagging it in your own handoff notes —
  other workstreams depend on the current shape.
- **`rules.json`'s existing rule_ids are load-bearing** — `rule_engine.py`
  and `exemption.py` look them up by exact string
  (`LMPC-2011-R3-SCOPE`, `LMPC-2011-R6-DECLARATIONS`, `LMPC-2011-R6-11-UNIT-PRICE`,
  `LMPC-2011-R7-2-FONT`, `LMPC-2011-R8-PLACEMENT`, `LMPC-2011-R26-SMALL-PACKS`).
  Don't rename these; add new rule_ids alongside them instead.
  the fields the RULES expect. `main.py`'s `_prepare_extractions()` is the
  one place that bridges vocabulary mismatches — if you add a new field
  name on either side, add the bridge there and say so in your handoff notes.
- **Run the actual code before reporting it done.** Every bug in this
  project so far was caught by execution, not by reading — a truncated file,
  a silent field-name mismatch, a regex that matched the wrong label. Import
  every module you touch, run it against a real photo or real data, and show
  the output, before calling a piece finished.
- **Don't claim a component works because it looks right.** State exactly
  what you tested and what you didn't, the way this document does above.
