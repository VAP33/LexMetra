# Legal Metrology Compliance Platform — Starter Build

This is now a genuinely full-stack, running prototype — OCR, rule engine, sticker
detection, product similarity, Postgres persistence, and a working dashboard, all
tested end-to-end against your real product photos. It is still not "finished" —
see the honest gaps list near the bottom — but every piece listed as "working"
below has actually been run, not just written. **See `SETUP.md` for how to run
the whole stack.**

## What's real and working here

- **`rules/rules.json`** — Legal Metrology Act 2009 + LMPC Rules 2011 encoded as
  versioned, dated data records (Rules 3, 6, 7, 8, 12, 26, 27, 32, Second Schedule),
  matching the schema your plan specifies in section 2.2. **Every rule is flagged
  `verification_status: "needs_official_verification"`** — the numeral-height bands
  and a few thresholds were pulled from legal commentary, not the primary gazette
  text. Your Legal/Domain Lead must verify each one against egazette.gov.in before
  your demo and flip the flag to `"verified"`. Rule 32 is a deliberate placeholder —
  it's commodity-specific and needs populating for your actual demo categories.
- **`backend/exemption.py`** — exemption classification (Rule 3), runs before any
  compliance check, exactly as your plan insists on in section 2.3.
- **`backend/unit_price.py`** — deterministic unit-sale-price calculator (Rule 12).
  Count-based commodities (capsules/tablets/pieces) price per single unit, confirmed
  against a real label (see "Tested against real products" below); weight/volume
  price per kg/litre. Verifies declared values numerically against computed ones
  (with unit conversion, 2% tolerance) when structured OCR output is available —
  not just "is some text present."
- **`backend/rule_engine.py`** — ties exemption + mandatory fields + numeral height
  + unit price + sticker suspicion into one PASS/FAIL/UNCERTAIN/EXEMPT verdict.
- **`backend/schema.py`** — the shared `ExtractedFact` / `ProductInspection` JSON
  contract from your plan's section 5.2. Lock this early; every module (CV, backend,
  frontend) should import from here rather than redefining field names.
- **`backend/sticker_detection.py`** — classical-CV (OpenCV, no training data)
  heuristic for possible stickers/alterations: edge-discontinuity + print-sharpness
  mismatch. Advisory only — it can only push a verdict to UNCERTAIN for human
  review, never to FAIL by itself. See the file's docstring for the honest accuracy
  discussion and the upgrade path once you have paired original/altered photos.
- **`backend/vlm_verifier.py`** — LLM-based check for ambiguous *wording* only
  (e.g. a non-standard date format). Contractually cannot decide PASS/FAIL, only
  attach a plain-language note. Needs your own `ANTHROPIC_API_KEY` to actually call
  the API; the JSON-parsing plumbing is tested offline via `verify_ambiguous_field_mocked`.
- **`backend/product_similarity.py`** — perceptual-hash + color-histogram
  nearest-neighbor matching for "have we seen this exact package before, and did
  its price/label change." See the file's docstring for why this uses plain
  embedding search rather than a full RAG stack — short version: RAG trades a
  guaranteed-correct rule citation for a probabilistic one, which is the wrong
  trade for a legal-compliance tool, and the "retrieval" problem here is really
  just image nearest-neighbor, which doesn't need RAG's machinery.
- **`backend/main.py`** — FastAPI wrapper exposing `/inspect` (text fields →
  verdict) and `/analyze-image` (photo → sticker suspicion + history match).
  Both tested end-to-end via FastAPI's TestClient, including against your real
  uploaded photos.
- **`frontend/capture.html`** — calibrated capture tool: overlay guide + reference
  card (ID-1, 85.60mm) for real millimeter measurements, not guesses.
- **`frontend/dashboard.html`** — working dashboard: Scan tab (photo → full
  pipeline → verdict, with raw OCR text shown next to every field so mis-extractions
  are visible, not hidden), Inspections tab (Postgres-backed history), Review Queue
  tab (filters to facts with `review_required=true`, lets a human mark reviewed
  with a note). No build step — open the file directly, talks to the API over CORS.
- **`backend/ocr_extraction.py`** — REAL OCR (Tesseract, pretrained) + rule-based
  field classification, tested against your uploaded photos. Correctly extracts
  manufacturer/marketer paragraphs, dates, quantities. Has a known real bug:
  in cramped multi-value label columns it can mis-pair adjacent numeric fields
  (confirmed: swapped MRP and unit-sale-price on a real box) — the dashboard
  always shows raw extracted text next to the verdict specifically so this is
  catchable by a human, not hidden.
