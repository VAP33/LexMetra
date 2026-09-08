# IMPLEMENTATION_STATUS.md
## SIH 2026 — PS 26034 — Legal Metrology Compliance Platform
### Execution log (persistent — read this + PROJECT_STATE.md before resuming work)

This file is a chronological work log. `PROJECT_STATE.md` is the current
high-level snapshot. If they ever disagree, trust the repository itself
first, this log second (it records *why*, not just *what*).

---

## Session 1 — Backend hardening pass

Started from a pre-existing, honest, read-only audit (`PROJECT_STATE.md`,
Sept 2026, ~35% complete / pre-alpha). Followed its own P0→P1→P2 roadmap
rather than re-deriving one.

### Completed

1. **P0 fixes**
   - Added missing `pytesseract`, `python-dotenv`, `python-jose[cryptography]`,
     `passlib[bcrypt]`, `bcrypt`, `reportlab`, `pytest`, `pytest-cov` to
     `backend/requirements.txt`. Documented the Tesseract *binary* (non-pip)
     dependency inline.
   - Confirmed `ocr_extraction.run_ocr()` already degrades gracefully
     (per-call `try/except`) if the Tesseract binary is absent — this
     specific claim in the prior audit was verified true, not just assumed.
   - Moved `DATABASE_URL` out of source into `backend/config.py`
     (env-var driven, `.env` support via `python-dotenv`). Added
     `backend/.env.example`. `config.py` refuses to start with the
     placeholder JWT secret unless `LMPC_DEV_MODE=true`.

2. **Authentication & RBAC (new)**
   - `backend/auth.py`: bcrypt password hashing, JWT issuing/verification,
     three-tier role hierarchy (`inspector` < `reviewer` < `admin`),
     FastAPI dependencies (`require_inspector`, `require_reviewer`,
     `require_admin`).
   - `db/schema.sql`: new `users` table. Bootstrap rule — the very first
     `/auth/register` call on a fresh DB is allowed unauthenticated and is
     granted `admin`; every subsequent registration requires an
     authenticated admin via `/auth/register/admin`.
   - All write/read endpoints (`/scan`, `/inspect`, `/analyze-image`,
     `/inspections*`, `/products/*/history`, `/sessions*`) now require at
     least `inspector`. `/inspections/{id}/review` requires `reviewer`.
     `/audit-log` requires `admin`.
   - CORS origins now read from `config.ALLOWED_ORIGINS` (was `["*"]`).

3. **Audit trail (new)**
   - `db/schema.sql`: `audit_log` table (append-only). `db.record_audit_event()`
     never raises — audit logging cannot break the inspection pipeline.
   - Logged: login success/failure, user creation, inspection creation
     (via `/scan`, `/inspect`, and session finalize), review actions,
     report generation, session creation/capture/finalization.
   - `inspections.created_by` / `.reviewed_by` / `.image_path` columns added
     (idempotent `ALTER TABLE ... IF NOT EXISTS` migration block).

4. **Evidence retention (new)**
   - `/scan` and session captures now write the original uploaded image to
     `config.UPLOAD_DIR` under a UUID-prefixed filename (prevents path
     traversal / collision from a client-supplied filename) and store the
     path against the inspection record. Previously images were processed
     and discarded — a real legal-evidence gap, now closed.

