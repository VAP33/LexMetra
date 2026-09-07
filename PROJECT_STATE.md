
# PROJECT_STATE.md
## SIH 2026 — PS 26034 — Legal Metrology (Packaged Commodities) Compliance Platform
### Complete Technical Audit — Post Session 1 — September 2026

> **Audit policy:** This document was produced by reading every file in the repository exactly as it exists after Session 1 hardening work.
> No files were modified, created, deleted, or refactored during this audit pass.
> All judgements are based solely on observed code and the `IMPLEMENTATION_STATUS.md` execution log.

> ### ⚠ PARTLY SUPERSEDED BY SESSION 3 — read this first
> This file is a **point-in-time snapshot taken after Session 1**, and it is kept
> unmodified because that is what makes it useful. It is no longer current in
> three respects. See `IMPLEMENTATION_STATUS.md` § "Session 3" for the detail.
>
> 1. **The "Working" column below overstates what has been executed.** Everything
>    in §1.1 relating to FastAPI, JWT auth, RBAC, Postgres and the audit log was
>    verified in Session 1's environment. In the current development container
>    `fastapi`, `psycopg2`, `jose`, `passlib` and `pyzbar` are absent and cannot
>    be installed, so those layers have **not been executed since**, and
>    `test_auth` is a collection error.
> 2. **Two real defects have been fixed since this audit.** OCR fusion could
>    report two contradictory numbers (`100 g` vs `700 g`) as mutually
>    corroborating *with a confidence bonus*; and the rule engine treated any
>    unrecognised `rules.json` condition as an unconditionally mandatory
>    requirement, which was one edit away from producing a false FAIL.
> 3. **Test counts here are stale.** The suite is now 171 passed / 1 collection
>    error / 10 skipped, and it currently runs under a bundled pytest shim plus a
>    strict pydantic stand-in rather than the real libraries.
>
> Where this document and the repository disagree, trust the repository.

---

## 1. EXECUTIVE STATUS

### 1.1 What Currently Works

| Component | Status |
|---|---|
| FastAPI server with JWT authentication on all endpoints | Working |
| Bootstrap first-user admin creation (`POST /auth/register`) | Working |
| Admin-only user creation (`POST /auth/register/admin`) | Working |
| Login / JWT token issuance (`POST /auth/login`) | Working |
| Role hierarchy: `inspector` < `reviewer` < `admin` | Working |
| RBAC `Depends()` guards on every write + read endpoint | Working |
| Audit log (append-only, admin-visible via `GET /audit-log`) | Working |
| Centralized config via `config.py` + `python-dotenv` + `.env.example` | Working |
| CORS origins read from env (`ALLOWED_ORIGINS`), no wildcard | Working |
| JWT secret enforcement (`LMPC_DEV_MODE=false` refuses insecure default) | Working |
| Full-pipeline `/scan` endpoint (OCR → rule engine → Postgres → evidence file saved) | Working |
| `/inspect` endpoint with field-name bridge and applicability inference | Working |
| `/analyze-image` endpoint (sticker + similarity, no legal verdict) | Working |
| Multi-surface session API: `POST /sessions`, `POST /sessions/{id}/captures`, `GET /sessions/{id}`, `POST /sessions/{id}/finalize` | Working — tested end-to-end |
| Per-capture OCR + image quality assessment (`image_quality.py`) | Working |
| Heuristic PDP bounding-box estimate from OCR text clusters | Working (informational only) |
| Session evidence merge (highest-confidence-wins field accumulation) | Working |
| Evidence-sufficient coverage computation using same field list as legal engine | Working (JSONB double-decode bug fixed) |
| Guided capture messages per missing field (`capture_session.guidance_messages`) | Working |
| Rule 3 scope/exemption engine (`exemption.py`) | Working |
| Rule 6 mandatory declarations (retail path) with conditional fields (`best_before_use_by`, `country_of_origin`) | Working |
| Rule 6(11) unit-sale-price deterministic calculator | Working |
| Rule 7(2) font-height check (returns UNCERTAIN without calibrated measurement) | Working |
| Rule 8(1) placement check (shallow — PASS if PDP bbox present) | Working |
| Rule 24 wholesale declarations evaluator (new) | Working — tested |
| `best_before_applicable` inferred from perishable category allowlist | Working (was always `False` before) |
| `is_imported` inferred from positive OCR country-of-origin evidence | Working (was always `False` before) |
| Field-name bridge (`bridge_classified_fields`) centralized in `capture_session.py` | Working — applied to both `/scan`, `/inspect`, and session finalize |
| Tesseract OCR pipeline (multi-PSM, multi-variant preprocessing, deduplication) | Working |
| Sticker / alteration heuristic (classical CV, advisory only) | Working |
| Product similarity (pHash + HSV histogram, flat JSON index) | Working |
| VLM verifier connected to pipeline (gated behind `VLM_VERIFICATION_ENABLED=true` + API key) | Working (advisory only, graceful no-op if disabled/unavailable) |
| PDF report generation via ReportLab (`GET /inspections/{id}/report.pdf`) | Working — verified produces valid PDF |
| Evidence image retention (UUID-prefixed on-disk storage, path in DB) | Working |
| PostgreSQL persistence (5 core tables + `audit_log` + session tables) | Working |
| Idempotent schema auto-initialization on startup | Working |
| JSONB double-decode bug fix (both evidence_json and session OCR fields) | Working |
| Review endpoint requires `reviewer` role; records `reviewed_by` | Working |
| Test suite — 34 tests, 0 skipped | Working (verified live per execution log) |
| `Dockerfile` + `docker-compose.yml` + `.dockerignore` | Present — **not yet verified with actual Docker** |
| `backend/.env.example` | Present |

### 1.2 What Partially Works

| Component | Gap |
|---|---|
| Rule 7(2) font-height | Evaluator exists but always returns `UNCERTAIN`; no automatic pixel-to-mm conversion. `capture.html` calibration tool is disconnected from `/scan`. |
| Rule 8(1) placement | Returns `PASS` trivially when any PDP bbox is supplied; no per-declaration placement or clearance distance validation. |
| Product similarity index | Flat JSON (`product_index.json`, runtime-generated, not in git). Correct for demo; will not scale past ~500 entries. |
| Sticker detection | Heuristic only (no trained model). Non-negligible false-positive rate on ordinary package edges. |
| VLM verifier | Wired into pipeline but requires `ANTHROPIC_API_KEY` + `VLM_VERIFICATION_ENABLED=true`. Never tested live against Anthropic API in this session. |
| Docker deployment | `Dockerfile` and `docker-compose.yml` are written and mirror the tested manual setup, but `docker compose up --build` has **not been executed** (no Docker in the build environment). |
| `capture.html` calibration tool | Generates payload correctly but output must be manually copy-pasted into `/inspect`; not connected to `/scan` or the session API. |
| Session test coverage | Multi-surface tests use "second photo of same product" rather than genuine disjoint front/back evidence — a test-data gap, not a code gap. |

### 1.3 What Is Broken

| Issue | Location | Severity |
|---|---|---|
| Docker build unverified | `backend/Dockerfile`, `docker-compose.yml` | P1 — must be tested in a Docker environment before demo |
| `product_index.json` not in git — empty on fresh clone | `backend/product_index.json` | P2 — similarity index shows zero matches on first install |
| `backend/db/__init__.py` is empty | `backend/db/__init__.py` | Low — package works via `import db.persistence as db` but package is incomplete |
| `CLAUDE MASTERPROMPT.txt` in repo root (non-source artifact) | `CLAUDE MASTERPROMPT.txt` | Low — should be `.gitignore`d or moved to a `docs/` directory |

### 1.4 What Is Only Mocked / Demo Functionality

