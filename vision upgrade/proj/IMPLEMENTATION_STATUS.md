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

## Session 2 — Vision/Evidence Engine upgrade (real photos, no phase gating)

Continued directly from Session 1's checkpoint per instruction; no
approval-gated phases. Worked against 29 real, user-supplied phone photos
(`dataset/real_photos/`, NOT the synthetic generator output) throughout —
every claim below that says "verified" was checked against either a real
photo, a live PostgreSQL instance actually running in this sandbox, or the
existing test suite (never asserted from memory).

### Completed and verified

1. **Environment fix**: pinned `bcrypt==4.0.1` in `requirements.txt` — the
   previously-installed bcrypt/passlib combination was silently failing
   password verification, breaking 2 auth tests. Fixed; both pass now.

2. **Region-aware image quality** (`image_quality.py`, extended):
   `assess_region_quality()`, `assess_field_quality_map()`,
   `build_recapture_guidance()`. Reuses the existing blur/exposure/glare
   heuristics but scoped to one field's bbox, so "glare over MRP" no longer
   gets averaged away by an otherwise-fine photo. Wired into
   `/sessions/{id}/captures` (`recapture_guidance` in the response).

3. **Evidence provenance schema** (`schema.py`, additive): new
   `EvidenceVerification` enum (`VERIFIED` / `CORROBORATED` / `CONFLICTING`
   / `UNCERTAIN` / `NOT_OBSERVED`) plus `source_images`, `ocr_engines`,
   `spatial_relationship`, `conflicting_values` on `ExtractedFact`. Additive
   only — `extra="forbid"` models still validate on old records.