5. **PDF report generation (new)**
   - `backend/report.py` (reportlab, not WeasyPrint — avoids native-dep
     fragility). `GET /inspections/{id}/report.pdf`. Renders the mandatory
     disclaimer ("automated screening / pre-inspection aid, not a final
     legal determination"), summary table, and a findings table with rule
     ID / status / reason / confidence per finding. Verified: produces a
     valid 2-page PDF against a real synthetic-dataset scan.

6. **Rule 24 (wholesale) evaluator (new)**
   - Generalized the Rule 6 declaration evaluator in `rule_engine.py` into
     `_evaluate_declaration_rule()`, reused for a new
     `_evaluate_rule24_wholesale_declarations()`, wired into `run_inspection()`
     for `sale_type == "wholesale"`. Added a new public
     `required_declaration_fields()` helper (used later by the capture-
     session coverage math). Verified via `/inspect` with a wholesale
     payload: Rule 24 facts fire, Rule 6 facts do not.

7. **Field-name bridge fix / consolidation**
   - The OCR→rule-vocabulary bridge (`manufacturer_name` →
     `manufacturer_name_address`, `expiry_date` → `best_before_use_by`,
     `net_quantity` → `wholesale_count_or_net_quantity`) previously lived
     only in `main._prepare_extractions()` and was applied inconsistently
     (missing from `/inspect` entirely). Extracted into a single
     `capture_session.bridge_classified_fields()` and made it the *only*
     place this mapping is defined; both `main._prepare_extractions()` and
     the new capture-session coverage math now call it. Applied the bridge
     to `/inspect` for the first time.

8. **Conservative applicability inference (new)**
   - `main._infer_applicability_context()`: `best_before_applicable` now
     inferred from a perishable-category allowlist (food/beverage/dairy/
     bakery/confectionery); `is_imported` inferred only from an explicit
     caller flag or a *positively extracted* non-India country-of-origin
     OCR value — absence of that field is never treated as "not imported"
     (would silently skip the very check meant to catch undeclared
     imports). Both flags previously defaulted to `False` unconditionally.

9. **Multi-surface capture sessions (new — the core architectural gap
   identified in the original audit, section 1.5 "Multi-surface / multi-image
   session stitching: schema supports it; no capture orchestration")**
   - `backend/capture_session.py`: merges per-capture OCR fields across a
     session (keeps the higher-confidence reading per field on conflict),
     computes real evidence coverage using the exact same
     `required_declaration_fields()` the legal engine uses, generates
     human capture guidance ("Capture the panel showing the MRP",
     "Evidence sufficient for applicable checks", etc.).
   - `backend/image_quality.py`: classical-CV (Laplacian blur, exposure,
     highlight-clipping glare) image-quality assessment, and a heuristic
     PDP bounding-box estimate from OCR text clustering (explicitly
     informational, never fed into the font-height legal check, which
     still requires a separately-calibrated `pdp_area_cm2`).
   - `db/schema.sql`: `inspection_sessions` + `session_captures` tables.
   - New endpoints: `POST /sessions`, `POST /sessions/{id}/captures`,
     `GET /sessions/{id}`, `POST /sessions/{id}/finalize`.
   - **Two real bugs found and fixed during live testing (not just written
     — actually exercised against a running Postgres instance):**
     a. Coverage math was checking raw OCR field names instead of bridged
        rule-vocabulary names (see item 7) — a present declaration would
        be reported as permanently "missing" to the inspector. Fixed by
        the bridge consolidation above.
     b. **JSONB double-decode bug**: `session_captures.ocr_fields_json` /
        `surface_observation_json` (and the pre-existing
        `inspection_facts.evidence_json`) are `JSONB` columns; psycopg2
        auto-decodes these to native Python objects on read. The original
        code (both the new session-read path AND the pre-existing
        `get_inspection_detail()` evidence decode, which predates this
        session) called `json.loads()` on the already-decoded object,
        raised `TypeError`, silently caught it, and reset the value to
        `{}` / `None`. This meant every persisted fact's `evidence` field
        was silently `None`, and session coverage silently reset to `0.0`
        on any read-back. Fixed both call sites to handle either a raw
        JSON string or an already-decoded object.
   - Verified end-to-end after the fix: create session, one capture reaches
     75% coverage, guidance correctly lists only genuinely-missing fields,
     `GET /sessions/{id}` read-back matches, and `finalize` produces a real
     `FAIL` for declarations confirmed absent with sufficient coverage
     (not a permanent `UNCERTAIN`), `PASS` for everything found, and
     rejects a second finalize attempt (409) and an empty-session finalize
     (400).

10. **Test suite (new — was zero test files)**
    - `backend/tests/`: `test_exemption.py`, `test_rule_engine.py`,
      `test_auth.py`, `test_capture_session.py` (unit, no DB required) and
      `test_api_integration.py` (live FastAPI `TestClient` + real Postgres).
    - `tests/conftest.py`: `db_ready` session fixture now calls
      `db.truncate_all_data()` before each test run so results never depend
      on leftover manual-testing data in the same `DATABASE_URL` — this is
      opt-out via `LMPC_TEST_RESET_DB=false`, and is documented as
      destructive/test-only. Do not point this test suite at a database
      containing real inspection records.
    - Current result: 34 passed, 0 skipped (verified live, not assumed).
    - Two test-authoring bugs were caught and fixed along the way (both in
      test assumptions, not product code): the export-exemption test needs
      `sale_type="export"`, not just `is_export_only=True` — the product
      code was already correctly conservative here (an export-marked
      package sold at retail is NOT silently exempt; Rule 25 governs that
      case) — and a pytest fixture scope mismatch.

11. **Deployment**
    - `backend/Dockerfile` (python:3.12-slim + tesseract-ocr installed via
      apt, since it's a native binary pytesseract needs), `docker-compose.yml`
      (backend + Postgres 16, healthchecked, named volumes for DB/uploads/
      reports), `.dockerignore`.
    - Not yet verified: Docker itself is not available in this sandbox
      (`docker: not found`), so the image build/compose-up has NOT been
      executed. The Dockerfile mirrors the exact manual setup (same apt
      packages, same pip requirements, same env var names) already
      validated live outside a container. Verify `docker compose up --build`
      plus `curl localhost:8000/health` on first use in an environment with
      Docker.

### Manually verified live (curl + running uvicorn + real Postgres 16 + real synthetic-dataset images), in addition to the pytest suite
- `/health`, `/auth/register` (bootstrap), `/auth/login`, `/auth/me`
- RBAC: unauthenticated `/scan` returns 401; inspector calling `/review` returns 403
- `/scan` full pipeline: OCR to field extraction to rule engine to Postgres
  persistence to evidence image saved on disk
- `/inspect` wholesale payload: Rule 24 facts fire, not Rule 6
- `/inspections`, `/inspections/{id}/report.pdf` (valid 2-page PDF)
- `/inspections/{id}/review` (reviewer role, `reviewed_by` recorded)
- `/audit-log` (admin-only, contains the actions above)
- `/sessions`, `/sessions/{id}/captures` (x2), `/sessions/{id}`,
  `/sessions/{id}/finalize` (see item 9 above)

### Known issues / accepted limitations at end of this session
- The synthetic dataset (`dataset/images/`) has one label-image per
  product covering nearly all fields, so multi-surface testing so far
  exercises "second photo of the same product" merging, not a genuine
  disjoint front/back split. Real product photos (or a purpose-built
  two-surface synthetic pair) would exercise the coverage math more
  realistically — this is a test-data gap, not a code gap.
- `vlm_verifier.py` is wired into `/scan` (`_apply_vlm_verification`) but
  gated behind `VLM_VERIFICATION_ENABLED=true` plus `ANTHROPIC_API_KEY`;
  not exercised end-to-end against a live Anthropic API in this session
  (would require a real key; `api.anthropic.com` is in the sandbox's
  allowed domain list, so this is untested rather than unsupported).
- Docker build unverified (see above).
- No mobile application, ARCore/depth integration, or offline/sync layer.
  The multi-surface backend orchestration now exists (item 9), but there
  is no guided-camera client consuming it yet.
- Rules 4, 5, 25, 26(b), 26(c), 27, 31 still have data in `rules.json` but
  no evaluator in `rule_engine.py` (unchanged from the original audit).
- Rule 7(2) font-height check still requires a manually-calibrated
  `pdp_area_cm2`; no automatic pixel-to-mm path (unchanged).
- Trained OCR layout model, trained tamper/sticker classifier, real product
  photo dataset: none added (explicitly out of scope for a code-only
  session; these need real data collection).

### Exact next actions (priority order, for whoever resumes this)
1. Verify `docker compose up --build` end-to-end in an environment with
   Docker; fix any image-build issues (most likely candidate: apt package
   names/versions on a fresh `python:3.12-slim` pull).
2. Build a genuine two-surface synthetic test fixture (front label missing
   manufacturer info, back label missing MRP, e.g.) to properly exercise
   `capture_session` coverage math with disjoint evidence per photo.
3. Wire a minimal guided-capture client (even a thin web page using
   `/sessions/*`) so the multi-surface backend has some consumer beyond
   curl — this is the natural next visible milestone before a real mobile
   app.
4. Implement Rule 25 (export repack) evaluator — currently the only
   sale-type-conditional path with zero evaluator coverage that also has a
   clear exemption-engine interaction already documented in
   `exemption.py`'s comments (see `exemption.py` lines ~299-301).
5. Decide and document a strategy for `product_similarity.py`'s flat JSON
   index (currently fine for a demo, will not scale — unchanged from
   original audit).