| Feature | Reality |
|---|---|
| Sticker / alteration detection | Classical CV heuristic, no trained model. Advisory only — can only push to `UNCERTAIN`, never `FAIL`. |
| Product similarity / visual identity | pHash + histogram, not a trained deep embedding. Visual candidate retrieval, not product identity. |
| VLM semantic verification | Wired but never tested against live Anthropic API. Advisory only, never changes PASS/FAIL. |
| MRP price-change detection | Requires index to have accumulated prior scans; empty on fresh install. |
| Synthetic dataset (50 images) | Programmatically drawn Pillow images. Explicitly tagged `synthetic:true`. Not real product photos. |
| Font-height compliance | Always `UNCERTAIN`; calibrated measurement workflow is a separate manual tool (`capture.html`). |
| PDP bounding-box estimate | Heuristic from OCR text cluster, explicitly labelled informational — never fed into font-height legal check. |

### 1.5 What Is Missing

- Mobile application (Android / React Native / Kotlin — zero code)
- ARCore / Depth API / assisted scanning (zero code)
- Offline capture and synchronization (zero code)
- Guided-camera client consuming the session API (backend exists; no frontend client)
- FSSAI cross-verification (zero code)
- Trained OCR layout / field-detection model
- Trained sticker / alteration classifier
- Real product photo dataset (two real photos tested during development, none committed)
- Rule 4 (multi-pack) evaluator
- Rule 5 / Second Schedule standard-pack evaluator
- Rule 25 (export repack) evaluator
- Rule 26(b) fast-food exemption evaluator
- Rule 26(c) drug formulation exemption evaluator
- Rule 27 (registration) evaluator
- Rule 31 (advertisement) evaluator
- Rule 7(2) font-width ratio check
- 10–20 g/ml partial relaxation declaration path
- PaddleOCR integration (commented out in requirements.txt)
- FAISS / vector DB for product similarity at scale
- React / TypeScript web dashboard (current dashboard is legacy static HTML)
- PDF report — editable export (CSV / Excel)
- Frontend bounding-box overlays on uploaded image
- Mobile-friendly dashboard layout
- Barcode / QR scanning
- Multilingual OCR (Hindi / Indian scripts)
- Connection pooling (new connection per request)
- Production secrets rotation / vault integration

### 1.6 Overall Readiness Percentage

**55% — Alpha / Working Prototype**

Justification (up from 35% pre-Session-1):
- Authentication, RBAC, audit trail, and secret management fully implemented (+10%)
- PDF report generation implemented (+5%)
- Rule 24 (wholesale) evaluator implemented (+3%)
- Multi-surface session architecture implemented and tested end-to-end (+7%)
- Evidence image retention implemented (+3%)
- VLM connected to pipeline (advisory) (+2%)
- `best_before_applicable` / `is_imported` inference fixed (+2%)
- Field-name bridge centralized and applied to `/inspect` (+1%)
- Test suite: 34 tests, 0 skipped (+5%)
- Docker deployment files present (+2%)
- Major P0 items from previous audit resolved (pytesseract in requirements, hardcoded DB password moved to config) (+5%)

Remaining gap (45%): no mobile app, no trained models, no real dataset, 7 rule evaluators missing, Docker unverified, no React frontend, no offline/sync, no FAISS, no FSSAI integration.

---

## 2. COMPLETE REPOSITORY TREE

```
SIH 2026/
├── .dockerignore                  CONFIG — Docker build exclusions
├── .git/                          Git version control
├── .gitignore                     CONFIG — standard Python + secrets gitignore
├── CLAUDE MASTERPROMPT.txt        NON-SOURCE — AI architect prompt (should be removed/gitignored)
├── docker-compose.yml             CONFIG — backend + Postgres 16 deployment
├── ENGINE_UPGRADE_NOTES.md        DOCS — upgrade log from initial hardening pass
├── IMPLEMENTATION_STATUS.md       DOCS — Session 1 execution log (what was done, verified, known gaps)
├── PROJECT_MANIFEST.json          GENERATED AUDIT — machine-readable manifest (this audit)
├── PROJECT_STATE.md               GENERATED AUDIT — this document
├── README.md                      DOCS — project overview, working features, honest gap list
├── SETUP.md                       DOCS — local setup instructions
│
├── backend/
│   ├── auth.py                    SOURCE — bcrypt + JWT + RBAC (inspector/reviewer/admin)
│   ├── capture_session.py         SOURCE — multi-surface evidence merge, coverage compute, guidance
│   ├── config.py                  SOURCE — centralized env-var config (DATABASE_URL, JWT, CORS, paths)
│   ├── image_quality.py           SOURCE — classical CV image quality assessment + PDP bbox estimate
│   ├── main.py                    SOURCE — FastAPI entrypoint: auth, scan, inspect, sessions, reports
│   ├── ocr_extraction.py          SOURCE — Tesseract OCR + regex field classifier
│   ├── report.py                  SOURCE — ReportLab PDF report generator
│   ├── rule_engine.py             SOURCE — deterministic legal compliance evaluator
│   ├── exemption.py               SOURCE — Rule 3 scope/exemption classifier
│   ├── schema.py                  SOURCE — shared Pydantic contract (all modules)
│   ├── sticker_detection.py       SOURCE — classical CV sticker/alteration heuristic
│   ├── product_similarity.py      SOURCE — pHash + HSV histogram similarity index
│   ├── unit_price.py              SOURCE — Rule 6(11) unit-sale-price Decimal calculator
│   ├── vlm_verifier.py            SOURCE — Anthropic Claude ambiguity checker (wired, gated)
│   ├── requirements.txt           CONFIG — Python dependencies (now complete including pytesseract)
│   ├── Dockerfile                 CONFIG — python:3.12-slim + tesseract-ocr apt install
│   ├── .env.example               CONFIG — template for local .env file
│   ├── product_index.json         RUNTIME GENERATED — flat JSON similarity index (not in git)
│   ├── uploads/                   RUNTIME GENERATED — uploaded evidence images (gitignored)
│   ├── reports/                   RUNTIME GENERATED — generated PDF reports (gitignored)
│   ├── db/
│   │   ├── __init__.py            SOURCE — empty package marker
│   │   ├── schema.sql             SOURCE — PostgreSQL DDL (7 tables + indexes + constraints)
│   │   └── persistence.py        SOURCE — psycopg2 CRUD, user/auth, audit, session functions
│   └── tests/
│       ├── conftest.py            TEST — pytest fixtures (db_ready, api_client, tokens)
│       ├── test_api_integration.py TEST — live FastAPI TestClient + real Postgres
│       ├── test_auth.py           TEST — unit tests (bcrypt, JWT, role hierarchy)
│       ├── test_capture_session.py TEST — unit tests (merge, coverage, guidance)
│       ├── test_exemption.py      TEST — unit tests (Rule 3, Rule 26a exemptions)
│       └── test_rule_engine.py    TEST — unit tests (Rule 6, Rule 24, UNCERTAIN invariant)
│
├── frontend/
│   ├── dashboard.html             SOURCE — legacy 3-tab static SPA (Scan / Inspections / Review Queue)
│   └── capture.html               SOURCE — calibrated card-measurement tool (manual output)
│
├── rules/
│   └── rules.json                 SOURCE — 19 versioned LMPC Rules 2011 records
│
├── dataset/
│   ├── generate_dataset.py        SOURCE — synthetic dataset generator (Pillow-based)
│   ├── images/                    GENERATED ASSETS — 50 synthetic PNG images
│   └── annotations/
│       └── annotations.json       GENERATED — image metadata, splits, expected status
│
└── sample data/
    ├── IMG-20260906-WA0018.jpg     ASSET — real product photo (Traya, WhatsApp)
    ├── IMG20260906173316.jpg       ASSET — real product photo
    ├── VID20260906171516.mp4       ASSET — real product video
    ├── VID20260906171600.mp4       ASSET — real product video
    ├── ... (13 more .mp4 files)
    └── PRODUCTS/
        └── Pickle/
            ├── image (2).png      ASSET — real pickle product photo
            ├── image (3).png      ASSET — real pickle product photo
            └── image (4).png      ASSET — real pickle product photo
```

