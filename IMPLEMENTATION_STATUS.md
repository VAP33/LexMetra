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

---

## Session 3 — Vision-layer verification and legal-core testability

> **Note on numbering:** Session 2 built the region-first OCR pipeline
> (`preprocess.py`, `region_detection.py`, `ocr_engine.py`, the `images dataset/`
> folder) and was never written up here — that session ended abruptly. Its output
> is in the repository and is covered by the tests described below. This section
> is Session 3.

This session did not add features. It closed verification gaps, and in doing
so found and fixed two real defects. Everything below was measured or executed;
nothing is asserted from inspection alone.

### Two real defects found and fixed

**1. Fusion could report two contradictory numbers as mutually confirming.**
`text_similarity("NET QUANTITY 100 g", "NET QUANTITY 700 g")` is 0.9333, above
the 0.86 agreement threshold, so two OCR passes that flatly disagreed about the
net quantity were fused as CORROBORATED **and given a confidence bonus**. One
wrong digit in a long line barely moves a character ratio. Fixed by
`numeric_signature()` / `readings_agree()` in `ocr_engine.py`: agreement now
requires both glyph similarity AND identical ordered digit runs (after
glyph-confusion canonicalisation, so `1OO` vs `100` is not a false conflict).
A numeric disagreement is now always CONFLICTING and is never resolved
automatically. Measured effect on real photographs: conflicts on dataset image 0
rose 22 → 24 while usable characters were essentially unchanged (1282 vs 1284),
i.e. it flagged two genuinely contradictory groups without costing recall.

**2. Unrecognised legal conditions silently became mandatory requirements.**
`_condition_is_applicable()` in `rule_engine.py` ended in a bare `return True`,
so any `condition` string in `rules.json` that the engine did not implement made
its requirement unconditionally applicable. `rules.json` already ships three such
strings (`pan_masala`, `tobacco_or_tobacco_product`,
`package_is_within_the_partial_relaxation_range`). Verified before fixing: a
requirement conditioned on `tobacco_or_tobacco_product` was returned as mandatory
for a package whose context said nothing about tobacco — and once package
coverage is sufficient, an absent mandatory declaration becomes **FAIL**. That is
the system accusing a compliant package of breaking the law.

To be precise about severity: this was **latent, not live**. The only one of the
three currently sitting in a `requirements` list has `field: None`, so
`_build_requirement_map` skipped it at its `if not field` guard. It was one
rules.json edit away from being live.

Fixed with a genuine tri-state, `condition_applicability()` returning
`APPLICABLE` / `NOT_APPLICABLE` / `APPLICABILITY_UNKNOWN`. Returning False
instead would merely have traded a false FAIL for a false PASS (the requirement
would be silently dropped), so neither boolean is honest. An UNKNOWN requirement
is still evaluated and still reported, but its absence can only ever produce
UNCERTAIN. Defaults are only applied where this engine's own public API
publishes one (mirroring `run_inspection()`'s keyword defaults, guarded against
drift by `test_condition_defaults_match_the_public_api`); the three conditions
with no published default are never assumed in either direction.

### One negative result, recorded in code so it is not re-attempted
De-duplicating overlapping OCR read-sets looked like a free 36% speedup
(32.6s → 21.0s on image 0). It is harmful and was reverted. Two measured
reasons, both documented at length above `select_regions_to_read()` in
`ocr_engine.py` and guarded by
`test_overlapping_reads_are_deliberately_not_deduplicated`:
- **Recall.** A small crop is preprocessed on its own terms; the same text
  inside a large panel is thresholded against panel statistics and left too
  small for Tesseract. On image 0 three prose lines read correctly from the
  contained region (conf 0.96) and as garbage from the containing region
  (conf 0.15). Image 7 lost 27% of its characters at identical wall-clock time.
  An area-ratio guard recovered images 3 and 7 but not image 0 — geometry does
  not predict which recipe reads better.
- **Evidence quality, which matters more.** Reading the same pixels under
  different recipes is the only source of CORROBORATED/CONFLICTING within a
  single image. Removing the redundancy does not remove the disagreement in the
  pixels, only our knowledge of it — the spurious `'17m'` went from CONFLICTING
  at conf 0.93 to CORROBORATED at conf 1.00. That converts an honest "sources
  disagree" into unearned confidence.

### Test suite: 171 passed, 1 collection error, 10 skipped
`test_orientation` (26, new), `test_ocr_engine` (46, new), `test_rule_engine`
(6 → 21), `test_preprocess` (35), `test_region_detection` (30),
`test_capture_session` (9), `test_exemption` (4).

