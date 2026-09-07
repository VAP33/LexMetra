# PROJECT_STATE.md
## SIH 2026 — PS 26034 — Legal Metrology (Packaged Commodities) Compliance Platform
### Current snapshot — see IMPLEMENTATION_STATUS.md for the detailed change log

---

## 1. What this is

"AI-powered Evidence-Backed Legal Metrology Inspection Platform." Backend-first
FastAPI service implementing: image capture -> OCR/CV evidence extraction ->
deterministic, versioned legal rule engine -> PASS/FAIL/UNCERTAIN/EXEMPT ->
persistence -> PDF report / audit trail. AI/CV never makes the legal decision;
the rule engine is the sole authority and always defaults to UNCERTAIN when
evidence is insufficient.

## 2. Architecture

```
image(s) --> OCR/CV extraction --> field-name bridge --> deterministic
rule engine (rules.json, versioned) --> PASS/FAIL/UNCERTAIN/EXEMPT
--> Postgres persistence --> PDF report / dashboard / audit trail
```

Multi-surface capture is now a first-class layer:

```
POST /sessions               -> open an InspectionSession
POST /sessions/{id}/captures -> add one SurfaceObservation (one photo),
                                 evidence is MERGED, not replaced
GET  /sessions/{id}          -> cumulative coverage + guidance
POST /sessions/{id}/finalize -> rule engine runs ONCE against the union
                                 of every surface observed
```

`NOT VISIBLE != MISSING` is enforced structurally: a required declaration
absent from every capture becomes `FAIL` only once accumulated evidence
coverage crosses 70%; below that it is `UNCERTAIN`, never a fabricated
compliance judgment.

## 3. Repository layout

```
backend/
  main.py               FastAPI app, all HTTP endpoints, request models
  config.py             env/.env-driven configuration (DB URL, JWT secret, CORS, storage)
  auth.py               bcrypt hashing, JWT issue/verify, RBAC dependencies
  schema.py             shared Pydantic contract (ProductInspection, SurfaceObservation, ...)
  rule_engine.py         deterministic legal engine, reads rules/rules.json
  exemption.py           Rule 3 scope/exemption classifier
  unit_price.py          Rule 6(11) unit-sale-price calculator (Decimal-exact)
  ocr_extraction.py      Tesseract OCR + regex field classifier
  ocr_engines.py          multi-engine OCR abstraction (Tesseract + optional PaddleOCR, fail-closed)
  orientation_ocr.py      per-region rotation-aware OCR (NOT whole-image rotation)
  evidence_fusion.py      cross-engine agreement/conflict + scoped cross-image split-field reconstruction
  vision_pipeline.py      single shared vision pipeline used by /scan and /sessions/{id}/captures
  product_identity.py     barcode/QR decode (pyzbar), advisory only
  capture_session.py     multi-surface merge / coverage / guidance logic
  image_quality.py       blur/exposure/glare heuristics + PDP bbox estimate + region-aware quality/recapture guidance
  sticker_detection.py   classical-CV tamper/sticker advisory flag
  product_similarity.py  pHash + histogram visual similarity (flat JSON index)
  vlm_verifier.py        optional Claude-based ambiguity check (advisory only, gated)
  report.py              PDF report generation (reportlab)
  db/
    schema.sql           full schema incl. users, audit_log, sessions, captures
    persistence.py       psycopg2 data access layer
  tests/                 pytest suite (unit + live-API integration)
  Dockerfile
  .env.example
docker-compose.yml       backend + Postgres 16
rules/rules.json         versioned legal rule dataset (source of legal truth)
dataset/                 50 synthetic label images + annotations, PLUS
                         dataset/real_photos/ (29 real user-supplied phone
                         photos) + real_photos_ground_truth.json (honest
                         hand-annotated spot check) + benchmark_real.py
frontend/                static dashboard.html / capture.html (legacy, single-image, no auth wiring)
```

## 4. Component status