**File classification summary:**
- Source files: 22 (backend Python + HTML + SQL + JSON rules)
- Test files: 6
- Configuration files: 7 (`.gitignore`, `.dockerignore`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `config.py`, `.env.example`)
- Documentation: 5 (README, SETUP, ENGINE_UPGRADE_NOTES, IMPLEMENTATION_STATUS, CLAUDE MASTERPROMPT.txt)
- Generated / runtime: `product_index.json`, `uploads/`, `reports/`, `__pycache__/`, audit doc files
- Real sample assets: 2 JPG photos, 13 MP4 videos, 3 PNG pickle product photos — **in `sample data/` but not wired into pipeline**

---

## 3. BACKEND ARCHITECTURE

### 3.1 `backend/config.py` *(new)*

**Purpose:** Centralized environment-variable configuration. Loaded by all backend modules via `import config`. Eliminates hardcoded credentials from source code.

**Key values:**
- `DATABASE_URL` — from env or `.env`; fallback `postgresql://lmpc_app:lmpc_dev_pw@localhost:5432/lmpc` (dev-only)
- `JWT_SECRET_KEY` — from env; refuses startup with empty secret when `LMPC_DEV_MODE=false`
- `JWT_ALGORITHM` / `JWT_EXPIRE_MINUTES`
- `ALLOWED_ORIGINS` — comma-separated, replaces former `["*"]`
- `UPLOAD_DIR` / `REPORT_DIR` — created on import if absent
- `ANTHROPIC_API_KEY` / `VLM_VERIFICATION_ENABLED`

**Dependencies:** `python-dotenv`, `os`, `pathlib`

**Current limitations:**
- Hardcoded dev fallback for `DATABASE_URL` still exists; not a security risk as long as `LMPC_DEV_MODE=false` is enforced for production, but the fallback should ideally be removed entirely.
- `DEV_MODE = _env_bool("LMPC_DEV_MODE", True)` defaults to `True` — this means a fresh install without any `.env` file will run in insecure dev mode without warning.

---

### 3.2 `backend/auth.py` *(new)*

**Purpose:** bcrypt password hashing, JWT issuance/verification, and FastAPI RBAC dependencies.

**Roles:** `inspector` (level 0) < `reviewer` (level 1) < `admin` (level 2)

**Public symbols:**
- `hash_password(password) → str`
- `verify_password(plain, hashed) → bool`
- `create_access_token(username, role) → str` (HS256 JWT)
- `decode_access_token(token) → TokenData`
- `authenticate_user(username, password) → Optional[CurrentUser]`
- `get_current_user(token) → CurrentUser` — FastAPI Depends
- `require_role(min_role)` → FastAPI Depends factory
- `require_inspector`, `require_reviewer`, `require_admin` — pre-built Depends

**Dependencies:** `python-jose[cryptography]`, `passlib[bcrypt]`, `bcrypt`, `config`, `db.persistence`

**Current limitations:**
- No token refresh endpoint
- No token revocation / blacklist
- Single device per user (no device tracking)
- `auto_error=False` on `OAuth2PasswordBearer` means a missing token returns `None` rather than 401 until `get_current_user` raises — correct behavior but worth noting

---

### 3.3 `backend/main.py` *(heavily modified)*

**Purpose:** FastAPI HTTP entrypoint. All endpoints now require authentication.

**New endpoints added:**
- `POST /auth/register` — bootstrap first admin (unauthenticated, once per DB)
- `POST /auth/register/admin` — admin-only subsequent registrations
- `POST /auth/login` — OAuth2 password form, returns JWT
- `GET /auth/me` — current user info
- `GET /audit-log` — admin-only, last N audit events
- `POST /sessions` — create multi-surface inspection session
- `POST /sessions/{id}/captures` — add one surface photo to session
- `GET /sessions/{id}` — current session status + cumulative evidence
- `POST /sessions/{id}/finalize` — run legal engine on union of all captures
- `GET /inspections/{id}/report.pdf` — download ReportLab PDF report

**Authentication added to:** all existing `/scan`, `/inspect`, `/analyze-image`, `/inspections*`, `/products/*/history` endpoints.

**Key internal changes:**
- CORS now uses `config.ALLOWED_ORIGINS` (not `["*"]`)
- `_prepare_extractions()` now calls `capture_session.bridge_classified_fields()` — single canonical bridge location
- `_infer_applicability_context()` infers `best_before_applicable` (perishable category list) and `is_imported` (positive OCR country-of-origin or explicit flag)
- `_apply_vlm_verification()` calls VLM on `UNCERTAIN` facts; gated behind `VLM_VERIFICATION_ENABLED`; graceful no-op on any failure
- Evidence images written to `config.UPLOAD_DIR` under UUID-prefixed filename
- `db.set_inspection_attribution()` records `created_by` and `image_path`
- `db.record_audit_event()` called at every significant action

**Current limitations:**
- `/auth/register` bootstrap logic has a subtle bug: `role = req.role if db.any_user_exists() else "admin"` — because `any_user_exists()` is checked BEFORE insertion, the first call always gets `"admin"` regardless of the requested role. This is correct behavior (first user becomes admin) but the ternary is inverted from how it reads — confirmed correct in practice but confusing to read.
- No token refresh endpoint
- Session `GET /sessions/{id}` recomputes accumulated fields by re-reading all captures from DB on every call — O(n) in capture count; fine for MVP

---

### 3.4 `backend/capture_session.py` *(new)*

**Purpose:** Multi-surface evidence orchestration. Merges OCR fields across captures, computes coverage, generates guidance.

**Public functions:**
- `bridge_classified_fields(classified) → Dict[str, dict]` — single canonical OCR→rule vocabulary bridge
- `merge_classified_fields(accumulated, new_fields) → Dict[str, dict]` — highest-confidence-wins merge
- `compute_coverage(sale_type, context, merged_fields) → Tuple[float, List[str]]` — uses `required_declaration_fields()` from rule engine
- `guidance_messages(image_quality, coverage, missing_fields) → List[str]`
- `build_surface_observation(...)` → `SurfaceObservation`
- `parse_surface_type(value) → SurfaceType`

**Field-name bridge aliases (centralized here):**
- `manufacturer_name` / `packer_name` / `importer_name` → `manufacturer_name_address`
- `expiry_date` → `best_before_use_by`
- `net_quantity` → `wholesale_count_or_net_quantity` (for wholesale sessions)

**Key architecture invariant enforced:** coverage threshold `EVIDENCE_SUFFICIENT_COVERAGE = 0.70` is the same threshold used by `rule_engine._evidence_sufficient_for_missing_field()`.

**Current limitations:**
- `compute_coverage` calls `load_rules()` on every invocation (reads `rules.json` from disk). Fine for a session with a handful of captures; not efficient for high-frequency polling.
- Surface guidance caps at 2 hints per turn — good UX design, but the `missing_fields` list returned to the API client is always the full list.

---

### 3.5 `backend/image_quality.py` *(new)*

**Purpose:** Classical CV image quality metrics for one captured surface. Used by the session capture endpoint to flag retake-worthy images.

**Public functions:**
- `assess_image_quality(img_bgr, ocr_line_count) → ImageQuality`
- `estimate_pdp_bbox(ocr_boxes, image_width, image_height) → Optional[Tuple]`

**Metrics:** Laplacian blur variance (normalized to ~[0,1]), midtone exposure, highlight-clipping glare.

**Honest caveats in code:** "Higher is better" polarity documented; "heuristic scale, not a calibrated metric" acknowledged; PDP estimate is explicitly informational and never fed into the font-height legal check.

**Current limitations:**
- All three thresholds (`BLUR_LOW_THRESHOLD=0.15`, `EXPOSURE_LOW_THRESHOLD=0.30`, `GLARE_LOW_THRESHOLD=0.40`) are empirical heuristics, not calibrated against a ground-truth quality dataset.
- `estimate_pdp_bbox` assumes text clustering approximates the PDP — false for packages where declarations are spread across multiple distant surfaces.

---

### 3.6 `backend/report.py` *(new)*

