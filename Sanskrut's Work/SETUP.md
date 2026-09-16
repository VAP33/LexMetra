# Running the full stack locally

## 1. Postgres

```bash
sudo apt-get install postgresql
sudo service postgresql start
sudo -u postgres psql -c "CREATE USER lmpc_app WITH PASSWORD 'lmpc_dev_pw';"
sudo -u postgres psql -c "CREATE DATABASE lmpc OWNER lmpc_app;"
```

Set `DATABASE_URL` if you want a different connection (default in `db/persistence.py`
is `postgresql://lmpc_app:lmpc_dev_pw@localhost:5432/lmpc` — change the password
before this goes anywhere near a real deployment, this is a dev default only).

## 2. Backend

```bash
cd backend
pip install -r requirements.txt
# Tesseract OCR engine (not a Python package):
sudo apt-get install tesseract-ocr
uvicorn main:app --reload --port 8000
```

The schema (`db/schema.sql`) is created automatically on startup — no manual
migration step needed for this prototype.

## 3. Frontend

`frontend/dashboard.html` is a static file with no build step — just open it in
a browser. It talks to `http://localhost:8000` (hardcoded at the top of the
`<script>` block — change `API` there if your backend runs elsewhere). Because
it's a plain `file://` page making cross-origin requests, the backend has CORS
enabled for all origins (`main.py`'s `CORSMiddleware`) — tighten that before any
real deployment.

`frontend/capture.html` is the separate calibrated-capture tool (reference-card
measurement for numeral height / PDP area) — also a standalone static file.

## What each dashboard tab does

- **Scan** — upload a photo, fill in the few fields OCR can't reliably read
  (sale type, category, quantity as a fallback, MRP), get a verdict with the
  full fact table and the raw OCR text next to each field so you can sanity-check
  extraction before trusting a FAIL.
- **Inspections** — every scan ever run, from Postgres, clickable for full detail.
- **Review Queue** — filters to inspections where at least one fact has
  `review_required = true` (low OCR confidence, sticker suspicion, exemption
  edge cases) — this is the human-in-the-loop screen your plan's section 7
  calls for. Marking an item reviewed writes a note back to Postgres.

## Known limitations to be upfront about in your demo

- OCR field extraction (`ocr_extraction.py`) is regex/heuristic classification
  on top of Tesseract, not a trained layout model — it can mis-pair nearby
  numeric fields in cramped label columns (confirmed: MRP and unit-sale-price
  got swapped on a real box during testing). The dashboard always shows the raw
  extracted text next to the verdict specifically so a human catches this before
  it's trusted.
- Sticker detection is a classical-CV heuristic (no trained model, no training
  data available) — expect false positives on ordinary photo edges (hands,
  frame borders), which is why it can only ever push a result to UNCERTAIN,
  never FAIL, by design in `rule_engine.py`.
- The Postgres schema has no auth/users table yet — every endpoint is open.
  Fine for a hackathon demo on localhost, not for anything beyond that.
