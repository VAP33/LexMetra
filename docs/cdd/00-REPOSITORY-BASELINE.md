# 00 — Repository Baseline (LexMetra)

**Owner:** ARCH-01 (Architecture / Integration Lead)
**Status:** FROZEN baseline for Wave 1+. Amendments to this document go through ARCH-01.
**Repo:** github.com/prc7558/LexMetra @ `main`, single commit `ccd795c` ("added docs & dataset")
**Last updated:** 2026-09-15
**Method:** Source read directly (endpoints, models, and entrypoints grepped from code, not inferred from filenames), per CDD Instructions §3.

> This is the formal expansion of `CDD-STAGE1-ASSESSMENT.md` into the durable
> baseline every other agent builds against. Where Stage 1 assessed and
> recommended, this document *freezes*. The one section still pending external
> input is the test baseline (§6), which TEST-01 owns and reports; ARCH-01 folds
> the real numbers in once `docs/cdd/TEST-BASELINE.md` lands.

---

## 1. What this baseline is for

Every Wave 1+ agent starts from a fresh context and cannot trust memory,
the README's claims, or the vision document as a description of *what exists
today*. This file is the single agreed-upon answer to "what is actually in the
repo right now, and which parts are safe to depend on." If a statement is not in
this file (or in the contracts doc `01-CONTRACTS.md`), treat it as unverified.

Verification vocabulary used below:

- **VERIFIED_WORKING** — read in source and/or confirmed by a run; safe to depend on.
- **WORKING_BUT_UNVERIFIED** — code exists and appears functional but has not been
  validated against an authoritative source or a fresh test run in this pass.
- **PARTIAL** — works for some inputs, degrades or is incomplete for others.
- **MISSING** — not present in the codebase at all.
- **NON-CORE / SCOPE REVIEW** — present in the tree but not wired into the running app.

---

## 2. Current architecture (verified)

A **single FastAPI modular monolith** (`backend/main.py`) fronted by static HTML
plus an early React app, backed by Postgres + Redis, deployed via Docker Compose.
The modular-monolith shape is intentional and matches the target architecture —
this is an *additive* program, not a rewrite.

| Concern | Vision target | Repo reality today | Status |
|---|---|---|---|
| Rule engine | OpenL Tablets | Hand-written `backend/rule_engine.py` (~96K), evidence-first PASS/FAIL/UNCERTAIN/EXEMPT | WORKING_BUT_UNVERIFIED |
| CV / layout | YOLO | `backend/region_detection.py` (~60K) classical OpenCV heuristics, documented as *not* a trained detector | PARTIAL |
| OCR | PaddleOCR + Tesseract fusion | Tesseract only; PaddleOCR commented out in `requirements.txt` | PARTIAL |
| Multilingual OCR | EN/HI/MR | English only (`tesseract-ocr-eng`) | PARTIAL |
| Legal RAG retrieval | BGE-M3 + pgvector + hybrid + rerank | TF-IDF/BM25 hybrid (`sklearn`); no embeddings, no pgvector | PARTIAL (retrieval), MISSING (semantic) |
| Rule versioning/governance | via OpenL | `backend/regulatory/` + `backend/rag/publication.py`; immutable, effective-dated | VERIFIED_WORKING |
| Amendment workflow | Gazette→OCR→diff→approval→OpenL | `backend/amendments.py` state machine (`DRAFT→…→APPROVED→SCHEDULED`; `ACTIVE` not auto-reachable) | VERIFIED_WORKING (governance), PARTIAL (OCR→diff e2e) |
| Auth / RBAC | RBAC | JWT + bcrypt, 3-tier (inspector/reviewer/admin), bootstrap-admin | VERIFIED_WORKING |
| Audit trail | Required | Append-only `audit_log` table; logging never breaks the pipeline | VERIFIED_WORKING |
| Tamper detection | CV anomaly pipeline | `backend/sticker_detection.py` classical CV, advisory-only (USP4) | WORKING_BUT_UNVERIFIED |
| FSSAI cross-verification | Parallel rule domain | Absent | MISSING |
| Consumer ecosystem | Scan/report/track | Absent | MISSING |
| Authority case management | Queue/assign/resolve | Absent | MISSING |
| Analytics / intelligence | Trends, clustering | Absent | MISSING |
| Voice / IndicTrans2 | Multilingual assistant | Absent | MISSING |
| Frontend | Gov-oriented multilingual UI | `frontend/react-app/` is the Inspector surface (Scan / History / Review Queue parity with `dashboard.html`). `frontend/dashboard.html` is **FROZEN** (no new features, not deleted). `frontend/capture.html` stays a separate calibrated-capture tool. | React: WORKING_BUT_UNVERIFIED (tsc+vite build green 2026-09-16; live API round-trip blocked — backend not running). dashboard: FROZEN reference |
| Deployment | Docker | Complete `docker-compose.yml` (Postgres 16, Redis 7, backend + healthchecks) | VERIFIED_WORKING |