**Purpose:** ReportLab-based PDF report generation. Renders a completed inspection into a 2-page PDF with disclaimer, summary table, and findings table.

**Public function:** `build_inspection_report_pdf(inspection: Dict) → bytes`

**Layout:** Disclaimer (red-bordered box), summary table (inspection metadata + overall status), findings table (rule/field, status, reason, confidence) with coloured status text.

**Design choice — ReportLab vs WeasyPrint:** ReportLab chosen over WeasyPrint to avoid heavy native HTML-renderer dependencies in constrained build environments. Pure Python.

**Current limitations:**
- No bounding-box image with annotations
- No captured surface thumbnails
- No reviewer note in PDF
- No digital signature
- Finding reason text truncated to 220 characters in the table

---

### 3.7 `backend/rule_engine.py` *(modified)*

**New additions:**
- `required_declaration_fields(rules, sale_type, context) → List[str]` — public helper exposing the applicable field list for use by the coverage compute logic
- `_evaluate_rule24_wholesale_declarations(...)` — Rule 24 wholesale package declarations evaluator
- `_evaluate_declaration_rule()` — generalized declaration evaluator shared by Rule 6 and Rule 24
- `run_inspection()` now accepts `best_before_applicable: bool = False` and `is_imported: bool = False` parameters (previously always `False`)
- Rule 24 evaluator wired into `run_inspection()` for `sale_type == "wholesale"`

**Unchanged architecture:** Evidence-first, UNCERTAIN-by-default, `captures`-coverage-gated FAIL.

**Current limitations (unchanged from prior audit):**
- Rules 4, 5, 25, 26(b), 26(c), 27, 31 still have data in `rules.json` but no evaluator
- Rule 7(2) font-width ratio not evaluated
- 10–20 g/ml partial relaxation path not evaluated
- `_evaluate_placement()` is shallow (PASS if any PDP bbox present; no clearance distance calculation)

---

### 3.8 `backend/db/schema.sql` *(modified)*

**New tables/columns:**
- `users` table — `user_id SERIAL PK`, `username TEXT UNIQUE`, `full_name`, `hashed_password`, `role`, `is_active`, `created_at`
- `audit_log` table — append-only, `id`, `occurred_at`, `actor_username`, `action`, `resource_type`, `resource_id`, `detail`, `ip_address`
- `inspection_sessions` table — session metadata, `status` (`OPEN`/`FINALIZED`/`ABANDONED`), `finalized_inspection_id FK`
- `session_captures` table — one row per surface photo in a session, `ocr_fields_json JSONB`, `surface_observation_json JSONB`, `evidence_coverage`
- `inspections.image_path` — full disk path of stored original image (idempotent `ALTER TABLE ... IF NOT EXISTS`)
- `inspections.created_by` — inspector username attribution
- `inspections.reviewed_by` — reviewer username attribution

**Total tables:** 7 (`users`, `products`, `inspections`, `inspection_facts`, `audit_log`, `inspection_sessions`, `session_captures`)

---

### 3.9 `backend/db/persistence.py` *(modified)*

**New functions:**
- `create_user()`, `get_user_by_username()`, `list_users()`, `any_user_exists()`
- `record_audit_event()` — never raises (audit must not break pipeline)
- `list_audit_log()`
- `set_inspection_attribution()` — attaches `created_by` / `image_path` to inspection
- `create_session()`, `get_session()`, `add_session_capture()`, `list_session_captures()`, `finalize_session()`
- `truncate_all_data()` — test-only, wipes all tables with RESTART IDENTITY CASCADE
- `list_sessions()`
- `mark_reviewed()` now accepts `reviewed_by` parameter

**JSONB double-decode fix:** `get_inspection_detail()` and `list_session_captures()` now check `isinstance(raw, str)` before calling `json.loads()`, avoiding `TypeError` when psycopg2 already decoded the JSONB column.

**Remaining limitation:** No connection pooling. New `psycopg2.connect()` call per request via `get_conn()`. Adequate for a demo/hackathon; needs `psycopg2.pool` or an async driver for production load.

---

### 3.10 All other modules unchanged

`schema.py`, `ocr_extraction.py`, `sticker_detection.py`, `product_similarity.py`, `vlm_verifier.py`, `unit_price.py`, `exemption.py` — functionally unchanged from the previous audit. See previous `PROJECT_STATE.md` for full details on each.

---

## 4. DATABASE

### 4.1 Technology
PostgreSQL 16. Python driver: `psycopg2-binary`. No ORM.

### 4.2 Connection Configuration
`config.DATABASE_URL` — from `DATABASE_URL` environment variable (or `backend/.env`). Dev fallback `postgresql://lmpc_app:lmpc_dev_pw@localhost:5432/lmpc` still present in `config.py` but is the env default, not hardcoded in the module that uses it.

### 4.3 Tables (7 total)

| Table | PK | Purpose |
|---|---|---|
| `users` | `user_id SERIAL` | Authentication and RBAC |
| `products` | `product_id TEXT` | Product identity registry |
| `inspections` | `inspection_id TEXT` | Completed inspection records |
| `inspection_facts` | `id SERIAL` | Per-field extracted facts + rule findings |
| `audit_log` | `id SERIAL` | Append-only security/workflow audit trail |
| `inspection_sessions` | `session_id TEXT` | Multi-surface session state |
| `session_captures` | `id SERIAL` | One row per surface photo in a session |

### 4.4 Key Constraints
- `inspections.overall_status CHECK IN ('PASS','FAIL','UNCERTAIN','EXEMPT')`
- `inspection_facts.status CHECK IN ('PASS','FAIL','UNCERTAIN','EXEMPT')`
- `inspections.mrp CHECK >= 0`
- `inspections.net_quantity_value CHECK > 0`
- `inspection_facts.confidence CHECK 0 <= confidence <= 1`
- `inspection_facts ON DELETE CASCADE inspections`
- `session_captures ON DELETE CASCADE inspection_sessions`
- `inspection_sessions.finalized_inspection_id FK → inspections(inspection_id)`

### 4.5 Indexes
10 indexes covering: `inspections(product_id)`, `(overall_status)`, `(created_at DESC)`, partial `(reviewed=FALSE)`, partial `(review_required=TRUE)`, `inspection_facts(inspection_id)`, `(field)`, `(status)`, `(rule_id)`, partial `(review_required=TRUE)`, `audit_log(occurred_at DESC)`, `inspection_sessions(status)`, `(product_id)`, `session_captures(session_id)`.

### 4.6 Migration Strategy
Schema applied via idempotent `CREATE TABLE IF NOT EXISTS` + `DO $$ BEGIN IF NOT EXISTS ... ALTER TABLE ... END $$` blocks on every startup. No separate migration tool. New columns added via the `DO $$` blocks without requiring table drops. Adequate for the current MVP; will need proper Alembic/Flyway migrations before production.

### 4.7 Fresh Database Required?
Yes for a new install. Schema auto-created on startup. Users table is empty — first `POST /auth/register` call creates the bootstrap admin.

---

## 5. API CONTRACT

### 5.1 Authentication Endpoints

| Method | Path | Auth Required | Description |
|---|---|---|---|
| `POST` | `/auth/register` | None (bootstrap once) | Create first admin; subsequent calls return 401 |
| `POST` | `/auth/register/admin` | `admin` | Create any-role user |
| `POST` | `/auth/login` | None | OAuth2 password form → JWT |
| `GET` | `/auth/me` | `inspector+` | Current user info |
| `GET` | `/audit-log` | `admin` | Last N audit events |

### 5.2 Inspection Endpoints

| Method | Path | Auth Required | Description |
|---|---|---|---|
| `POST` | `/scan` | `inspector+` | Full single-surface scan (image + metadata → verdict + PDF-ready result) |
| `POST` | `/inspect` | `inspector+` | Rule engine on pre-structured fields (no image) |
| `POST` | `/analyze-image` | `inspector+` | Sticker + similarity analysis only, no legal verdict |
| `GET` | `/inspections` | `inspector+` | List inspections (newest first, filterable) |
| `GET` | `/inspections/{id}` | `inspector+` | Full inspection detail + facts |
| `POST` | `/inspections/{id}/review` | `reviewer+` | Mark reviewed with note; records `reviewed_by` |
| `GET` | `/inspections/{id}/report.pdf` | `inspector+` | Download ReportLab PDF |
| `GET` | `/products/{id}/history` | `inspector+` | Last 20 inspections for a product |

