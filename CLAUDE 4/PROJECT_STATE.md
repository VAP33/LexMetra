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
  capture_session.py     multi-surface merge / coverage / guidance logic
  image_quality.py       blur/exposure/glare heuristics + PDP bbox estimate
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
dataset/                 50 synthetic label images + annotations
frontend/                static dashboard.html / capture.html (legacy, single-image, no auth wiring)
```

## 4. Component status

| Component | Status |
|---|---|
| FastAPI backend | Working. All endpoints below verified live against a real Postgres 16 instance. |
| Authentication / RBAC | Working. JWT + bcrypt, 3 roles (inspector/reviewer/admin), bootstrap-first-admin flow. |
| Audit trail | Working. Append-only `audit_log`, admin-only read. |
| OCR (Tesseract) | Working on synthetic/clean labels; degrades gracefully (empty evidence, not a crash) if the binary is missing. Real-world label accuracy unverified — no trained layout model. |
| Field-name bridge | Working, single source of truth (`capture_session.bridge_classified_fields`), used identically by `/scan`, `/inspect`, and session finalize. |
| Rule engine | Working. Rule 3 (scope/exemption), Rule 6 (retail declarations), Rule 6(11) (unit price), Rule 7(2) (font height, needs calibrated input), Rule 8 (placement), Rule 24 (wholesale, new) have evaluators. Rules 4, 5, 25, 26(b), 26(c), 27, 31 have data in `rules.json` but no evaluator yet. |
| Multi-surface capture sessions | Working (new). Evidence-merge, coverage, guidance, and finalize verified end-to-end including a genuine FAIL produced from sufficient multi-surface evidence. |
| Evidence retention | Working (new). Uploaded images saved to disk (UUID-prefixed filenames), path recorded on the inspection. |
| PDF reports | Working (new). `reportlab`-based, includes mandatory disclaimer. |
| Database | Working. Postgres 16, idempotent schema migrations, `users` / `audit_log` / `inspection_sessions` / `session_captures` tables added this session. |
| Tests | Working (new). 34 tests, 0 skipped, unit + live-API integration. Self-cleaning against a disposable dev/test DB. |
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

- `cd backend && python3 -m pytest tests/ -q` — 34 passed, 0 skipped
  (verified live). Requires a reachable, disposable Postgres instance;
  will truncate all data tables in whatever database `DATABASE_URL`
  points to (`LMPC_TEST_RESET_DB=false` to disable — not recommended, tests
  assume a clean slate).
- No CI pipeline configured yet (no GitHub Actions workflow file).
- Manual live verification performed this session against a real Postgres
  16 instance and real synthetic-dataset images: full `/scan` pipeline,
  wholesale `/inspect`, RBAC boundaries, PDF report generation, review
  workflow, audit log, and the full multi-surface session lifecycle
  (create -> capture x2 -> status -> finalize -> reject double-finalize).

## 8. Known limitations (honest, current)

- Frontend dashboard is not wired to the new auth/session system.
- No real-world product photo dataset; OCR accuracy on messy real labels is
  unverified.
- No trained CV models (layout detection, tamper classification) — both
  remain classical-heuristic / advisory only, as they always have been.
- `product_similarity.py`'s flat JSON index will not scale past a few
  hundred products.
- Docker build is written but unverified in this environment.
- No mobile app, ARCore/depth capture, or offline/sync layer — the backend
  now has the multi-surface API a mobile client would need, but no client
  exists yet.
- Seven Legal Metrology rules remain data-only (see section 5).

## 9. Immediate priorities

1. Verify the Docker build in an environment that has Docker.
2. Build a genuine two-surface synthetic test fixture to properly exercise
   disjoint-evidence coverage math (current dataset only supports
   same-product-different-photo merge testing).
3. Update or replace `frontend/*.html` to use the auth/session APIs, or
   build a minimal guided-capture web client against `/sessions/*`.
4. Implement the Rule 25 (export) evaluator — the exemption engine already
   has explicit comments flagging this as the next required piece.
5. Real product photo collection remains the single highest-impact,
   non-automatable next step for demo credibility.