4. **Multi-engine OCR abstraction** (`ocr_engines.py`): Tesseract always on;
   PaddleOCR wired as a real adapter behind `OCR_ENABLE_PADDLE`, lazy,
   fails closed on any import/model/inference error.
   **Verified fact, not assumption**: a direct HTTPS probe to
   `paddleocr.bj.bcebos.com` (PaddleOCR's model host) from this sandbox
   returned a proxy-level 403. PaddleOCR is therefore implemented but
   **UNVERIFIED at runtime in this environment** — confirm model download
   works in your actual deployment target before relying on it. Nothing in
   this codebase reports a PaddleOCR result that wasn't actually produced.

5. **Orientation-aware OCR** (`orientation_ocr.py`, new): per-region (NOT
   whole-image) rotation handling — classical dual-directional morphology
   to find horizontal vs. vertical text blocks, Tesseract OSD + a
   best-of-two-rotations disambiguation (tries both 90°/270° and keeps
   whichever actually reads real words) when OSD isn't confident, then maps
   every line's bbox back to the original image's coordinate system.
   **Verified on a real photo**: the Vaseline body-lotion label
   (`dataset/real_photos/...22-07-38-18...jpg`) has a genuinely sideways
   "NET VOL. WHEN PACKED" column next to normal horizontal text. Baseline
   whole-image OCR could not read it at all (garbled fragments only,
   confidence <0.5). With orientation handling it now reads "NET VOL. WHEN
   PACKED" correctly at 0.93 confidence. Locked in as a permanent regression
   fixture (`tests/test_orientation_ocr.py`, 4/4 passing, including a pure
   coordinate-math roundtrip test independent of any image).
   **Known limitation**: this recovers rotated text blocks; it does not
   improve reading of small, dense, correctly-oriented print on a curved
   surface — the Vaseline label's main horizontal paragraph remains
   low-confidence/garbled regardless of orientation handling. That is a
   separate, harder problem (resolution/curvature), not solved here, and is
   not claimed to be solved.

6. **Cross-engine / cross-image evidence fusion** (`evidence_fusion.py`,
   new): `classify_multi_engine()` — agreement across engines →
   CORROBORATED (confidence boosted slightly); disagreement → CONFLICTING
   (both raw values retained, confidence forced down, never averaged);
   single engine → VERIFIED; a LOW_QUALITY region caps verification at
   UNCERTAIN even when engines agree. `reconstruct_split_fields()` — scoped
   cross-image split-declaration join for `mrp`/`net_quantity`/`batch_no`
   only, only when one capture has a bare label (no digits at all: "MRP Rs"
   is eligible, "MRP Rs 1" is NOT because it already contains a number) and
   exactly one other capture in the session has a single unambiguous
   completing fragment. 8/8 unit tests pass, including the master spec's
   own worked examples verbatim: "MRP ₹" + "149.00" → reconstructs, flagged
   `UNCERTAIN`/`review_required=True`; "MRP ₹1" + unrelated fragment → left
   untouched; two competing fragments in two different images → rejected as
   ambiguous, not guessed.

7. **Barcode/product identity** (`product_identity.py`, new): pyzbar-based,
   fails closed if the native zbar library is missing. **Verified against a
   real photo**: correctly decoded the Bru coffee jar's EAN-13 barcode
   (`8909106043251`), matching the visible printed digits. Populates
   `barcode` in the `/scan` and `/sessions/{id}/captures` responses;
   never gates any legal decision (advisory only, per master spec Part 14).

8. **Real-photo OCR bug found and fixed**: the existing net-quantity
   fallback path was extracting "17m" (an artifact printed next to a
   barcode) as a net-quantity value on the Bru jar photo. Fixed by
   excluding `m`/`cm` units from the *fallback* (unlabelled) path — those
   units are legitimate only for length-declared goods (rare) and were
   overwhelmingly barcode/print noise in practice. Verified fixed on the
   real photo; no regression in the existing test suite.

9. **Real-photo MRP association bug found and fixed**: on the same Bru jar
   photo, `classify_fields()` was pairing the "MRP" label with the *wrong*
   nearby value line ("₹2.80/g", the per-gram unit price on the row below)
   instead of the correct "₹420/-" on the same row, because `_MONEY_RE`
   only recognised `₹NNN.NN` / `RsNNN.NN` shapes and a bare `.XX`-decimal
   shape — it had no pattern for the extremely common Indian whole-rupee
   shorthand `NNN/-`, and Tesseract had rendered the ₹ glyph as `=`. Added
   a third alternative to `_MONEY_RE` for `NNN/-` notation. Verified fixed
   (MRP now correctly resolves to 420.0 on this photo); full suite still
   green.

10. **Legal decision safety — dedicated regression suite**
    (`tests/test_legal_safety_invariants.py`, new, 5/5 passing): explicit,
    permanent tests for the three invariants the whole architecture depends
    on:
    - low-confidence/UNCERTAIN evidence never produces FAIL (only
      UNCERTAIN);
    - NOT_OBSERVED never produces FAIL without independently-established
      sufficient coverage (`_evidence_sufficient_for_missing_field`,
      pre-existing in `rule_engine.py` — this session added the lock-in
      tests, including the edge case that a LOW_QUALITY capture's claimed
      "coverage" must not count towards that threshold);
    - CONFLICTING evidence never silently resolves to a confident PASS/FAIL
      — tested through the **actual production code path**
      (`evidence_fusion` → `main._field_to_raw_extraction` →
      `rule_engine.run_inspection`), not the rule engine in isolation. Added
      a safety-net fix in `main._field_to_raw_extraction`: it now forces a
      CONFLICTING field's confidence below the rule engine's low-confidence
      threshold independent of whatever confidence `evidence_fusion`
      computed, so this invariant cannot regress even if fusion's confidence
      math changes later.

11. **Full API integration** (`vision_pipeline.py`, new — single shared
    pipeline, no duplicated logic): both `/scan` and
    `/sessions/{id}/captures` now run whole-image OCR + orientation-aware
    OCR + optional PaddleOCR + cross-engine fusion + region-quality capping
    + barcode decode through the same function. API responses expose
    `ocr_engine_status`, `barcode`, per-field `verification`, and
    (session endpoint) `recapture_guidance` and `reconstructed_fields`.

12. **Database plumbing — completed AND verified against a live DB.**
    `raw_ocr_lines_json` and `barcode_data` columns added to
    `session_captures` (migration follows the repo's existing idempotent
    `DO $$ ... IF NOT EXISTS ... $$` pattern — found and fixed one ordering
    bug where the new `ALTER TABLE` ran before `CREATE TABLE
    session_captures` in the file). `add_session_capture` /
    `list_session_captures` extended additively (new params default to
    `None`/empty, old call sites unaffected). Cross-image reconstruction in
    `/sessions/{id}/captures` now genuinely looks at previous captures'
    stored raw OCR lines, not just their classified fields.
    **This was actually verified, not left as "DB unavailable in sandbox"**:
    PostgreSQL 16 was installed in this sandbox (`apt-get install
    postgresql` succeeded via the environment's allowed mirrors),
    `db/schema.sql` was applied to a real database, and **the full test
    suite was run against it: 53 passed, 0 failed, 0 skipped** (previously
    10 DB-dependent tests were skipped for lack of a database). A full
    manual end-to-end run through `TestClient` — register → login → open
    session → two real Bru-jar photo captures → check coverage/guidance/
    barcode — also completed successfully.
    **Caveat for whoever resumes this**: the Postgres service does not
    persist running between separate tool invocations in this particular
    sandbox (each shell call can start fresh); the data directory itself
    persists on disk. Run `service postgresql start` before re-running
    DB-backed tests if they show as skipped again — this is a sandbox
    quirk, not a code issue.

13. **Real-photo benchmark** (`dataset/benchmark_real.py` +
    `dataset/real_photos_ground_truth.json`, both new): a small, honestly
    hand-annotated (by visually reading the photos, not fabricated) spot
    check across 6 photos / 4 distinct real products — a cylindrical coffee
    jar (2 photos, split panels), a cylindrical body-lotion bottle with
    genuinely mixed text orientation, a cylindrical large snack tube, a
    planar blister pack with **no legal declaration visible at all** (tests
    that the pipeline correctly reports NOT_OBSERVED everywhere rather than
    hallucinating), and a **spherical** confectionery ball (motion-blurred,
    partially cropped — tests graceful degradation on the hardest geometry
    class, which per master spec Part 3 this project explicitly does not
    try to fully solve). Fields the human annotator could not confidently
    read either (cropped, blurred) are marked `ambiguous_do_not_score` and
    excluded from scoring, per the master spec's "mark the limitation
    rather than fabricate" instruction.

    **Actual measured results** (25 fields scored, 3 skipped as
    unscoreable by a human):
    - Correct value extracted: **3 / 25**
    - Incorrect value extracted: **6 / 25** ← the number that matters most:
      these are false positives that could feed the legal engine a wrong
      value if not caught by the confidence/verification machinery above.
    - Correctly reported NOT_OBSERVED: **9 / 25**
    - Incorrectly reported NOT_OBSERVED (missed a field that was present):
      **7 / 25**
    - Barcode: 1 correct, 1 not found (the spherical candy — barcode too
      small/curved), 1 skipped (annotator couldn't confidently transcribe
      ground truth), 0 incorrect.

    **This is a 6-image spot check, not a statistically powered benchmark,
    and is reported as exactly that** — do not extrapolate a general
    accuracy percentage from it. Its value is in the specific, honest
    failure modes it surfaced (see below), not the aggregate ratio.

    One specific finding worth flagging explicitly: on the screwdriver
    blister pack, the net-quantity fallback extracted "SW-999 4PCS" (the
    product's model number + piece count from marketing text) as a
    net-quantity value. This is **not clearly a bug** — "N pieces" is a
    legitimate LMPC net-quantity declaration format for goods sold by
    count — but it is exactly the kind of ambiguous extraction that must
    reach a human reviewer rather than silently pass through, and is left
    as a documented limitation rather than "fixed" in a way that might be
    wrong in the other direction.

### Verified vs. implemented-but-unverified (explicit, per truthfulness rule)

**Verified** (real photo, live DB, or passing test in this session):
region-aware quality; recapture guidance text; evidence provenance schema;
orientation-aware OCR (Vaseline fixture); cross-engine fusion logic (unit
tests + real pipeline run); split-declaration reconstruction logic (unit
tests, including spec's own worked examples); barcode decode (real photo);
net-quantity and MRP OCR bug fixes (real photo, before/after); all three
legal-safety invariants (through the real production bridge, not just in
isolation); full DB migration and persistence layer (live Postgres, 53/53
tests); end-to-end session capture flow (manual `TestClient` run with real
photos).

**Implemented but NOT runtime-verified in this environment**:
PaddleOCR adapter (network-blocked here — code is real, untested at
runtime; verify in your deployment target); cross-image reconstruction
against genuinely disjoint front/back real photos with a true split field
(the unit tests use synthetic OcrLine fixtures for this specific scenario
because none of the 29 real photos happen to contain a genuine
label-in-one-image/value-in-another split — the logic is real and tested,
just not yet hit by a real photo case).

**Not attempted this session** (explicitly out of scope per the
"pragmatic MVP, not a research paper" instruction): tamper/reference-image
comparison work (existing `sticker_detection.py`/`product_similarity.py`
untouched, left as the documented existing capability); cylindrical/
spherical geometric unwarping (correctly punted per master spec Part 3 —
the spherical Doraemon candy photo in the benchmark demonstrates exactly
why, and the system degrades to lower confidence there rather than
guessing); ARCore/mobile client; custom model training.

### Known limitations for whoever resumes this

- `classify_fields()`'s label-to-value row association is still a
  proximity heuristic (`_candidate_value_lines`) and can mis-pair a label
  with the wrong nearby value line when a label and an unrelated value sit
  at similar row heights (two concrete real-photo instances found and
  fixed this session; more likely exist — this is a heuristic, not a
  layout parser).
- Orientation-aware OCR is classical-CV block detection (dual morphology),
  not a trained text detector; very tightly packed dense print can still
  merge into one block and not benefit from per-block rotation.
- The "N pieces" ambiguity above (count-based net-quantity vs. incidental
  marketing text) needs either a labelled-context requirement or human
  review; not resolved.
- No genuine real-photo test case yet for split-declaration reconstruction
  (see "implemented but not runtime-verified" above) - would strengthen
  confidence in that feature considerably if found/created.
- PaddleOCR's actual runtime behaviour is unknown outside this sandbox.

### Exact next actions
1. Find or create a real two-image pair with a genuine split declaration
   (e.g. deliberately photograph "MRP ₹" cut off at a frame edge, then the
   value in the next frame) to move split-reconstruction from
   "unit-tested" to "verified on a real photo".
2. Verify PaddleOCR model download in an actual target deployment
   (not this sandbox); if viable, re-run the real-photo benchmark with it
   enabled and compare against the Tesseract-only numbers above.
3. Expand the real-photo ground-truth set past 6 images/4 products for a
   statistically meaningful benchmark, using the same honest-annotation
   discipline (mark what you can't confidently read, don't guess).
4. Tamper/reference-image comparison work, once the above is stable.