### 5.3 Multi-Surface Session Endpoints

| Method | Path | Auth Required | Description |
|---|---|---|---|
| `POST` | `/sessions` | `inspector+` | Open a session; returns `session_id` + initial coverage |
| `POST` | `/sessions/{id}/captures` | `inspector+` | Upload one surface image; returns OCR fields + guidance + running coverage |
| `GET` | `/sessions/{id}` | `inspector+` | Current session status + cumulative evidence |
| `POST` | `/sessions/{id}/finalize` | `inspector+` | Run legal engine on merged evidence; returns `ProductInspection` |

### 5.4 Health

| Method | Path | Auth Required | Description |
|---|---|---|---|
| `GET` | `/health` | None | Liveness check |

### 5.5 Notable Behavioral Details
- `POST /sessions/{id}/finalize` returns **409** if session is already FINALIZED and **400** if session has zero captures
- `POST /auth/register` returns **401** if any user already exists (not 403, since no token exists yet)
- `GET /inspections/{id}/report.pdf` returns `Content-Disposition: attachment` PDF bytes
- `POST /scan` includes `vlm_advisory_notes` in response (empty list if VLM disabled)
- All write endpoints record an `audit_log` entry

---

## 6. OCR / VISION PIPELINE

*(Unchanged from previous audit — see full trace there. Summary below.)*

```
UploadFile
  → _read_image_upload() [validate, decode, size-check]
  → run_ocr(pil_img)          [REAL: Tesseract, 3 variants × 2 PSMs, dedupe]
  → classify_fields(lines)    [REAL: 13 regex patterns, conservative heuristic]
  → bridge_classified_fields()  [REAL: vocabulary alias bridge, centralized]
  → _prepare_extractions()    [REAL: Dict[str, RawExtraction]]
  → _infer_applicability_context()  [NEW: best_before + is_imported inference]
  → run_inspection()          [REAL: deterministic legal engine]
```

**Still not in the OCR pipeline:**
- Automatic pixel-to-mm font height measurement
- PDP region segmentation
- Trained field-detection model
- PaddleOCR
- Barcode / QR reading
- Multilingual (Hindi / Indian scripts)
- FSSAI cross-verification

---

## 7. LEGAL / RULE ENGINE

### 7.1 Rules With Working Evaluator

| Rule ID | Clause | Evaluator | Notes |
|---|---|---|---|
| `LMPC-2011-R3-SCOPE` | Rule 3 | `exemption.classify_exemption()` | Working |
| `LMPC-2011-R26-SMALL-PACKS` | Rule 26(a) | `exemption._rule26_small_pack_status()` | Pan-masala exclusion (2026-02-01) included |
| `LMPC-2011-R6-DECLARATIONS` | Rule 6(1) | `rule_engine._evaluate_declaration_rule()` | Retail path; conditional fields now correctly gated |
| `LMPC-2011-R6-11-UNIT-PRICE` | Rule 6(11) | `rule_engine._evaluate_unit_sale_price()` | Decimal arithmetic, verified |
| `LMPC-2011-R7-2-FONT` | Rule 7(2) | `rule_engine._evaluate_font_height()` | Always UNCERTAIN without calibrated measurement |
| `LMPC-2011-R8-PLACEMENT` | Rule 8(1) | `rule_engine._evaluate_placement()` | Shallow — PASS if any PDP bbox present |
| `LMPC-2011-R24-WHOLESALE` | Rule 24 | `rule_engine._evaluate_rule24_wholesale_declarations()` | **NEW** — tested via `/inspect` + unit test |

### 7.2 Rules With No Evaluator (data in `rules.json`, no Python code)

`LMPC-2011-R4-MULTIPACK`, `LMPC-2011-R5-STANDARD-PACK`, `LMPC-2011-R6-10-ECOMMERCE`, `LMPC-2011-R7-PDP-AREA`, `LMPC-2011-R8-2-RETURNABLE-BOTTLE`, `LMPC-2011-R25-EXPORT`, `LMPC-2011-R26-B-FAST-FOOD`, `LMPC-2011-R26-C-DRUG-FORMULATIONS`, `LMPC-2011-R27-REGISTRATION`, `LMPC-2011-R31-ADVERTISEMENT`, `LMPC-2011-R32-PENALTY`, `LMPC-2011-SCHEDULE-II`

### 7.3 Legal Verification Status

All 19 rules carry `verification_status` in `rules.json`. Only 4 are marked anything other than `"needs_official_verification"`:
- `LMPC-2011-R6-11-UNIT-PRICE` — `"verified_against_official_doca_faq_and_2022_amendment_text_but_current_amendment_audit_required"`
- `LMPC-2011-R7-PDP-AREA`, `LMPC-2011-R8-PLACEMENT`, `LMPC-2011-R8-2-RETURNABLE-BOTTLE` — `"verified_against_available_rule_text_but_current_amendment_audit_required"`
- `LMPC-2011-R26-SMALL-PACKS` — `"verified_against_available_rule_text_and_2025_amendment_but_current_amendment_audit_required"`

**All legal thresholds must be independently verified against primary gazette text before authoritative use.**

---

## 8. ML / AI FEATURES

| Feature | Technology | Status |
|---|---|---|
| OCR (text extraction) | Tesseract (pretrained general) | REAL — working; not fine-tuned for Indian labels |
| OCR field classification | Regex heuristics | REAL — no ML |
| Image quality assessment | Classical CV (Laplacian, histogram) | REAL — heuristic, not calibrated |
| Sticker / alteration detection | Classical CV (Canny, gradients) | FALLBACK — advisory only, no trained model |
| Product similarity / visual retrieval | pHash + HSV histogram | FALLBACK — flat JSON index, not deep embedding |
| VLM ambiguity verification | Anthropic Claude (API call) | REAL WIRING — gated; never tested live against API |
| Font-height measurement | Manual calibrated tool (`capture.html`) | MANUAL — no automated path |
| PDP region detection | Heuristic OCR text bounding box | HEURISTIC / INFORMATIONAL — not verified PDP |
| Trained layout / field detector | None | MISSING |
| FSSAI cross-verification | None | MISSING |
| Barcode / QR reading | None | MISSING |

---

## 9. FRONTEND

### 9.1 `frontend/dashboard.html` — Legacy Static SPA

**Status:** Functional for basic demo. **Not updated** to use authentication. Will fail on all API calls with `401 Unauthorized` against the current backend because it sends no `Authorization: Bearer` header.

**Issue:** The dashboard was not updated during Session 1. Every `fetch()` call in the dashboard goes to `http://localhost:8000` without a token. The entire frontend is now broken against the secured backend unless run without auth (which is no longer possible).

**Missing screens:** Login, PDF download, bounding-box overlays, mobile layout.

### 9.2 `frontend/capture.html` — Calibrated Measurement Tool

**Status:** Works as a standalone offline tool. Still manually disconnected from `/scan` and the session API. Unchanged.

### 9.3 Recommended Frontend Work

The dashboard **must be updated to add login and token management** before a demo is possible. Minimum: add a login screen, store token in `sessionStorage`, attach `Authorization: Bearer {token}` to all API calls.

---

## 10. MOBILE READINESS

**Android / React Native / Kotlin:** 0 files. Zero mobile code.
**ARCore / Depth API:** 0 files.
**Offline capture / sync:** 0 files.
**Guided-camera client:** The backend multi-surface session API exists and is tested. Zero client consuming it.
**WebRTC camera (`capture.html`):** Browser-only, unchanged.

**Mobile readiness: 0%.** Unchanged from previous audit.

---

## 11. AUTHENTICATION & SECURITY

