# TEST-BASELINE — LexMetra / LMPC backend

**Owner:** TEST-01 (Integration / Evaluation)
**As of commit:** `ca3d221` (branch `cursor/setup-dev-environment-aa7b`)
**Date:** 2026-09-15
**Runner:** `python -m pytest backend/tests` (Python 3.12.3, pytest 8.4.2)

This file is the **regression floor**. It records what actually passes today,
measured by running the commands below and reading their real output — not by
counting test files. Any later PR that drops a file below the pass count in the
"clean-DB baseline" column, or introduces a failure/error, **fails review**.

Every number here was produced by running the command and reading its output.
Raw logs are archived as build artifacts (`test_baseline_clean_output.log`,
`test_baseline_full_output.log`, `coverage.json`, `test_baseline_clean.xml`).

---

## Headline numbers

| Configuration | Passed | Skipped | Failed | Errored | Coverage |
|---|---|---|---|---|---|
| **Clean-DB baseline** (canonical) | **480** | **4** | **0** | **0** | **78.1%** |
| Default `.env` (demo bootstrap on, no poppler) | 469 | 15 | 0 | 0 | 76% |

Total collected: **484** tests across **32** test modules (+ 3 modules under
`backend/tests/regulatory/`).

- **Zero failures and zero errors** in both configurations.
- The two configurations differ only in *how many tests are skipped*, driven by
  environment/data availability (see "Skip classification"). No test result
  changed from pass↔fail between them.

### The two configurations, exactly

**Clean-DB baseline (canonical — reproduce this):**

```bash
# One-time: a disposable test database owned by lmpc_app
sudo -u postgres createdb -O lmpc_app lmpc_test

cd /workspace
DATABASE_URL="postgresql://lmpc_app:lmpc_dev_pw@localhost:5432/lmpc_test" \
LMPC_BOOTSTRAP_DEMO_USERS=false LMPC_DEMO_MODE=false \
LMPC_DEV_MODE=true LMPC_TEST_RESET_DB=true \
python -m pytest backend/tests -v --cov=backend
# => 480 passed, 4 skipped in ~16s
```

**Default `.env` (what a fresh `docker compose`/dev `.env` with demo mode gives):**

```bash
cd /workspace && python -m pytest backend/tests
# => 469 passed, 15 skipped in ~10s
```

Both require: PostgreSQL reachable via `DATABASE_URL`, Tesseract OCR binary,
and (for the 5 PDF read-back tests) `poppler-utils` (`pdftotext`).

---

## Per-file pass/skip (clean-DB baseline, as of `ca3d221`)

Format: `<test file>: <pass>/<skip>` (fail/error are 0 everywhere).

| Test file | pass | skip |
|---|---|---|
| `regulatory/test_amendments.py` | 3 | 0 |
| `regulatory/test_rag.py` | 3 | 0 |
| `regulatory/test_versioning.py` | 3 | 0 |
| `test_api_integration.py` | 11 | 2 |
| `test_auth.py` | 5 | 0 |
| `test_barcode_decode.py` | 16 | 2 |
| `test_bru_integration.py` | 10 | 0 |
| `test_build04_rag_runtime_integrity.py` | 4 | 0 |
| `test_build05_rule_versioning.py` | 6 | 0 |
| `test_build06_rule_version_runtime.py` | 6 | 0 |
| `test_build07_rag_publication.py` | 4 | 0 |
| `test_build08_rag_immutability.py` | 4 | 0 |
| `test_build09_amendment_publication.py` | 10 | 0 |
| `test_build10_runtime_hardening.py` | 4 | 0 |
| `test_build11_production_safety.py` | 9 | 0 |
| `test_build11_rag_safety.py` | 6 | 0 |
| `test_build11_versioning_safety.py` | 2 | 0 |
| `test_calibration.py` | 19 | 0 |
| `test_capture_session.py` | 27 | 0 |
| `test_declaration_pipeline.py` | 20 | 0 |
| `test_declaration_verification_propagation.py` | 11 | 0 |
| `test_exemption.py` | 4 | 0 |
| `test_generalized_date_association.py` | 30 | 0 |
| `test_geometry.py` | 23 | 0 |
| `test_ocr_engine.py` | 56 | 0 |
| `test_orientation.py` | 26 | 0 |
| `test_persistence_evidence.py` | 12 | 0 |
| `test_preprocess.py` | 35 | 0 |
| `test_region_detection.py` | 30 | 0 |
| `test_report_evidence.py` | 33 | 0 |
| `test_rule_engine.py` | 40 | 0 |
| `test_scan_visual_recovery_integration.py` | 2 | 0 |
| `test_visual_recovery_merge.py` | 2 | 0 |
| `test_vlm_visual_recovery.py` | 4 | 0 |
| **TOTAL** | **480** | **4** |

Under the default `.env`, the only differences are:
`test_api_integration.py` = 5/8 and `test_report_evidence.py` = 28/5
(everything else identical).

---

## Skip classification (classified, not guessed)