---

## 3. Repository reality report

| Item | Status |
|---|---|
| FastAPI backend, ~20 real endpoints | VERIFIED_WORKING (grepped from `main.py`/`router.py`) |
| Postgres persistence (users, audit_log, inspections, …) | VERIFIED_WORKING |
| JWT auth + 3-tier RBAC | VERIFIED_WORKING |
| Audit logging | VERIFIED_WORKING |
| Rule engine (custom, not OpenL) | WORKING_BUT_UNVERIFIED against primary legal sources — every rule carries `needs_official_verification` |
| OCR (Tesseract + heuristic repair) | PARTIAL — degrades on poor prints |
| Sticker/tamper detection | WORKING_BUT_UNVERIFIED (heuristic baseline, no trained classifier) |
| RAG chunking / immutability / publication governance | VERIFIED_WORKING |
| RAG semantic retrieval | MISSING (BM25/TF-IDF only) |
| Amendment lifecycle state machine | VERIFIED_WORKING |
| Amendment OCR→diff end-to-end | PARTIAL |
| Docker Compose (Postgres+Redis+backend) | VERIFIED_WORKING |
| React frontend | WORKING_BUT_UNVERIFIED — `npm run build` (`tsc && vite build`) succeeded 2026-09-16; login screen verified in browser against the built preview. Authenticated Scan/Inspections/Review flows not live-checked (backend was down). |
| Static dashboard | **FROZEN** (ARCH-01 D-02 + FE-01 parity). Do not add features. Do not delete until EVID-01 and other Wave 1 agents confirm they no longer need it as a reference. |
| OpenL Tablets / YOLO / pgvector / BGE-M3 | MISSING entirely |
| FSSAI / Consumer / Authority / Analytics / Voice | MISSING entirely |
| `DEPENDENCIES/` tree | NON-CORE — see §7 and `02-DEPENDENCIES-CLASSIFICATION.md` |
| Test suite (`backend/tests/`, ~33 files) | NOT YET RUN in a recorded pass — see §6, owned by TEST-01 |

---

## 4. Key facts every agent must carry forward accurately

1. **OpenL Tablets is a JVM application, not a Python library.** It ships as a
   Docker image (`openltablets/ws`) exposing Excel decision tables as REST/SOAP
   services. The FastAPI backend calls it **over HTTP**. There is no
   `pip install openl` path. Do not let any agent assume otherwise.