### 11.1 Authentication — **NOW IMPLEMENTED**
- bcrypt password hashing via `passlib`
- HS256 JWT tokens, configurable expiry (default 8 hours)
- `OAuth2PasswordBearer` token extraction
- Bootstrap first-user admin pattern

### 11.2 Authorization — **NOW IMPLEMENTED**
- Three-tier RBAC: `inspector < reviewer < admin`
- `require_role(min_role)` FastAPI Depends factory
- All write/read endpoints protected
- `/inspections/{id}/review` requires `reviewer`
- `/audit-log` requires `admin`

### 11.3 Secrets — **IMPROVED**
- `JWT_SECRET_KEY` from environment; refuses startup when absent outside DEV_MODE
- `DATABASE_URL` from environment (fallback still in `config.py` but no longer hardcoded in persistence layer)
- `.env.example` present; `.env` gitignored

### 11.4 CORS — **IMPROVED**
- Now reads from `config.ALLOWED_ORIGINS` (env var, default localhost dev ports)
- No longer `allow_origins=["*"]`

### 11.5 Audit Logging — **NOW IMPLEMENTED**
- `audit_log` table, append-only
- `record_audit_event()` never raises (audit must not break pipeline)
- Events: login success/failure, user creation, inspection creation (both `/scan` and `/inspect`), review, report generation, session create/capture/finalize

### 11.6 File Upload Security
- UUID-prefixed filenames prevent path traversal / collision
- 12 MB upload limit
- Content-type header pre-check (non-authoritative) + actual decoder verification
- Images written to `config.UPLOAD_DIR`; path stored in `inspections.image_path`

### 11.7 Remaining Security Gaps
- No token refresh or revocation
- No rate limiting on auth or upload endpoints
- No HTTPS enforcement (deployment must add TLS termination)
- No connection pooling (new DB connection per request)
- `LMPC_DEV_MODE=true` by default — a misconfigured production deploy would use weak JWT secret silently

---

## 12. REPORTING & AUDIT TRAIL

### 12.1 PDF Generation — **NOW IMPLEMENTED**
- `backend/report.py` — ReportLab, pure Python
- `GET /inspections/{id}/report.pdf` — authenticated, downloads PDF
- Contents: disclaimer, summary table (metadata + overall status), findings table (rule/field, status, reason, confidence with colour coding)
- Verified: produces valid 2-page PDF against real scan

**Gaps:** No inspector photo thumbnails, no bbox overlays, no reviewer note in PDF, no digital signature, findings reason truncated at 220 chars.

### 12.2 Evidence Storage — **NOW IMPLEMENTED**
- Original images stored to `config.UPLOAD_DIR` under UUID-prefixed filename
- `inspections.image_path` column stores full disk path
- Images are NOT in the database (correct); path reference is

**Gap:** No S3/MinIO abstraction — images stored on local disk. Not suitable for distributed deployment.

### 12.3 Audit Trail — **NOW IMPLEMENTED**
- `audit_log` table tracks: actor, action, resource_type, resource_id, detail, timestamp
- `inspections.created_by` / `.reviewed_by` attribution
- `GET /audit-log` admin-only endpoint

**Gap:** IP address logging field exists in schema but never populated from request in current code (always `None`).

### 12.4 Reviewer Workflow — **IMPROVED**
- `POST /inspections/{id}/review` now requires `reviewer` role
- `reviewed_by` username recorded in DB
- Audit event fired on review

---

## 13. DATASET & MODEL READINESS

*(Unchanged from previous audit.)*

| Metric | Value |
|---|---|
| Total images (committed) | 50 synthetic PNG + 3 real pickle PNG + 2 real JPG (in `sample data/`) |
| Synthetic images | 50 (programmatic Pillow, explicitly tagged `synthetic:true`) |
| Real product images committed | 5 (2 JPG + 3 PNG) — **not wired into pipeline** |
| Real product videos | 13 MP4 files in `sample data/` — **not wired into pipeline** |
| Annotation format | JSON, custom schema with field bboxes and expected status |
| Train/val/test split | By product (25 products), no leakage |
| Violation types | 4: missing_consumer_care, missing_mfg_date, tiny_mrp_font, missing_mrp |
| Indian product coverage | None in synthetic data |
| Model training status | Zero trained models, no training scripts |

**Note on `sample data/`:** The 13 MP4 video files and 5 real product photos are valuable real-world evidence that should be converted to frames / cropped stills and added to the training dataset. They are currently unused by the pipeline.

---

## 14. DEPENDENCY AUDIT

### 14.1 `backend/requirements.txt` — Updated

| Package | Version Spec | Role | Status |
|---|---|---|---|
| `fastapi` | >=0.110,<1.0 | Web framework | OK |
| `uvicorn[standard]` | >=0.29,<1.0 | ASGI server | OK |
| `pydantic` | >=2.6,<3.0 | Data validation | OK |
| `python-multipart` | >=0.0.9,<1.0 | File upload | OK |
| `opencv-python-headless` | >=4.9,<5.0 | CV | OK |
| `numpy` | >=1.26,<3.0 | Arrays | OK |
| `Pillow` | >=10.0,<12.0 | Image processing | OK |
| `imagehash` | >=4.3,<5.0 | pHash | OK |
| `httpx` | >=0.27,<1.0 | HTTP (testing) | Declared, unused in runtime code |
| `psycopg2-binary` | >=2.9,<3.0 | PostgreSQL driver | OK |
| `python-dotenv` | >=1.0,<2.0 | Env/config | **NEW** |
| `python-jose[cryptography]` | >=3.3,<4.0 | JWT | **NEW** |
| `passlib[bcrypt]` | >=1.7,<2.0 | Password hashing | **NEW** |
| `bcrypt` | >=4.0,<5.0 | bcrypt backend | **NEW** |
| `reportlab` | >=4.0,<5.0 | PDF generation | **NEW** |
| `pytesseract` | >=0.3.10,<1.0 | OCR wrapper | **FIXED** (was missing) |
| `pytest` | >=8.0,<9.0 | Test runner | **NEW** |
| `pytest-cov` | >=5.0,<6.0 | Coverage | **NEW** |
| `anthropic` | >=0.34,<1.0 | Anthropic Claude | Optional, documented |

**No missing runtime packages.** Tesseract binary documented inline with install commands for Debian/Ubuntu, macOS, Windows.

### 14.2 External Runtime Requirements

| Requirement | Documented |
|---|---|
| Tesseract OCR binary | `requirements.txt` (inline comment) + `SETUP.md` + `Dockerfile` |
| PostgreSQL 16 | `SETUP.md` + `docker-compose.yml` |
| Python 3.12 | `Dockerfile` (python:3.12-slim) — not in `requirements.txt` |

### 14.3 Environment Variables Required

| Variable | Required | Default | Risk |
|---|---|---|---|
| `DATABASE_URL` | No (has fallback) | `postgresql://lmpc_app:lmpc_dev_pw@localhost:5432/lmpc` | Low in dev; fallback must not be used in prod |
| `JWT_SECRET_KEY` | Yes (in prod) | `"dev-only-insecure-secret-change-me"` when DEV_MODE=true | HIGH if prod runs with DEV_MODE=true |
| `LMPC_DEV_MODE` | No | `true` | Defaults to insecure — must be explicitly set `false` for prod |
| `ALLOWED_ORIGINS` | No | localhost dev ports | Must be set to deployed frontend URL in prod |
| `ANTHROPIC_API_KEY` | No | Empty | Only needed if VLM enabled |
| `VLM_VERIFICATION_ENABLED` | No | `false` | Safe default |
| `UPLOAD_DIR` / `REPORT_DIR` | No | `backend/uploads`, `backend/reports` | Must be persistent volumes in Docker |
| `JWT_ALGORITHM` / `JWT_EXPIRE_MINUTES` | No | HS256 / 480 min | OK |

---

## 15. INTEGRATION RISKS