There are **no failing or erroring tests**. Every non-passing test is a `SKIP`,
each one deliberately guarded in the test code. Classification of the 15 skips
seen under the default `.env`:

### 1. Auth-gated integration tests — **environment (test isolation), not a bug** — 8 skips → run clean
`test_api_integration.py` (8 tests). Reason string:
> "A user already exists in this database and no known admin credentials were
> provided; run against a clean test database to exercise the auth-dependent
> test suite."

Root cause: `tests/conftest.py::db_ready` truncates all data, but the FastAPI
`startup` event then re-creates the demo users when `LMPC_BOOTSTRAP_DEMO_USERS=true`
+ `LMPC_DEV_MODE=true` (both set by the demo `.env`). The one-shot
`/auth/register` bootstrap then sees an existing user and the fixture skips.
Running with `LMPC_BOOTSTRAP_DEMO_USERS=false` against a disposable DB (the
documented intent in `conftest.py`) makes **6 of these 8 run and pass**; the
other 2 fall through to a data gate (below).

### 2. Synthetic dataset image missing — **test data, not a bug** — 2 skips
`test_api_integration.py::test_scan_full_pipeline_with_real_image` and
`::test_multi_surface_session_end_to_end`. Reason:
> "Synthetic dataset image not present in this checkout."

They require `dataset/images/prod001_compliant.png`, which this checkout does
not ship (the repo ships `dataset/real images/…` screenshots + synthetic
`dataset/annotations/annotations.json`, but not the referenced PNG). Skip even
on a clean DB. Not resolvable without generating/adding the fixture image
(`dataset/generate_dataset.py` regenerates the synthetic set).

### 3. Real-photo barcode tests — **test data path mismatch, not a bug** — 2 skips
`test_barcode_decode.py::TestRealPhotographs` (2 tests). Reason:
> "images dataset/ not present"

The test looks for `<repo>/images dataset/` or
`<repo>/DEPENDENCIES/images dataset/`. Neither exists. Note: the specific Bru
photo the test wants (`Screenshot_2026-09-06-22-06-12-38_…jpg`) **is present in
the repo** under `dataset/real images/`, just not at the path the test expects.
Left skipped rather than patched — retargeting the fixture path is a code change
outside TEST-01's report-only scope (flagged for the owner of barcode tests).

### 4. PDF read-back tests — **missing system dep, resolved** — 5 skips (default env only)
`test_report_evidence.py` (5 tests). Reason:
> "pdftotext (poppler-utils) not installed"

These render a PDF and read it back to assert on content. Installing
`poppler-utils` (`sudo apt-get install -y poppler-utils`) makes **all 5 run and
pass**. The clean-DB baseline includes poppler, so `test_report_evidence.py` is
33/0 there. This is an environment dependency that is **not** listed as required
(reportlab generates PDFs without it; only the read-back assertions need it).

---

## README factual claims — verified against what actually runs

| README claim | Verdict | Evidence |
|---|---|---|
| OCR **degrades gracefully** (returns no lines, does not crash) if the Tesseract binary is missing | ✅ Confirmed | Pointed `pytesseract.tesseract_cmd` at a non-existent path and called `ocr_extraction.run_ocr(blank_image)` → returned `[]` (empty list), no exception. |
| Real OCR (Tesseract) works end-to-end | ✅ Confirmed | Tesseract 5.3.4 installed; `test_ocr_engine.py` 56/0, `test_declaration_pipeline.py` 20/0, live `/scan` produced a verdict from a real photo. |
| Postgres persistence / DB round-trips confirmed | ✅ Confirmed | `test_persistence_evidence.py` 12/0; `test_api_integration.py` multi-surface JSONB round-trip passes on clean DB. |
| PDF report generation verified | ✅ Confirmed | `test_report_evidence.py` 33/0 with poppler (generate **and** read-back); `reportlab` renders `%PDF` output. |
| "Two real products tested end-to-end" | ⚠️ Partially confirmed | `test_bru_integration.py` 10/0 exercises the Bru product pipeline; the second product's `TestRealPhotographs` barcode assertions are **skipped** (data path mismatch, item 3). |

---

## OpenL / differential harness (planned, not yet applicable)

Per the TASK, TEST-01 owns a **differential test harness** comparing the legacy
`rule_engine.py` against RULE-01's future OpenL decision-table service
(same input → `{old_engine_result, openl_result}` → diff report).

- **No test file references OpenL today** — expected and correct at this stage.
- The harness will be built once RULE-01 lands a first working OpenL decision
  table to compare against. Until then this section is a placeholder so the
  contract is visible to RULE-01. Interface to produce:
  `fixture (ProductInspection input) → {old_engine_result, openl_result} → structured diff`.

---

## How to use this floor in review

1. Run the **clean-DB baseline** command above.
2. Compare per-file pass counts to the table.
3. A PR is a **regression** if any file's pass count drops, or if `failed`/
   `errored` becomes non-zero, or if total passes drop below **480**.
4. New tests should raise a file's floor here (update this table in the same PR).