- **`backend/db/`** (`schema.sql` + `persistence.py`) — real Postgres, not a
  mock. 3 tables (products, inspections, inspection_facts). Tested end-to-end:
  scan → save → list → detail → mark-reviewed → product-history, all confirmed
  over actual SQL round-trips.
- **`backend/main.py`** — FastAPI wrapper. `/scan` runs the FULL pipeline (OCR →
  classify → rule engine → sticker check → similarity check → Postgres) in one
  call; `/inspections`, `/inspections/{id}`, `/inspections/{id}/review`,
  `/products/{id}/history` back the dashboard. All tested over real HTTP
  (not just FastAPI's TestClient) with `uvicorn` actually running.
- **`dataset/generate_dataset.py`** + **`dataset/images/`** (50 files) +
  **`dataset/annotations/annotations.json`** — synthetic mockups for pipeline
  testing. **Not real product photos** — see the dataset section below.

### Tested against real products (not just synthetic data)

Two real products you photographed were run through the full pipeline:
- **Traya Hair Actives (30ml)** — back panel only → correctly FAIL, because
  `common_name` wasn't visible in that shot (a capture-completeness issue, not
  necessarily a real violation — front panel needed). Unit price ₹26.67/ml verified
  as numerically equal to the computed ₹26,666.67/litre.
- **Traya Hair Vitamin (30 capsules)** — front + back both available → correctly
  **PASS**, all 6 mandatory fields present, unit price ₹15.67/capsule verified
  exactly against the computed value. This is the pipeline's first fully-compliant
  real-product result. Running it through `/analyze-image` also correctly found 0
  matches in an empty history index, then matched itself at similarity 1.000 on a
  simulated rescan, and correctly flagged a simulated ₹470→₹499 price change as
  "price change, not an error" rather than a mismatch.

## What is NOT in here yet (and can't be faked)

- **Trained OCR/CV field detector** — `ocr_extraction.py` is real and working
  (Tesseract + regex classification), but it's not the trained YOLO-style
  detector your plan describes; that needs training data and GPU time your team
  will have to invest. The known MRP/USP column mis-pairing bug is the clearest
  symptom of this gap.
- **Real product dataset at scale** — several hundred to ~1,500 real Indian SKU
  photos, human-verified. Two real products are tested end-to-end (above);
  that's proof the pipeline works on real data, not a substitute for the real
  dataset your Data Lead still needs to build.
- **Trained sticker/alteration classifier** — `sticker_detection.py` is a running
  classical-CV baseline, not a trained model (no GPU/training data available here).
- **Auth, roles** — every endpoint is open. Fine for localhost demo only.
- **PDF report generation, Docker** — explicitly out of scope per your last message.
- **Frontend polish** — the dashboard is functional, not designed. No mobile
  layout, no bounding-box overlays on the photo, no bulk actions.

## About the "50 labelled images" dataset

`dataset/annotations/annotations.json` describes 50 **synthetically generated**
package mockups: 25 products, each with one compliant version and one paired
violation version. Split by **product**, not image — no leakage across train/val/test,
per your plan's section 3.4. Useful for pipeline integration testing and demoing the
paired-violation concept; **not** a substitute for real photography. Every entry is
tagged `"synthetic": true`. Be upfront with judges about which is which — your two
real product photos, tested above, are worth more to your credibility than all 50
synthetic ones combined.

## Try it now

See **`SETUP.md`** for full instructions. Quick version:

```bash
cd backend && pip install -r requirements.txt && uvicorn main:app --reload --port 8000
# open frontend/dashboard.html directly in a browser
```

```bash
cd dataset
python3 generate_dataset.py   # regenerate the 50-image synthetic set
```

## Suggested next steps, in priority order

1. Legal Lead: verify every threshold in `rules.json` against the primary source,
   and populate Rule 32 for your actual demo commodity categories.
2. Data Lead: start real photo collection this week — even 30-40 real SKUs beats
   any amount of synthetic data for your actual demo credibility.
3. CV/ML Lead: the biggest concrete bug to fix is `ocr_extraction.py`'s column
   mis-pairing (MRP vs unit-sale-price) — either improve the layout heuristic
   (explicit label/value column clustering by x-position) or train a real
   layout model once you have labeled real photos. If you get paired
   original/altered photos, retrain `sticker_detection.py` into a real
   classifier — the function signature can stay the same.
4. Backend Lead: add auth/roles around the now-working Postgres-backed endpoints.
5. Frontend Lead: the dashboard is functional — visual design, mobile layout,
   and drawing the `bbox` field (already returned per fact) over the photo are
   the natural next additions.