### 15.1 Frontend Broken Against Authenticated Backend (CRITICAL FOR DEMO)
`frontend/dashboard.html` was not updated during Session 1. It makes all API calls without an `Authorization: Bearer` header. Every API call will return `401 Unauthorized`. **The demo frontend will not work against the current backend without adding login/token logic.**

### 15.2 `LMPC_DEV_MODE=true` is the Default
`config.py` line: `DEV_MODE = _env_bool("LMPC_DEV_MODE", True)`. A production deployment that fails to set `LMPC_DEV_MODE=false` will run with the insecure JWT secret silently. The `docker-compose.yml` correctly sets `LMPC_DEV_MODE=false`, but a bare `uvicorn main:app` without setting the variable will use the weak secret.

### 15.3 Docker Build Unverified
`Dockerfile` and `docker-compose.yml` are written correctly and mirror the manually-tested setup, but `docker compose up --build` has never been executed. Likely to work; not confirmed.

### 15.4 `product_id` Extraction Still Uses `:` Split
`_product_id_from_inspection()` in `persistence.py` splits `inspection_id` on `:` to derive `product_id`. A `product_id` containing `:` will produce a wrong `product_id` in the `products` table.

### 15.5 `audit_log.ip_address` Never Populated
The schema has `ip_address TEXT`, `record_audit_event()` accepts `ip_address=None`, and no caller passes a real IP. All audit events have `ip_address = NULL`.

### 15.6 `GET /sessions/{id}` — O(n) Field Recomputation
On every `GET /sessions/{id}` call, all captures are read from DB and fields are re-merged in Python. Fine for sessions with 3–5 captures; will slow for sessions with many captures. No caching.

### 15.7 `product_index.json` Still Empty on Fresh Clone
Similarity index is runtime-generated. All fresh installs show zero similar products until scans accumulate.

### 15.8 `capture.html` / `capture_session` Still Disconnected
The calibrated measurement tool produces a JSON payload for `/inspect` but there is no automated end-to-end path connecting it to the session API. Font-height will always be `UNCERTAIN` in practice.

### 15.9 `CLAUDE MASTERPROMPT.txt` in Repo Root
An AI architect prompt file is committed to the repository root. This is not a security risk but is a non-standard artifact that should either be moved to `docs/` or added to `.gitignore`.

### 15.10 `register` Bootstrap Bug (Cosmetic)
`main.register()`: `role = req.role if db.any_user_exists() else "admin"` — intended to grant admin to the first user. The ternary is inverted from natural reading (the `else` branch fires when `any_user_exists()` is `False`, i.e., no users exist yet). The behavior is correct (first user → admin) but the logic reads as backwards. Should be `role = "admin" if not db.any_user_exists() else req.role`.

---

## 16. DEMO READINESS

### 16.1 Current Live Demo Flow

```
1. Deploy: uvicorn main:app --port 8000 (or docker compose up --build)
2. POST /auth/register → create bootstrap admin
3. POST /auth/login → get JWT token
4. Dashboard: BROKEN — needs auth header added to all fetch() calls
   (Use curl or Postman for the demo until frontend is fixed)
5. POST /scan (with Bearer token + image) → full pipeline → verdict + evidence stored
6. GET /inspections/{id}/report.pdf → download PDF
7. POST /inspections/{id}/review → mark reviewed (reviewer role)
8. GET /audit-log → audit trail (admin role)
```

### 16.2 Exact Failure Points in a Live Demo

| Step | Failure Mode | Probability |
|---|---|---|
| Opening `dashboard.html` in browser | Every API call returns 401 — dashboard completely non-functional | **CERTAIN** |
| `docker compose up --build` | May fail on first try (unverified) | Medium |
| OCR on real product photo | Wrong field or missed field on cluttered / low-quality labels | Medium |
| Font-height check | Always shows UNCERTAIN | **CERTAIN** |
| Similarity index | Empty on first run — "No similar products" | **CERTAIN** on fresh install |
| Rule conditional fields | `best_before_applicable` and `is_imported` correctly inferred now — improved |
| VLM advisory notes | Empty list unless ANTHROPIC_API_KEY + VLM_VERIFICATION_ENABLED=true configured | Likely empty |
| Wholesale `/inspect` | Works — Rule 24 fires correctly | Working |
| PDF report | Works for any completed inspection | Working |
| Audit log | Works — admin can view all events | Working |

---

## 17. RECOMMENDED TARGET ARCHITECTURE

*(Unchanged from previous audit — see there. The backend now fulfils more of this architecture: auth, multi-surface sessions, audit trail, PDF, evidence storage. Remaining gaps: mobile app, React frontend, FAISS, trained models, FSSAI module, offline sync.)*

---

## 18. FILE OWNERSHIP RECOMMENDATION

| File | Workstream | Recommendation |
|---|---|---|
| `rules/rules.json` | A — Legal/Compliance | MODIFY — verify all thresholds against primary gazette; add R25, R26(b/c) evaluable conditions |
| `backend/rule_engine.py` | A — Legal/Compliance | MODIFY — add R4, R25, R26(b/c), R27 evaluators; R7 width ratio; 10–20g path |
| `backend/exemption.py` | A — Legal/Compliance | MODIFY — add R26(b) and R26(c) paths |
| `backend/unit_price.py` | A — Legal/Compliance | MODIFY — add area (m²) unit family |
| `backend/ocr_extraction.py` | B — OCR/CV | MODIFY — add PaddleOCR path; improve column parsing; multilingual support |
| `backend/sticker_detection.py` | B+C — OCR/CV + ML | KEEP then REWRITE when training data available |
| `backend/image_quality.py` | B — OCR/CV | MODIFY — calibrate thresholds against real photos |
| `backend/capture_session.py` | B+D — OCR/CV + Platform | MODIFY — performance (cache `load_rules()`) |
| `backend/product_similarity.py` | C — ML/Intelligence | MODIFY — replace flat JSON with FAISS; replace pHash+hist with CLIP |
| `backend/vlm_verifier.py` | C — ML/Intelligence | KEEP — already connected; test against live API |
| `backend/schema.py` | D — Platform | KEEP — stable contract |
| `backend/main.py` | D — Platform | MODIFY — fix frontend auth issue; add IP logging; fix register ternary |
| `backend/auth.py` | D — Platform | MODIFY — add token refresh; add rate limiting |
| `backend/config.py` | D — Platform | MODIFY — change `DEV_MODE` default to `False` |
| `backend/db/schema.sql` | D — Platform | MODIFY — add Alembic migration support |
| `backend/db/persistence.py` | D — Platform | MODIFY — add connection pooling; populate IP in audit log |
| `backend/report.py` | D — Platform | MODIFY — add surface thumbnails, reviewer note, bbox overlays |
| `backend/db/__init__.py` | D — Platform | KEEP (empty package marker) |
| `backend/requirements.txt` | D — Platform | KEEP — now complete |
| `backend/Dockerfile` | D — Platform | KEEP — verify with actual Docker |
| `backend/config.py` | D — Platform | MODIFY — change DEV_MODE default |
| `backend/.env.example` | D — Platform | KEEP |
| `docker-compose.yml` | D — Platform | KEEP — verify with actual Docker |
| `frontend/dashboard.html` | D — Platform | MODIFY — add auth/token logic (P0 for demo) |
| `frontend/capture.html` | D — Platform | MODIFY — connect to session API |
| `dataset/generate_dataset.py` | C — ML | KEEP — fix Linux font path for Windows |
| `dataset/images/` | C — ML | KEEP + add real photos |
| `dataset/annotations/annotations.json` | C — ML | KEEP + supplement with real annotations |
| `sample data/` | C — ML | MOVE to `dataset/real_samples/`; wire into pipeline |
| `README.md`, `SETUP.md`, `IMPLEMENTATION_STATUS.md` | D — Platform | KEEP + update |
| `ENGINE_UPGRADE_NOTES.md` | D — Platform | KEEP |
| `.gitignore` | D — Platform | MODIFY — add `CLAUDE MASTERPROMPT.txt` |
| `CLAUDE MASTERPROMPT.txt` | D — Platform | MOVE to `docs/` or DELETE from git |