| Component | Status |
|---|---|
| FastAPI backend | Working. All endpoints below verified live against a real Postgres 16 instance. |
| Authentication / RBAC | Working. JWT + bcrypt, 3 roles (inspector/reviewer/admin), bootstrap-first-admin flow. |
| Audit trail | Working. Append-only `audit_log`, admin-only read. |
| OCR (Tesseract, primary) | Working. Multi-engine fusion layer added (`evidence_fusion.py`) — agreement/conflict tracked via `EvidenceVerification`, never silently averaged. Orientation-aware pass recovers rotated/sideways text (verified on a real photo). **Real-world accuracy measured, not assumed**: small honest 6-photo/4-product spot check (see IMPLEMENTATION_STATUS.md Session 2) found 3/25 scored fields correct, 6/25 incorrect, 9/25 correctly NOT_OBSERVED, 7/25 incorrectly NOT_OBSERVED. This is a small spot check, not a statistical benchmark — reported as exactly that, not extrapolated. |
| OCR (PaddleOCR, optional second engine) | Implemented (`ocr_engines.py`), gated behind `OCR_ENABLE_PADDLE`, fails closed. **Verified BLOCKED in this sandbox**: its model host (`paddleocr.bj.bcebos.com`) returned a proxy 403 on direct probe. Untested at runtime anywhere — verify in your actual deployment before relying on it. |
| Barcode/product identity | Working (new). `product_identity.py`, pyzbar-based, fails closed, advisory only. Verified against a real photo (correct EAN-13 decode). |
| Field-name bridge | Working, single source of truth (`capture_session.bridge_classified_fields`), used identically by `/scan`, `/inspect`, and session finalize. |
| Rule engine | Working. Rule 3 (scope/exemption), Rule 6 (retail declarations), Rule 6(11) (unit price), Rule 7(2) (font height, needs calibrated input), Rule 8 (placement), Rule 24 (wholesale, new) have evaluators. Rules 4, 5, 25, 26(b), 26(c), 27, 31 have data in `rules.json` but no evaluator yet. |
| Multi-surface capture sessions | Working. Evidence-merge, coverage, guidance, and finalize verified end-to-end including a genuine FAIL produced from sufficient multi-surface evidence. Now also carries region-aware recapture guidance, per-field `verification` status, barcode, and scoped cross-image split-declaration reconstruction (unit-tested against the spec's own worked examples; not yet hit by a real photo with a genuine split field — see IMPLEMENTATION_STATUS.md). |
| Legal decision safety | Working, and now has a **dedicated regression suite** (`tests/test_legal_safety_invariants.py`) locking in: UNCERTAIN never→FAIL, NOT_OBSERVED never→FAIL without sufficient coverage, CONFLICTING never silently→PASS/FAIL — tested through the real `evidence_fusion → main.py → rule_engine` bridge, not just the rule engine in isolation. |
| Evidence retention | Working (new). Uploaded images saved to disk (UUID-prefixed filenames), path recorded on the inspection. |
| PDF reports | Working (new). `reportlab`-based, includes mandatory disclaimer. |
| Database | Working. Postgres 16, idempotent schema migrations, `users` / `audit_log` / `inspection_sessions` / `session_captures` tables added this session. |
| Tests | Working. 53 tests, 0 skipped, unit + live-API integration, verified against a real, freshly-installed Postgres 16 instance in this session. |
| VLM advisory verification | Wired into `/scan`, gated behind `VLM_VERIFICATION_ENABLED` + `ANTHROPIC_API_KEY`, fails closed / advisory-only. Not exercised against a live Anthropic API this session. |
| Sticker/tamper detection | Classical CV heuristic, advisory only, unchanged. |
| Product similarity | pHash + histogram, flat JSON index, unchanged — will not scale past a few hundred entries. |
| Docker | Dockerfile + docker-compose.yml written this session, mirrors the validated manual setup. Build itself unverified — no Docker in the dev sandbox. |
| Mobile app / ARCore / offline sync | Not started. Out of scope for this backend-hardening pass. |
| Frontend dashboard (`frontend/*.html`) | Legacy, pre-dates auth/session work. Does not send a Bearer token, so it will get 401s against the current backend until updated. Not touched this session — flagged, not fixed. |

## 5. Legal-engine coverage detail

Evaluators present: Rule 3 (scope/exemption), Rule 6 (mandatory declarations,
retail), Rule 6(11) (unit sale price), Rule 7(2) (font height — requires a
manually-calibrated `pdp_area_cm2`; otherwise conservatively UNCERTAIN),
Rule 8 (PDP placement, shallow), Rule 24 (wholesale declarations, new).

Missing evaluators (data present in `rules.json`, no code): Rule 4
(multi-pack), Rule 5 (Second Schedule standard pack), Rule 25 (export
repack), Rule 26(b) (fast food), Rule 26(c) (drug formulations), Rule 27
(registration), Rule 31 (advertisement).

Every rule threshold in `rules.json` is tagged `needs_official_verification`
or similar — none were invented. Where a check cannot be verified against an
authoritative source, the engine returns `UNCERTAIN`, never a fabricated
`PASS`/`FAIL`, per the master spec's explicit priority ("choose UNCERTAIN
over a fabricated automated PASS").

## 6. Configuration / environment requirements

- PostgreSQL 16 reachable via `DATABASE_URL` (see `backend/.env.example`).
- `JWT_SECRET_KEY` must be a real random secret in any non-dev deployment;
  the app refuses to start with the placeholder unless `LMPC_DEV_MODE=true`.
- Tesseract OCR binary must be installed on the host/container (not a pip
  package) — `apt-get install tesseract-ocr` on Debian/Ubuntu, already in
  the provided Dockerfile.
- `ALLOWED_ORIGINS` must list real frontend origins in production — never `*`
  once authentication is enabled.
- Optional: `ANTHROPIC_API_KEY` + `VLM_VERIFICATION_ENABLED=true` for the
  advisory ambiguity check.

## 7. Test / validation status

- `cd backend && python3 -m pytest tests/ -q` — **53 passed, 0 skipped**,
  verified live against a real PostgreSQL 16 instance installed in this
  session (previously 10 DB-dependent tests were skipped for lack of a
  database). Requires a reachable, disposable Postgres instance; will
  truncate all data tables in whatever database `DATABASE_URL` points to.
- `python3 dataset/benchmark_real.py` — real-photo spot check (see section
  4 and IMPLEMENTATION_STATUS.md Session 2 for the actual numbers and
  their honest caveats). Requires no database.
- No CI pipeline configured yet (no GitHub Actions workflow file).
- Manual live verification performed against a real Postgres 16 instance
  AND real (non-synthetic) product photos: full `/scan` pipeline,
  wholesale `/inspect`, RBAC boundaries, PDF report generation, review
  workflow, audit log, the full multi-surface session lifecycle, and a
  manual end-to-end `TestClient` run through `/sessions/*` with two real
  Bru-coffee-jar photos (barcode decode, coverage accumulation, recapture
  guidance all confirmed working together, not just as isolated units).

## 8. Known limitations (honest, current)

- Frontend dashboard is not wired to the new auth/session system.
- Real-world OCR accuracy has now been measured (not just "unverified") on
  a small 6-photo/4-product hand-annotated spot check — see section 4 and
  IMPLEMENTATION_STATUS.md Session 2 for the numbers. It is not yet a
  statistically powered benchmark; more real photos would meaningfully
  improve confidence in these numbers.
- `classify_fields()`'s label-to-value association is a proximity
  heuristic and can mis-pair rows on real (non-synthetic) labels — two
  concrete instances found and fixed this session on real photos; more
  likely exist.
- No trained CV models (layout detection, tamper classification, text
  detection) — all vision components remain classical-CV / heuristic, by
  design (see master spec's "no custom model training until pretrained/
  classical baseline is benchmarked" instruction).
- `product_similarity.py`'s flat JSON index will not scale past a few
  hundred products.
- Docker build is written but unverified in this environment.
- No mobile app, ARCore/depth capture, or offline/sync layer.
- Seven Legal Metrology rules remain data-only (see section 5).
- PaddleOCR is implemented but verified BLOCKED in this sandbox (model
  host unreachable) — untested at runtime anywhere.
- Tamper/reference-image comparison work was not touched this session
  (existing `sticker_detection.py`/`product_similarity.py` heuristics
  remain as they were) — deliberately deprioritized per instruction to
  finish the core pipeline first.

## 9. Immediate priorities

1. Find or create a real two-image pair with a genuine split declaration
   to move split-field reconstruction from "unit-tested against the spec's
   worked examples" to "verified on a real photo".
2. Verify PaddleOCR model download in an actual (non-sandboxed) deployment
   target; if viable, re-run `dataset/benchmark_real.py` with it enabled
   and compare against the Tesseract-only numbers already recorded.
3. Expand the real-photo ground-truth set past 6 images for a
   statistically meaningful benchmark.
4. Verify the Docker build in an environment that has Docker.
5. Update or replace `frontend/*.html` to use the auth/session APIs, or
   build a minimal guided-capture web client against `/sessions/*` — this
   is now more valuable than before, since the API surface it would drive
   (recapture guidance, per-field verification, barcode) is richer.
6. Implement the Rule 25 (export) evaluator (unchanged priority from
   Session 1).
7. Tamper/reference-image comparison, once the above is stable.