`map_bbox_from_rotated` is now genuinely verified rather than assumed: all four
orientations × 24+ boxes on deliberately odd non-square dimensions, rotated
forward *by construction* (a mask containing only the box is rotated and the box
read back out of it, so the test does not depend on the arithmetic it checks),
plus a pixel-level check that the mapped box covers the same ink count.

### Performance: measured, and the remaining lever identified
~24s per dense 2392×1080 phone screenshot. cProfile on dataset image 7:
**22.62s of 26.17s is inside 14 Tesseract subprocess calls** (1.615s each), 2.24s
is the one-time `import pytesseract` (amortises to zero in a long-lived server
process), and ~1.3s covers detection, preprocessing, orientation and fusion
combined. The pipeline is ~94% Tesseract subprocess latency in steady state.

Three candidate levers were tested and two are ruled out by measurement:
read-set de-duplication (harmful, above) and `READ_TILE_MAX_SIDE_PX`. The one
remaining lever is **variant ranking quality** — `OCR_VARIANT_SLOTS` cannot drop
from 3 to 2 without losing 41% of image 3's characters, which means the best
variant is often not ranked first. Ranking better, not reading less, is where the
time is.

An earlier apparent timing regression (16.77s → 25.1s on image 7) was checked
rather than attributed: three consecutive runs gave 25.08 / 24.61 / 23.27s with
byte-identical output (14 calls, 466 chars), and the profile puts the cost in
Tesseract subprocesses, not in the new numeric check. It is host load, not the
change.

### ENVIRONMENT BLOCK — read this before trusting any test result
`fastapi`, `psycopg2`, `jose`, `passlib` and `pyzbar` are not installed in the
development container and **cannot be installed** (`pip` fails with
`ProxyError: Tunnel connection failed: 403 Forbidden`; no cached wheels, no
venvs). Consequences, stated plainly:

- **The test suite runs under two shims, not under its real dependencies.**
  `backend/tools/run_tests.py` provides a minimal pytest replacement, and
  `backend/tools/pydantic_shim.py` provides a strict stand-in for the slice of
  pydantic that `schema.py` uses. Both are labelled at every run and both defer
  to the real library when it is importable, so CI cannot silently diverge.
- **The legal rule engine now genuinely executes here** (this is new; it was a
  collection error before), but its required-field, `ge`/`le` and `extra=forbid`
  guarantees are currently enforced by the shim rather than by pydantic. The shim
  is deliberately strict for that reason — it caught an invalid `ImageQuality`
  field during this session. Even so, **the suite must be re-run under real
  pydantic before any release claim.**
- **`test_auth` is still a collection error** (needs fastapi). The auth, API and
  DB layers have not been executed in this environment at all.
- Barcode/QR decoding (`pyzbar`) is unavailable, so that path is unexercised.

A refactor of `schema.py`'s models to plain dataclasses was considered as a
cleaner fix and **deliberately rejected**: `schema.py` is also imported by
`main.py`, `persistence.py` and `ocr_extraction.py`, none of which can be
executed here either, so the refactor could not have been verified. Rewriting
working legal code that cannot be re-tested is the larger risk.

### What may NOT be claimed at the end of this session
The vision layer (preprocessing, region detection, orientation, OCR routing,
fusion) is tested and measured on real dataset photographs. The rule engine's
legal-safety invariants are tested. Nothing here justifies "verified", "production
ready" or "SIH DEMO READY" for:
- the API, auth or database layers (never executed here),
- OCR *accuracy* (there is still no labelled ground-truth set; `usable_chars` is
  a regression proxy and cannot distinguish a correct read from a confident
  misread),
- end-to-end camera → report workflow (not yet run end to end).

### Exact next actions (priority order)
1. Install real pytest + pydantic + fastapi in an unrestricted environment and
   re-run the whole suite. Until that happens, every count above carries the
   shim caveat.
2. Improve OCR variant RANKING (the one remaining speed lever, above). Success
   criterion: `OCR_VARIANT_SLOTS` 3 → 2 without losing recall on image 3.
3. Build a labelled ground-truth set for a handful of dataset images so accuracy
   can be stated instead of proxied.
4. Rules 4, 5, 25, 26(b)/(c), 27, 31 evaluators (unchanged from Session 1).
5. Frontend: the auth-less dashboard P0 blocker is still open.