---

## 19. INTEGRATION CONTRACT

*(Unchanged from previous audit — canonical field names, `RawExtraction`, `ExtractedFact`, `FactStatus` enum, `MeasurementMode` enum must not be duplicated or renamed. The `bridge_classified_fields()` function in `capture_session.py` is now the single authoritative alias location.)*

**NEW constraint:** All callers building `RawExtraction` dicts must use the rule-engine vocabulary field names (not OCR vocabulary). For OCR-derived data, always pass through `bridge_classified_fields()` first.

---

## 20. PRIORITY ROADMAP

### P0 — Blocks Demo

| Issue | Fix | Effort |
|---|---|---|
| `frontend/dashboard.html` sends no auth header — every API call returns 401 | Add login screen, store JWT in `sessionStorage`, attach `Authorization: Bearer` header to all fetch() calls | 2–3 hours |
| Docker build unverified | Run `docker compose up --build` + `curl localhost:8000/health` in a Docker environment | 1 hour |

### P1 — Required for SIH MVP

| Issue | Fix | Effort |
|---|---|---|
| No mobile application | React Native guided-camera app | Multi-day |
| `LMPC_DEV_MODE` defaults to `true` | Change default to `false`; update docs | 15 min |
| `audit_log.ip_address` never populated | Pass `request.client.host` to `record_audit_event()` | 30 min |
| `register` bootstrap ternary is inverted (cosmetic bug) | Flip condition | 5 min |
| Rule 25 (export repack) evaluator missing | Implement `_evaluate_rule25_export()` | 2 hours |
| `capture.html` → session API connection | Auto-POST calibration data to `/sessions/{id}/captures` | 2 hours |
| Real product photos needed | Collect 30–50 real Indian SKU photos | Real-world collection |
| Editable export (CSV) | Add `GET /inspections/export.csv` | 2 hours |

### P2 — Important Enhancement

| Issue | Fix | Effort |
|---|---|---|
| Rules R4, R26(b), R26(c), R27 evaluators | Implement | 4–8 hours |
| FAISS product similarity index | Replace flat JSON with FAISS | 3 hours |
| Connection pooling | `psycopg2.pool.SimpleConnectionPool` | 2 hours |
| PaddleOCR integration | Uncomment + test + add multilingual support | 1–2 days |
| Font-height auto-measurement | Wire `capture.html` calibration into session pipeline | 4 hours |
| `GET /sessions/{id}` performance | Cache accumulated fields in session table | 2 hours |
| Bounding-box overlay in dashboard | Draw `bbox` from facts onto uploaded image | 3 hours |
| Token refresh endpoint | `POST /auth/refresh` | 1 hour |
| Alembic migrations | Replace startup-DDL pattern | 3 hours |
| Test coverage for session API | Add disjoint front/back test fixture | 2 hours |

### P3 — Future Feature

| Issue | Fix | Effort |
|---|---|---|
| Trained OCR layout model | Collect labels; fine-tune LayoutLM / YOLO | Weeks |
| Trained sticker classifier | Collect paired altered/original photos | Weeks |
| FSSAI cross-verification | FSSAI API integration | Multi-day |
| CLIP-based visual embeddings | Replace pHash+histogram | 1–2 days |
| ARCore / depth-sensor scanning | Android native app | Multi-day |
| Offline capture with sync | Service worker + local SQLite | Multi-day |
| Analytics / trend dashboard | Chart.js / Recharts integration | 2–3 days |

---

## 21. FINAL VERDICT

### Architecture Quality
**Significantly improved. Now architecturally sound end-to-end for a government inspection prototype.** The separation of concerns (config → auth → OCR → rule engine → persistence → report) is clean. The multi-surface session model is correctly implemented and tested. The audit trail, RBAC, and evidence retention are production-worthy in concept even if not production-scaled.

### Current Functionality
**End-to-end pipeline works** for retail and wholesale, single and multi-surface, with authentication, evidence storage, PDF reports, audit trail, and review workflow. Rule 6, Rule 6(11), Rule 7(2), Rule 8, Rule 24, and Rule 3/26(a) exemptions are all evaluated. Two real products were tested successfully (per IMPLEMENTATION_STATUS.md). Test suite has 34 passing tests.

### Biggest Technical Risks
1. **Dashboard broken against secured backend** — demo will fail at the first browser interaction
2. **Docker unverified** — deployment path not confirmed
3. **No mobile app** — a primary SIH requirement is unmet
4. **OCR accuracy on real Indian labels** — no trained layout model
5. **All rule thresholds unverified** against primary gazette

### Biggest Legal Risks
1. All rule thresholds carry `"needs_official_verification"` — incorrect thresholds produce wrong PASS/EXEMPT
2. Best-before now correctly inferred for perishable categories but the category list (`food`, `beverage`, `dairy`, `bakery`, `confectionery`) is a heuristic, not a legally-defined list
3. `is_imported` inference from `country_of_origin` OCR is conservative but not definitive
4. No Rule 25 evaluator — export packages re-sold in India are not flagged
5. Disclaimer correctly present in PDF; must also be prominently shown in all frontend screens

### Biggest Demo Risks
1. Dashboard returns 401 on every API call — **demo blocker**
2. Docker not tested — deployment may fail
3. Font-height always UNCERTAIN
4. Similarity index empty on first install
5. No mobile inspection experience

### Exact Next 10 Implementation Steps

1. **Fix `frontend/dashboard.html`** — add login screen, store JWT in `sessionStorage`, attach `Authorization: Bearer {token}` to every `fetch()` call. 2–3 hours. **Demo blocker.**

2. **Verify Docker: `docker compose up --build` + `curl localhost:8000/health`** in an environment with Docker installed. Fix any apt/pip failures. 1 hour.

3. **Change `LMPC_DEV_MODE` default to `False`** in `config.py` — currently `_env_bool("LMPC_DEV_MODE", True)`. 1-line change. Prevents accidentally deploying with insecure JWT secret.

4. **Populate `audit_log.ip_address`** — pass `request.client.host` from the FastAPI `Request` object to `record_audit_event()` in `/scan`, `/inspect`, `/auth/login`. 30 minutes.

5. **Fix `register` bootstrap ternary** in `main.register()` — change `req.role if db.any_user_exists() else "admin"` to `"admin" if not db.any_user_exists() else req.role`. 5 minutes.

6. **Build a minimal guided-capture web client** (even a second static HTML page) that calls `POST /sessions`, `POST /sessions/{id}/captures`, and `POST /sessions/{id}/finalize` sequentially — this makes the multi-surface backend visible and testable from a browser without needing the mobile app. 3–4 hours.

7. **Implement Rule 25 (export repack) evaluator** — add `_evaluate_rule25_export()` to `rule_engine.py` following the same pattern as Rule 24. The exemption engine already handles the `is_export_only + sale_type="export"` path; Rule 25 handles the case where an export package is then sold domestically. 2 hours.

8. **Wire `sample data/` real photos into the test pipeline** — add the 5 committed real product images (2 JPG + 3 pickle PNG) and sample video frames to `dataset/real_samples/`; run them through `/scan` with manual field verification; document the results in `IMPLEMENTATION_STATUS.md`. This builds demo credibility beyond the synthetic dataset.

9. **Add editable CSV export** — `GET /inspections/export.csv` that streams inspections as CSV (inspection_id, product_id, status, mrp, date, reviewed). 2 hours. Required per SIH problem statement ("export to … editable formats").

10. **Replace flat JSON similarity index with FAISS** in `product_similarity.py` — the interface (`embed_image`, `find_similar`, `save_to_index`) is already clean. Swap `load_index()` / linear scan for a FAISS `IndexFlatL2` with a JSON-side metadata store for `product_id`, `mrp`, `scanned_at`. 3–4 hours. Eliminates the O(n) scan limitation.

---

*End of PROJECT_STATE.md*
*Audit completed: September 2026 (Post Session 1)*
*Auditor: Kiro — read-only, no project files modified*
