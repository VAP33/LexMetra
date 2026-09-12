# Integration changelog — this pass

Executes `anti2.md` §1 and §2 (wiring half only). Everything below was changed,
tested, and verified against real dataset images before this zip was built.

## backend/main.py

- **Barcode/SKU identification wired in.** `barcode_decode.decode_across_images()`
  now runs on every uploaded image in both `/extract-preview` and `/scan`, via a
  new shared helper `_decode_barcodes()`. Product-ID resolution priority is now:
  decoded barcode/GTIN → `common_name` → `manufacturer_name` → an explicitly
  tagged placeholder. The placeholder is never presented as a real read again —
  every response now carries a `product_id_source` field
  (`barcode_scan` / `barcode_ocr_checked` / `common_name` / `manufacturer_name` /
  `unidentified_placeholder`) so callers can tell the difference.
- **Geometry detection wired in.** `geometry.detect_package_geometry()` and
  `detect_pdp_geometry()` now run on the first captured surface via a new
  shared helper `_detect_geometry()`, and the detected `GeometryType` is passed
  into `run_inspection(geometry=...)`, which previously always received the
  default `UNKNOWN`. **This does NOT calibrate `pdp_area_cm2`** — that still
  requires a real-world reference (coin/card in frame, known dimension, or
  depth), none of which this app captures yet. See `anti2.md` §2 for the two
  scoped options to close that gap; it is deliberately not attempted here.
- Both endpoints now return `"barcode": {...}` and `"geometry": {...}` blocks
  in their JSON response with the raw decode/detection evidence, for the
  frontend and for audit purposes.

## frontend/react-app/src

- `api-client.ts`: `ExtractPreviewResponse` type extended with
  `product_id_source`, `product_id_needs_confirmation`, `barcode`, `geometry`.
- `InspectionApp.tsx`: the product-ID input field is no longer auto-filled with
  a placeholder ID — only with a genuine barcode read or label-text-derived
  guess. The "Auto-suggested" badge now reads "Read from barcode" /
  "Barcode digits (please confirm)" / "Auto-suggested from label text" /
  "Not identified — type manually" depending on `product_id_source`, instead
  of one undifferentiated label for every case including the random fallback.

## Verification performed before this zip was built

- `python -m py_compile backend/main.py` — clean.
- `import main` with all real dependencies installed — clean, no import errors.
- Full backend suite: `pytest tests/` → **348 passed, 13 skipped** (skipped
  tests require a live Postgres instance, not available in this sandbox), 0
  failures, 0 new skips introduced by this change.
- `barcode_decode.decode_symbols()` run directly against a real photo from
  `images dataset/` (a Sabudana Chiwda pack with a visible barcode) — correctly
  returned `LOCALISED_NOT_DECODED` with actionable guidance rather than
  crashing or fabricating a result. This is the module's own honest-negative
  behavior working as designed, not a wiring failure.
- `geometry.detect_package_geometry()` run against the same photo — returned a
  real bounding polygon and shape confidence.
- `run_inspection(geometry=GeometryType.UNKNOWN)` called directly to confirm
  the new keyword argument is accepted end to end.
- `npx tsc --noEmit` on the frontend — no new type errors (one pre-existing,
  unrelated warning about a CSS side-effect import in `main.tsx`).

## What this pass deliberately did NOT do

- Did not build a reference-object (coin/card) detector or a package-dimension
  lookup table, so `pdp_area_cm2` — and therefore Rule 7(2) font-height — is
  still gated on that missing calibration input. This is scoped, separate work;
  see `anti2.md` §2.
- Did not swap the VLM verifier's default provider to Gemini. See `anti2.md`
  §7 for the ~15-line change and where to get a free key; not applied here
  because it needs a `GEMINI_API_KEY` this environment doesn't have.
- Did not touch `region_detection.py`, OCR digit-repair, or add a YOLO/
  trained layout model. Per `anti2.md` §9, that's real, separate scoped work,
  not a wiring fix.
- Did not archive/delete the `CLAUDE 2` vision-specialist folder from the
  *original* repo — it's simply excluded from this cleaned zip. If you want it
  gone from your working copy too, delete it there directly; nothing in the
  active tree referenced it (confirmed by grep before this zip was built).

## What was removed from this zip vs. the original upload

- `CLAUDE 1/2/4/5/` — superseded source-session folders; canonical `backend/`
  and `frontend/` had already diverged from all of them by hundreds to
  thousands of lines. Nothing in the active tree imports from them.
- `.git/`, `.pytest_cache/`, `__pycache__/`, `*.pyc`, `.vscode/` — caches/VCS,
  regenerate or aren't needed for a clean handoff.
- `frontend/react-app/node_modules/` (135 MB) — regenerate with `npm install`.
- `backend/db/data_local/` (65 MB) — a real, already-initialized PostgreSQL 18
  data directory tied to the machine it was created on. Not portable as a raw
  file copy across machines/OS. Follow `SETUP.md` to create a fresh one, or
  restore your own `data_local` alongside this tree if you're moving between
  your own machines.
- Contents of `uploads/`, `reports/`, `backend/uploads/`, `backend/reports/` —
  generated evidence photos and PDF reports from prior runs. Folders kept
  (with `.gitkeep`) so the app has somewhere to write; the files themselves
  aren't source.
- `demo_inspection_report.pdf` at repo root — a generated artifact, not source.