2. **The custom `rule_engine.py` is not being deleted.** It is the reference
   implementation for differential testing (see `DECISIONS.md` D-2026-09-15-01
   and CDD Instructions' differential-testing requirement) and remains the
   parity baseline OpenL must match rule-by-rule before cutover.
3. **The canonical pipeline contract is `backend/schema.py`** (`ExtractedFact` /
   `ProductInspection` and their nested models). OCR, CV, rule engine, DB,
   report generation, and frontend all import from here. Field changes require
   ARCH-01 sign-off. See `01-CONTRACTS.md`.
4. **The regulatory domain models are canonical in `backend/models.py`**,
   re-exported through `backend/regulatory/models.py`. `RegulatoryContext`,
   `RuleVersion`, `RegulatoryFinding`, `KnowledgeChunk` etc. live there. Do not
   invent a second `RegulatoryContext`.
5. **Rules carry `verification_status: "needs_official_verification"`.** This is
   a legal-accuracy risk requiring a human legal reviewer against gazette text;
   no coding subagent resolves it.

---

## 5. Major gaps (ranked by blast radius)

1. **Rule engine is not OpenL.** Largest gap. Now a *decided migration* (OpenL
   mandatory) rather than an open question — see `DECISIONS.md`.
2. **No semantic/vector retrieval.** BM25/TF-IDF only; blocks Tier C RAG claims.
3. **No trained CV / YOLO.** Classical CV is an honest MVP fallback; caps accuracy on degraded prints.
4. **Consumer + Authority ecosystems unbuilt.** ~half the product vision (USP 6/7/8), zero code.
5. **Frontend split across two Inspector surfaces.** Now *decided and executed at the React layer*: React app is the surface to build on; `dashboard.html` is **frozen-not-deleted** (FE-01, 2026-09-16). `capture.html` remains out of FE-01 scope (calibrated mm capture, not the review dashboard).
6. **Repo hygiene:** `DEPENDENCIES/` is non-core and should be archived out of the working tree — see §7.

---

## 6. Test baseline (PENDING — owned by TEST-01)

> ARCH-01 deliberately does **not** assert a pass/fail count here. The 33 files
> under `backend/tests/` tell us nothing about pass/fail until run. TEST-01's
> first Wave 0 action is `cd backend && pip install -r requirements.txt &&
> pytest -v --tb=short` with real counts recorded in `docs/cdd/TEST-BASELINE.md`.
> Once that lands, ARCH-01 folds the summary numbers into this section and the
> baseline commit hash becomes the regression floor referenced by DEVOPS-01's CI.

**Placeholder — replace with TEST-01 numbers:**

| Metric | Value | As of commit |
|---|---|---|
| Tests passed | _pending TEST-01_ | `ccd795c` |
| Tests failed | _pending TEST-01_ | `ccd795c` |
| Tests errored | _pending TEST-01_ | `ccd795c` |
| Coverage % | _pending TEST-01_ | `ccd795c` |

---

## 7. `DEPENDENCIES/` classification (summary)

Full classification and the archiving instruction for DEVOPS-01 are in
`02-DEPENDENCIES-CLASSIFICATION.md`. Summary: the entire `DEPENDENCIES/` tree is
**non-core / archive** (an earlier `LMPC-Compliance-Platform` snapshot, a zip of
the same, `apply_scripts/` past-patch appliers, a `need fixing/` staging folder,
loose docs, and a diff patch). None of it is wired into the running app.
Instruction: **archive, do not delete.**

---

## 8. Contract & document index

| Document | Owner | Purpose |
|---|---|---|
| `00-REPOSITORY-BASELINE.md` (this) | ARCH-01 | Frozen "what exists" |
| `01-CONTRACTS.md` | ARCH-01 | Canonical pipeline contract + RuleSet Resolver → OpenL contract |
| `02-DEPENDENCIES-CLASSIFICATION.md` | ARCH-01 → DEVOPS-01 | Classification + archiving instruction |
| `AGENT-EXECUTION-GUIDE.md` | ARCH-01 | How every agent runs under CDD (roles, waves, DoD, PR gates) |
| `TEST-BASELINE.md` | TEST-01 | Real pass/fail floor |
| `agents/ARCH-01/{STATE,WORKLOG,DECISIONS,HANDOFF}.md` | ARCH-01 | Per-agent working state |
| `agents/FE-01/{STATE,WORKLOG,DECISIONS,HANDOFF}.md` | FE-01 | Inspector React consolidation |

---

## Amendment — 2026-09-16 (FE-01, coordinated with ARCH-01 D-02)

`frontend/react-app/` is now the Inspector surface. Feature parity with the
three `dashboard.html` tabs (Scan, Inspections, Review Queue) is implemented
in React; `dashboard.html` is **frozen** (no new features) and **not deleted**.
EVID-01 should extend `frontend/react-app/src/components/evidence/EvidenceView.tsx`.
`frontend/capture.html` is intentionally left separate.

ARCH-01: fold this amendment into the frozen voice of this document when you
next revise it. FE-01 did not change any pipeline contract.

---

*Baseline authored by ARCH-01 as the Stage 2 deliverable. Section 6 is owned
by TEST-01 (`TEST-BASELINE.md` now exists). Frontend status updated by FE-01
on 2026-09-16.*
