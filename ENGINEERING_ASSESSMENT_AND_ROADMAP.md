# SIH 2026 · PS 26034 — Engineering Assessment, Gap Register and Production Methodology

**Project:** Software system to check compliance of packaged commodities under the Legal Metrology (Packaged Commodities) Rules, 2011.
**Repository:** `C:\Users\HP\SIH 2026` · branch `main` · last commit `43ad34f`
**Assessment date:** 2026-09-08
**Author:** primary development agent, from direct inspection and execution of the code — not from the existing status documents.

This document is written to be handed to other engineers or coding models. It states what is solid, what is fragile, what does not exist yet, and the exact method to close each gap. Every claim is labelled with how strongly it is established.

---

## 0. How to read this document

The single most common way a project like this fails its evaluation is by conflating five different things. Throughout this document these words mean exactly this and nothing more:

| Label | Meaning |
|---|---|
| **IMPLEMENTED** | Code exists and imports cleanly. Nothing more is claimed. |
| **TESTED** | Automated tests exercise it and pass, and the tests have been shown to fail when the behaviour is broken. |
| **END-TO-END VERIFIED** | The real path was executed — real process, real I/O, real database, real HTTP — and observed to work. |
| **DEMO READY** | A human has driven the actual user workflow start to finish without hand-editing data. |
| **PRODUCTION READY** | Above, plus security review, migrations, backups, monitoring, load behaviour and legal sign-off. |

**Nothing in this repository is PRODUCTION READY today, and nothing is DEMO READY today.** The legal core is genuinely strong and well tested. The delivery shell around it — HTTP, database, frontend — has never been executed even once. That is the honest headline, and section 2 explains why.

A second discipline matters just as much. This codebase's characteristic defect is not the crash; it is the **plausible-looking wrong answer**. Four separate defects fixed in Session 4 all produced valid PDFs, well-formed database rows and normal-looking findings while being wrong. Section 6.2 gives the audit technique that finds these. Apply it before writing new features.

---

## 1. Requested answers, up front

Two questions were asked and deserve direct answers.

### 1.1 "Is the OCR module done? Are CV, assisted camera and preprocessing complete?"

**No — but they are the most advanced part of the system, and the remaining work is integration and measurement, not invention.**

| Capability | Status | The precise gap |
|---|---|---|
| Preprocessing (`preprocess.py`, 1424 lines) | **TESTED** (35 tests) | Quality-driven variants, CLAHE, glare suppression, perspective rectification, screenshot-chrome crop. Original image is preserved. The variant **ranking** is weak: on one benchmark image, moving from 3 variant slots to 2 lost 41% of characters, meaning the best variant is often not ranked first. This is the single remaining performance and accuracy lever. |
| Region detection (`region_detection.py`, 1544 lines) | **TESTED** (30 tests) | Proposes text / barcode / package-boundary / sticker / declaration-candidate regions. A detected package boundary is correctly **not** treated as PDP compliance. |
| Orientation (`orientation.py`, 523 lines) | **TESTED** (499-line test file) | Per-region orientation rather than whole-image rotation, as required. |
| OCR engine (`ocr_engine.py`, 2151 lines) | **TESTED** (1039-line test file) | Region-first, multi-variant, multi-pass, with fusion states CORROBORATED / SINGLE_SOURCE / CONFLICTING and numeric-signature agreement so `100 g` vs `700 g` can never corroborate. Wired live via `config.ENABLE_REGION_FIRST_OCR` (default on) with a legacy fallback. |
| Field extraction (`ocr_extraction.py`, 1240 lines) | **TESTED** | `run_ocr()` is the single OCR choke point for `/scan`, `/inspect` and `analyze-image`. |
| Assisted / guided camera | **IMPLEMENTED, NOT END-TO-END VERIFIED** | Server side exists: capture sessions, per-surface coverage, `guidance_messages()`, quality signals. `frontend/capture.html` exists but has never been opened against a running backend. **`recapture_guidance` computed by the OCR engine is still discarded** — see 3.1. |
| Barcode / QR decoding | **NOT IMPLEMENTED** | `pyzbar` is unavailable in the sandbox and there is no implementation. Regions are *detected* but never decoded. |
| Accuracy | **UNMEASURABLE TODAY** | There is no labelled ground-truth set. `images dataset/` has 29 real phone screenshots but no per-field labels. The 50-image set in `CLAUDE 1/dataset/` is self-declared `"synthetic": true` with an explicit "do not use as compliance evidence" note. **No accuracy figure may be quoted in any submission or demo.** |

So: OCR and CV are strong enough to move on from *as a build task*, provided you accept two conditions — barcode decoding is a known hole, and no accuracy claim is permitted until a labelled set exists. Do not treat them as closed.

### 1.2 "Are we going perfectly with the objectives?"

**Directionally yes on the hard part, and no on the demonstrable part.**

The problem statement's genuinely difficult requirement is a system that reaches a *defensible* legal conclusion rather than a plausible one. That architecture is right and is holding: AI extracts and measures, a deterministic versioned rule engine evaluates, humans resolve uncertainty. The separation is real in code, not just in the README. Evidence traceability, conservative absence handling and the refusal to let low confidence become non-compliance are all implemented and tested. That is the part most teams get wrong, and it is the part this project gets right.

Where it is not perfect:

1. **Measurement is missing from the canonical backend.** `geometry.py`, `calibration.py` and `measurement.py` do not exist in `backend/`. They exist only in the unintegrated `CLAUDE 4/` folder. Font-height compliance under Rule 7(2) is a headline requirement of the problem statement, and today it can only ever return UNCERTAIN because no verified millimetre measurement can be produced. **This is the largest functional gap against the objectives.**
2. **Only about a third of the loaded rules are actually evaluated.** `rules/rules.json` contains 19 rules; `run_inspection()` wires 5 evaluators plus scope and exemptions. The rest are data with no evaluator (section 4.3).
3. **13 of 19 rules are marked `needs_official_verification`.** The legal content has not been audited against the current amended text.
4. **Nothing has been demonstrated.** The frontend cannot authenticate, so the end-to-end story a judge would watch does not run yet.

### 1.3 A correction to the record

The master execution prompt refers to *"the ASTRA engineering audit supplied with this task."* **No such file exists anywhere in this repository.** I searched. I have not reconstructed, guessed at, or paraphrased its contents, and no finding in this document is attributed to it. If that audit matters, supply the file.

---

## 2. Ground truth about the environment — read this before trusting any test result

The development sandbox has **no network access for `pip`** (`ProxyError: Tunnel connection failed: 403 Forbidden`), no cached wheels and no usable virtualenv. Present: `python 3.10.12`, `cv2`, `numpy`, `PIL`, `pytesseract`, the `tesseract` binary, `reportlab`, `pdftotext`, `pdftoppm`, `gs`. **Absent: `fastapi`, `pydantic`, `psycopg2`, `pytest`, `pyzbar`**, and there is no PostgreSQL server.

Two shims exist so the legal core remains testable: `backend/tools/run_tests.py` (a minimal pytest replacement) and `backend/tools/pydantic_shim.py` (a deliberately strict stand-in enforcing required fields, `ge`/`le` bounds and `extra=forbid`). Both defer to the real library when importable and both print a caveat on every run.

Three consequences that must not be glossed over:

- **The current test result is `249 passed / 1 failed / 10 skipped`.** The one failure is `test_auth`, which cannot import `fastapi`. The 10 skips are `test_api_integration`, which needs a live server. These are environmental, not defects — but they are also the exact tests that would catch an integration break, so their absence is not harmless.
- **Validation semantics under test are the shim's, not pydantic's.** Re-run the suite under real pydantic before any release or accuracy claim.
- **The very first task for a machine with working networking is to install the real dependencies and re-run everything.** Until that happens, treat all HTTP and database code as unexecuted. It is unexecuted.

Additionally, **file deletion is blocked in this sandbox**, and git index operations required `GIT_INDEX_FILE=/tmp/gitindex` as a workaround. On a normal machine neither applies.

One tooling trap worth inheriting: `wc -l` piped through `xargs` returns `0 total` for the specialist folders because `xargs` splits on the space in `CLAUDE 2`. **Always quote those paths.** This nearly produced the false conclusion that the specialist work was empty.

---

## 3. Part A — What is solid

Everything in this section was established by executing code, not by reading it.

### 3.1 Evidence traceability (P0-1) — the strongest part of the system

Invariant 17 requires every legal finding to be traceable to evidence and a rule version. Session 4 found and fixed four *connected* defects, every one of which produced plausible output, which is why none had surfaced:

1. **The dropped bbox.** `main._field_to_raw_extraction` built `RawExtraction` without `bbox` or `evidence`, so `rule_engine._evidence_for_extraction` hit `if bbox is None: return []` and **every fact the API produced had `evidence == []`**. OCR had computed the geometry correctly and it was thrown away one call before it was needed. Fixed by moving the translation into `capture_session.build_raw_extraction()` — deliberately out of `main.py`, because `main.py` imports FastAPI and therefore cannot be unit tested here at all. Measured with `backend/tools/probe_evidence_chain.py`: **0 of 10 facts locatable before, 5 of 10 after**; the other 5 are declarations never observed, which correctly carry no region.
2. **The fabricated image id.** Provenance-less evidence used `image_id="unknown"`, indistinguishable from a real photograph called `unknown.jpg` once persisted. Replaced with `schema.UNATTRIBUTED_IMAGE_ID = "UNATTRIBUTED-NO-SOURCE-IMAGE"` plus `is_attributed()` / `is_locatable()`. **Principle to carry forward: a conspicuous sentinel, never a plausible placeholder.**
3. **The missing table.** There was no `inspection_findings` table at all, so every `RuleFinding` was discarded at request end. Added the DDL plus `FINDING_COLUMNS`, `build_finding_row`, `decode_json_column` and `hydrate_finding_row` in `backend/db/persistence.py`. The DDL and the code's column set were then diffed programmatically and agree exactly.
4. **The report that claimed what it never showed.** `report.py` did `rows_source = findings if findings else facts` under a "Rule Findings" heading, with a hardcoded closing sentence asserting every row was "traceable to a versioned rule identifier" — while printing no image, no region and no rule version. Because findings were never persisted, **the fallback was the branch always taken: every report ever generated rendered extracted facts while claiming they were legal findings.** Fixed with a pure `report.build_findings_section()`, an Evidence column rendering `front_7f3a.jpg @ (120,640) 300x28px`, conspicuous disclosure when facts stand in for findings, and a closing statement *derived* from the rows rather than asserted.

Note the subtlety in "locatable": both `schema.EvidenceReference.is_locatable()` and `report._is_locatable()` require **image AND region**. A region with no source image is not weaker traceability, it is none — nobody can act on `(115,700) 420x52px` without knowing which photograph it indexes. An early version of the report's untraceable count checked only "no evidence at all", which understated the gap in precisely the case where provenance had broken. A test caught that.

Provenance is stamped **per field, before the merge**, because `capture_session.merge_classified_fields` keeps the higher-confidence reading per field — `mrp` may win from the back panel while `net_quantity` won from the front. A single request-level image id would attribute some findings to the wrong photograph, which is worse than no attribution because it sends a reviewer to an image that does not contain the text.

**Verification quality here is high.** `test_report_evidence.py` includes 5 tests that generate a real PDF and read the text back out with `pdftotext`, which found a layout defect invisible to unit tests: bare-string table header cells cannot wrap, so the extracted text read `"Rule versionStatus"` — the header had overflowed into the neighbouring column. Fixed by making header cells `Paragraph` objects.

### 3.2 The deterministic legal core

`rule_engine.py` (1574 lines, 29 tests) with `rules/rules.json` as versioned data. Genuinely good properties, all tested:

- Absence is evidence-gated. A required declaration that was not observed becomes FAIL **only** when package coverage was sufficient; otherwise UNCERTAIN. NOT_OBSERVED never silently becomes MISSING.
- Tri-state applicability: `condition_applicability()` returns APPLICABLE / NOT_APPLICABLE / APPLICABILITY_UNKNOWN. Session 3 found `_condition_is_applicable` ending in a bare `return True`, which made any unrecognised `rules.json` condition an unconditionally mandatory requirement — a route to false FAIL. UNKNOWN is still evaluated and reported but can only reach UNCERTAIN.
- A client-supplied `VERIFIED` measurement flag is downgraded to `ESTIMATED` unless a validated calibration accompanies it (`_has_validated_calibration`), satisfying invariant 8 at the contract boundary.
- Low extraction confidence produces UNCERTAIN with a reason, never non-compliance.

### 3.3 Reporting

`report.py` (450 lines, 33 tests). Its governing design rule is worth preserving verbatim in any rewrite: **the document may not assert more than it can show.** Row-level Evidence column, disclosed fact-substitution, derived closing statement, and an explicit count of findings that cannot be shown to a reviewer in context.

### 3.4 OCR fusion correctness

Session 3 found that fusion treated `"NET QUANTITY 100 g"` and `"700 g"` as CORROBORATED **with a confidence bonus**, because character similarity was 0.9333 against a 0.86 threshold — one wrong digit barely moves a ratio. Fixed with `numeric_signature()` / `readings_agree()`: agreement now additionally requires identical ordered digit runs. **Numeric disagreement is always CONFLICTING and is never auto-resolved.**

### 3.5 Invariant 4, closed this session

Invariant 4 says CONFLICTING evidence cannot automatically produce a definitive compliance finding. It was **unimplemented** — the words "conflict" and "fusion" appeared zero times in both `rule_engine.py` and `schema.py`. The OCR engine computed conflict state and then destroyed it: `run_ocr()` returned only `ImageReading.lines`, which reduced every observation to `(text, bbox, confidence)`, discarding `fusion_state`, `alternatives`, `corroborated_by`, `region_id`, and — at the `ImageReading` level — `conflicts` and `recapture_guidance` entirely. Same defect class as the dropped bbox: computed richly, discarded at the join.

Demonstrated concretely before fixing: an MRP that the engine had read both as `Rs. 50.00` and `Rs. 90.00` from the same pixels produced a **definitive PASS fact at confidence 0.90**, with no trace of the disagreement anywhere downstream.

The fix, now verified end to end:

- `schema.EvidenceAgreement` (CORROBORATED / SINGLE_SOURCE / CONFLICTING / **AGREEMENT_UNKNOWN**) with member names and values identical to `ocr_engine.FusionState`, so there is one vocabulary rather than two that must be kept in step. `coerce_evidence_agreement()` maps an unrecognised value to AGREEMENT_UNKNOWN, never to SINGLE_SOURCE — defaulting to SINGLE_SOURCE would convert "we could not tell whether the readings agreed" into the positive claim "there was no disagreement".
- `OcrLine` gained `fusion_state`, `alternatives`, `region_id`, carried as plain strings so the import graph stays acyclic.
- `ocr_extraction.attach_reading_agreement()` attributes agreement per field in **one** place rather than at the 13 sites that build classified-field dicts. The attribution is exact, not heuristic: all 13 sites store some line's `.bbox` verbatim, never a merged box, so the field's region identifies the reading that supplied its value. A field whose region matches no line becomes AGREEMENT_UNKNOWN, so a future site that starts storing a computed region fails safe and loudly.
- `RawExtraction` gained `agreement` and `alternative_values`; `capture_session.build_raw_extraction` forwards them.
- `rule_engine.agreement_cap()` refuses a definitive verdict, applied inside `_make_fact` — the choke point every fact passes through, so evaluators not yet written inherit it. It caps PASS **and FAIL**: accusing a package of a breach on a reading the pipeline could not settle is the worst available outcome, worse than the false PASS. It only ever downgrades; nothing here can promote a verdict.
- `_finding()` now takes `fact=` and derives status, reason and review flag from it, so a capped fact cannot sit beside a finding still claiming PASS. Only 5 of the 18 call sites pass a variable status and needed this; the other 13 pass literal UNCERTAIN or EXEMPT, which the cap provably never alters.

Measured result of the full chain (`OCR fusion_state → RawExtraction.agreement → verdict`):

```
CORROBORATED   -> CORROBORATED      -> PASS      review=False
None (legacy)  -> SINGLE_SOURCE     -> PASS      review=False
CONFLICTING    -> CONFLICTING       -> UNCERTAIN review=True
"garbage"      -> AGREEMENT_UNKNOWN -> UNCERTAIN review=True
```

The reviewer is shown the actual competing readings, not merely told a conflict exists. Full suite still `249 passed / 1 failed / 10 skipped` — no regressions.

**Two caveats, stated plainly.** This work is **uncommitted**, and **no new tests cover it** — the 249 passing tests are the pre-existing ones. See section 7.

---

## 4. Part B and C — Gap register

Ordered by risk to the objectives. "Attention" and "remaining" are merged because the distinction is arbitrary in practice: an unverified subsystem and a missing one carry the same demo risk.

### 4.1 BLOCKER — the delivery shell has never executed

| # | Gap | Evidence | Risk |
|---|---|---|---|
| B1 | **`main.py` (1235 lines, 18 endpoints) has never run.** | `fastapi` not installable in sandbox; `test_auth` fails on import; `test_api_integration` all 10 skipped. | Any of the 18 endpoints could fail on first contact. Request/response wiring, dependency injection and the 16 role guards are all unexecuted. |
| B2 | **No database round trip has ever occurred.** | No `psycopg2`, no PostgreSQL server. `persistence.py` and `schema.sql` agree only by programmatic column diff. | A type mismatch or constraint violation would appear only at runtime. Note the failure mode a unit test structurally cannot see: code and DDL agreeing with each other while both disagree with the actual database. |
| B3 | **`frontend/dashboard.html` sends no `Authorization` header.** Confirmed: zero occurrences of the string. | Every call 401s against the secured backend. | The demo does not run. This is the shortest path from "nothing works" to "something works". |
| B4 | **No `.env.example`, absent from repo root.** | The mandate requires it explicitly. | Secrets discipline is unverified. Audit for hardcoded credentials before any commit is shared. |
| B5 | **Docker never built.** Only `backend/Dockerfile`; `docker-compose.yml` at root references services never started. | Deployment claim is unsupported. |

### 4.2 HIGH — missing capability against the problem statement

| # | Gap | Detail |
|---|---|---|
| C1 | **Geometry / calibration / measurement absent from `backend/`.** | Only in `CLAUDE 4/` (2.1M): `geometry.py` (33K), `calibration.py` (18.8K), `GEOMETRY_MODULE_NOTES.md` (17K), plus tests. Without it, Rule 7(2) font height can only ever be UNCERTAIN. Required logic on integration: `NO VALID CALIBRATION → ESTIMATED/UNCERTAIN`; only `VALIDATED CALIBRATION + VALID GEOMETRY + VALID MEASUREMENT → VERIFIED`. |
| C2 | **Barcode / QR never decoded.** | Regions detected, no decoder. `pyzbar` unavailable here. Needed for product identity and for the e-commerce/Rule 6(10) story. |
| C3 | **`recapture_guidance` and `conflicts` still discarded at the OCR boundary.** | `run_ocr()` returns `List[OcrLine]`, so `ImageReading.recapture_guidance`, `.conflicts`, `.region_readings`, `.engines_used`, `.detection` are lost. Invariant 18 requires RECAPTURE to be a reachable outcome; today the engine computes the guidance and nobody receives it. Per-field agreement now survives; image-level guidance does not. |
| C4 | **No labelled ground truth.** | `usable_chars` in `bench_ocr.py` is a regression proxy only. Blocks every accuracy claim. |

### 4.3 HIGH — legal coverage

`rules/rules.json` holds 19 rules, but `run_inspection()` wires only **5 evaluators** — Rule 6 declarations, Rule 24 wholesale, Rule 7(2) font height, Rule 6(11) unit price, Rule 8 placement — plus scope (Rule 3) and `exemption.py`. The following are **data without an evaluator**: Rule 4 (multipack), Rule 5 (standard pack sizes / Second Schedule), Rule 26(b) fast food, Rule 26(c) drug formulations, Rule 27 (registration), Rule 31 (advertisement), Rule 32 (penalty), Schedule II. Rules 25 and 26 are partially reached through `exemption.py`.

Separately: **13 of 19 rules carry `verification_status: needs_official_verification`**, and `rules.json` has **no top-level version field** (it returns `None`). Per-rule versions exist and are cited in findings, but the rule *set* is unversioned, which weakens invariant 17 — a finding can name the rule version it used but not the rule-set revision.

**Do not fabricate legal sources when closing this.** Cite the actual amended text or leave the status as unverified.

### 4.4 MEDIUM — quality of enforcement

| # | Gap | Detail |
|---|---|---|
| D1 | **The invariant-4 work has no tests.** | The cap is enforced structurally but unverified by the suite. Highest-priority test debt in the repo. |
| D2 | **The AST drift-guard was designed but not written.** | The rule "every `_finding()` call whose status is not a literal UNCERTAIN/EXEMPT must pass `fact=`" is currently only documented in a docstring. Until the test exists, a new evaluator can silently bypass the cap. |
| D3 | **The low-confidence check is duplicated across ~10 sites.** | `if extraction.confidence < low_confidence_threshold` appears at roughly ten call sites. A rule enforced in ten places is a rule that will one day be enforced in nine. Should be consolidated into `_make_fact` the way `agreement_cap` was. |
| D4 | **Tests run under shims.** | Re-run under real `pytest` + real `pydantic`. |
| D5 | **Performance: ~24s per 2392×1080 image.** | cProfile: 22.62s of 26.17s in 14 Tesseract subprocess calls at 1.615s each — **94% is subprocess latency**. Read-set dedup and `READ_TILE_MAX_SIDE_PX` are *ruled out by measurement*. The only remaining lever is variant **ranking** quality. |
| D6 | **Specialist folders unintegrated.** | `CLAUDE 1/` 1.9M, `CLAUDE 2/` 32M, `CLAUDE 4/` 2.1M. Gitignored deliberately so three competing `rule_engine.py` / `ocr_extraction.py` / `schema.py` do not enter the repo. Not deleted. |

### 4.5 A negative result — do not re-attempt

**De-duplicating overlapping OCR read-sets looks like a free 36% speedup. It is not.** It costs up to 27% of characters *and* destroys the only source of CORROBORATED / CONFLICTING evidence within a single image — which, after this session's work, is now load-bearing for invariant 4. Documented above `select_regions_to_read()` and guarded by a regression test. Anyone proposing this optimisation should read that comment first.

---

## 5. Part D — The methodology

This section is the part worth keeping. The gaps above will change; the method should not.

### 5.1 The prime directive

> AI extracts and measures evidence. A deterministic, versioned legal rule engine evaluates applicable requirements. Humans resolve uncertainty.

Every change must leave that separation intact. AI or VLM output must never reach a legal verdict directly. If a proposed change makes a model's output determine PASS or FAIL, the change is wrong regardless of how much it improves a metric.

### 5.2 The silent-fallback audit — the single highest-yield technique here

Every real defect found in this codebase so far shared one shape: **a fallback that substitutes a plausible value for a missing one.** Not code that raises. Code that copes.

To audit any module, search for these and interrogate each one:

- `if X is None: return []` or `return {}` or `return default` — what did the caller lose, and will it notice?
- `A if A else B` — is `B` actually the branch always taken in production? (This is exactly how every report came to render facts while claiming they were findings.)
- `except Exception: <fall back>` — does the fallback silently downgrade evidence quality?
- `.get(key, <plausible default>)` — is the default a *claim*? `"unknown"`, `0.0`, `True`, `SINGLE_SOURCE` are all assertions dressed as defaults.
- Any string literal that could be mistaken for real data (`"unknown"`, `"N/A"`, `"default"`).

The rule that replaces them: **a conspicuous sentinel, never a plausible placeholder.** `UNATTRIBUTED-NO-SOURCE-IMAGE` and `AGREEMENT_UNKNOWN` are the two working examples. Both are impossible to mistake for real data, and both fail *safe* — they cannot produce a definitive verdict.

Ask of every join between two stages: **what did stage A compute that stage B never receives?** Both the dropped bbox and the dropped fusion state were found this way. Neither was a bug *inside* a stage.

### 5.3 Enforce invariants at choke points, never at call sites

When you must enforce a rule, find the one function every instance passes through and enforce it there. `agreement_cap` inside `_make_fact` protects evaluators nobody has written yet. The low-confidence check, spread across ten call sites, protects only the ten someone remembered.

When the plumbing genuinely must be repeated, **make omission a test failure**: walk the module's AST, find every call, assert the required argument is present. This converts remembered discipline into enforced structure. The codebase already uses this idiom for the `run_inspection` signature defaults; extend it.

### 5.4 Non-vacuity — prove the test can fail

A test that passes against broken code is worse than no test, because it produces confidence. For every safety test:

1. Reintroduce the defect (or set the field to `None`, or restore the old branch).
2. Run the test. **Confirm it fails**, and note how many tests fail.
3. Revert.
4. Record the count in the commit message or status doc.

Session 4 did this for all four defects — e.g. setting `"evidence_json": None` in `build_finding_row` fails 4 tests; restoring the old report fallback fails 4 more. Do the same for the invariant-4 cap.

Also: **do not write tests that accept PASS *or* FAIL *or* UNCERTAIN as success.** The test must assert the one correct behaviour. And do not hide skipped tests — report the skip count and the reason every time.

### 5.5 Test what cannot be reached, by extracting pure functions

When a driver is unavailable — no FastAPI, no PostgreSQL — do not conclude the logic is untestable. Move the domain logic out of the untestable module into one that imports nothing exotic, and test it there. The bbox-drop fix moved the translation out of `main.py` (which imports FastAPI) into `capture_session.py` precisely so it could be tested at all. `report.build_findings_section()` was extracted from PDF generation for the same reason. **The evidence contract is too important to be reachable only through an un-runnable module.**

Corollary: prefer verifying the *rendered artefact* when you can. `pdftotext` on a generated PDF caught a column-overflow defect that no unit test would ever have seen.

### 5.6 The specialist-folder integration protocol

Never *copy everything → overwrite canonical → hope it works*. The mandated sequence, in order, per module:

**INSPECT → COMPARE → UNDERSTAND → TEST → ADAPT → INTEGRATE → VERIFY → and only then REMOVE DUPLICATION.**

Rules that constrain it:

- **The existence of a specialist implementation is not acceptance evidence. Only verified end-to-end behaviour counts.**
- One canonical vision/evidence pipeline. Never two competing OCR paths. Do not blindly replace `ocr_extraction.py` / `ocr_engine.py`.
- Do not reduce rich OCR observations to text-only records. (This is what invariant 4's break was.)
- Do not delete a specialist folder before its useful work is verified.
- If a folder is missing or useless, implement the capability yourself. Do not wait.
- Architectural dependencies override the nominal 2 → 4 → 1 priority: evidence contracts must stabilise before final legal evaluation; geometry must satisfy the evidence and uncertainty contracts; the frontend must consume the *final* API contracts. That is why P0-1 had to land first, and why the frontend comes last despite being the most visible.

Known content: `CLAUDE 1/` self-labels most of its own backend as *"Superseded"* — only `frontend/react-app/` and `dataset/` are additive, and the dataset is synthetic. `CLAUDE 2/proj/backend/` (32M) holds `vision_pipeline.py`, `evidence_fusion.py`, `orientation_ocr.py`, `ocr_engines.py`, `live_capture.py`, `measurement.py`, `package_boundary.py`, `product_identity.py` and useful tests including `test_legal_safety_invariants.py`. `CLAUDE 4/backend/` holds the geometry and calibration work plus its own `rules/rules.json` — **do not let a second rules file into the canonical tree.**

Three equivalences to refuse, every time: package boundary ≠ PDP compliance; PDP detection ≠ legal placement compliance; an OCR text box ≠ a legally established PDP measurement.

### 5.7 Documentation and claim discipline

Use the five-level vocabulary from section 0 and never blur it. Do not write "verified" for anything you did not execute. Do not write "production ready" or "perfect" while meaningful limitations remain; use "SIH DEMO READY" only after a human has driven the whole workflow. Do not quote accuracy without a labelled set. Do not fabricate legal sources.

Report each feature in this shape: FEATURE / OBJECTIVE / IMPLEMENTED / FILES CHANGED / SPECIALIST WORK USED / TESTS ADDED / TESTS RUN (passed, failed, skipped) / END-TO-END VERIFIED / PERSISTENCE VERIFIED / USER WORKFLOW VERIFIED / KNOWN LIMITATIONS / SECURITY / LEGAL RISKS / NEXT FEATURE.

### 5.8 Repository hygiene

Inspect `git status` before major changes. Never reset or destroy unrelated work. Never blindly overwrite another agent's output. Never commit secrets. Maintain one canonical implementation per responsibility — no `ocr_v2.py`, `rule_engine_new.py`, `capture_new.py`. Keep the specialist folders gitignored until integrated.

---

## 6. Part E — Ordered work plan with acceptance criteria

Each step states the acceptance test, so a coding model can tell whether it is done. Do not advance while a step's criterion is unmet.

### Step 0 — Restore a real toolchain (blocks everything; do first)

On a machine with networking: `pip install fastapi uvicorn pydantic psycopg2-binary pytest python-jose passlib bcrypt pyzbar python-multipart reportlab`, install PostgreSQL 16, install Tesseract.

**Acceptance:** `pytest backend/tests` runs under real pytest with real pydantic. Record the true pass/fail/skip counts — expect changes, since the shim's validation is not pydantic's. `test_auth` must now import. Fix whatever real pydantic rejects; that output is a genuine finding, not noise.

### Step 1 — Test the invariant-4 work, then commit it (test debt on live code)

Write `backend/tests/test_agreement_cap.py` covering: each `EvidenceAgreement` value's effect on a definitive verdict; that FAIL is capped as well as PASS; that UNCERTAIN and EXEMPT are untouched (this justifies the drift-guard's exemption list, so assert it rather than assume it); that the cap only ever downgrades; that fact and finding statuses never disagree; that competing readings reach the reviewer's reason string; that an unrecognised upstream value becomes AGREEMENT_UNKNOWN and not SINGLE_SOURCE; and the full chain `OcrLine(fusion_state="CONFLICTING") → classify_fields → bridge → build_raw_extraction → run_inspection → UNCERTAIN`.

Then write the **AST drift-guard**: parse `rule_engine.py`, find every `_finding(...)` call, and fail if one whose `status` is not literal `FactStatus.UNCERTAIN` or `FactStatus.EXEMPT` omits `fact=`.

Add an `attach_reading_agreement` test asserting no ordinary single-line-derived field lands on AGREEMENT_UNKNOWN — that catches a future extraction site storing a merged bbox.

**Acceptance:** all new tests pass; each proven non-vacuous per 5.4; suite ≥ 249 + new, with no regressions; committed.

### Step 2 — Stand up the database for real (closes B2)

Create the schema from `backend/db/schema.sql`, then run a genuine insert-and-reload of an inspection carrying findings with evidence.

**Acceptance:** `probe_evidence_chain.py` (or an equivalent) writes to real PostgreSQL and reads back facts and findings whose `image_id` and `bbox` are byte-identical to what went in, and a generated PDF from the *reloaded* data still prints `front_7f3a.jpg @ (120,640) 300x28px`. Only then may the status docs say persistence is end-to-end verified. Add a migration mechanism at this point; hand-run DDL will not survive contact with a second machine.

### Step 3 — Start the API and exercise every endpoint (closes B1)

Run `uvicorn`, un-skip `test_api_integration`, and drive all 18 endpoints.

**Acceptance:** 0 of 10 integration tests skipped; every endpoint returns its documented shape; every role guard rejects the wrong role with 403 and accepts the right one; `/scan` produces a persisted inspection whose findings carry locatable evidence. Add `.env.example` and grep the tree for hardcoded credentials in the same pass (closes B4).

### Step 4 — Make the frontend authenticate (closes B3; unlocks the demo)

Add a login screen, token storage and an `Authorization: Bearer` header to every fetch in `dashboard.html` and `capture.html`; handle 401 by returning to login.

**Acceptance:** a human logs in, uploads an image, sees an inspection with evidence, downloads the PDF — without hand-editing anything. **This is the first moment the phrase "SIH DEMO READY" becomes available**, and only for the path actually walked.

### Step 5 — Surface recapture guidance (closes C3, invariant 18)

Add a rich accessor — for example `run_ocr_reading(image) -> ImageReading` — with `run_ocr()` delegating to it so the existing `List[OcrLine]` contract that `/scan`, `/inspect` and `analyze-image` depend on is untouched. Thread `recapture_guidance` and `conflicts` into the capture/scan response, and render them in `capture.html`.

**Acceptance:** a deliberately poor image yields a response containing actionable guidance, displayed to the user; a conflicted read yields both an UNCERTAIN finding and a recapture prompt. Test that the legacy return type is unchanged.

### Step 6 — Integrate CLAUDE 2 (vision/evidence) per 5.6

Priority order within it: `evidence_fusion.py` first (it must satisfy the now-stable evidence contract), then `orientation_ocr.py` / `ocr_engines.py` as *improvements to* the canonical engine, then `product_identity.py`, then `live_capture.py`. Run `CLAUDE 2/`'s `test_legal_safety_invariants.py` against the **canonical** modules — it is the most valuable artefact in that folder, and it will either pass or tell you something true.

**Acceptance:** one OCR path remains; no rich observation is reduced to text-only; the canonical suite still passes; any adopted module arrives with its tests adapted and passing.

### Step 7 — Integrate CLAUDE 4 (geometry/calibration) — the biggest functional win (closes C1)

Read `GEOMETRY_MODULE_NOTES.md` first. Adapt `geometry.py`, `calibration.py`, `measurement.py` into `backend/`. Discard `CLAUDE 4/rules/rules.json`; the canonical rules file is authoritative. Enforce: `NO VALID CALIBRATION → ESTIMATED/UNCERTAIN`; only `VALIDATED CALIBRATION + VALID GEOMETRY + VALID MEASUREMENT → VERIFIED`. Derive verification from evidence, never from a client-supplied mode.

**Acceptance:** Rule 7(2) returns a VERIFIED PASS or FAIL for a calibrated capture and UNCERTAIN without calibration; a forged client `VERIFIED` flag is still downgraded (existing `_has_validated_calibration` test must still pass); cylindrical vs flat geometry is handled distinctly.

### Step 8 — Complete legal coverage (closes 4.3)

Add evaluators for Rule 4, Rule 5 / Schedule II, Rule 26(b), Rule 26(c), Rule 27, Rule 31. Add a top-level `version` and effective-date to `rules.json` and cite it in every finding. Then audit all 19 rules against the current amended text and move `needs_official_verification` forward **only** where a real source was read.

**Acceptance:** every rule in `rules.json` either has an evaluator or is explicitly documented as reference-only; findings cite both rule version and rule-set version; a legally-sourced test case per rule.

### Step 9 — Ground truth and accuracy (closes C4)

Label the 29 real screenshots in `images dataset/` per field with values and bboxes. Use `CLAUDE 1/dataset/` for pipeline plumbing tests **only**, and never as compliance evidence.

**Acceptance:** a reproducible per-field precision/recall report. Only after this may any accuracy number be stated. Then, and only then, attack OCR variant *ranking* (D5) with that harness measuring the gain.

### Step 10 — Review workflow, audit, adversarial suite

Verify `review_inspection` (`main.py:1167`) end to end: an UNCERTAIN finding reaches a reviewer, is resolved, and the resolution is persisted, audited and reflected in the report **without mutating the original evidence** (invariant 16). Then build the adversarial suite: tampered stickers, overlaid labels, conflicting panels, glare, partial occlusion, rotated text, non-Latin scripts. Assert the system degrades to UNCERTAIN/RECAPTURE rather than guessing.

**Acceptance:** immutability of original evidence proven by test; every adversarial case produces a defensible non-definitive outcome, never a confident wrong one.

### Step 11 — Deployment and security (closes B5)

Build and run the Docker images and compose stack. Then a full security pass: authz on every endpoint, SQL parameterisation (already no ORM — verify every query), file-upload limits and content-type validation, rate limiting, secret handling, dependency audit.

**Acceptance:** stack comes up from a clean checkout with documented commands; security review recorded with findings and fixes. Skip Kubernetes.

---

## 7. Immediate state of the working tree — read before your next commit

**There are uncommitted changes in the tree right now.** Last commit is `43ad34f`. Modified since: `backend/schema.py` (added `EvidenceAgreement`, `coerce_evidence_agreement`), `backend/rule_engine.py` (added `agreement`/`alternative_values` to `RawExtraction`, `agreement_cap()`, the cap call inside `_make_fact`, `fact=` on `_finding` and its 5 call sites), `backend/ocr_extraction.py` (`OcrLine` fields, `attach_reading_agreement()`), `backend/ocr_engine.py` (`.lines` now carries fusion state), `backend/capture_session.py` (forwards agreement into `RawExtraction`).

The suite passes at `249 / 1 / 10` with no regressions, and the chain is verified by direct execution as shown in 3.5 — but **no test covers any of it**. Step 1 of section 6 exists precisely to pay that debt. Do Step 1 before building anything new on top.

Also uncommitted from earlier: `samples/sample_report_with_evidence.pdf` and the `.gitignore` entries for the specialist folders may or may not be staged depending on how the index was left; check `git status` before committing.

---

## Appendix A — The 18 safety invariants

These have absolute priority over feature completeness. **Never weaken one to make a test pass.**

1. NOT_VISIBLE ≠ MISSING.
2. NOT_OBSERVED ≠ MISSING.
3. UNREADABLE ≠ MISSING.
4. CONFLICTING evidence cannot automatically produce a definitive compliance finding.
5. UNKNOWN applicability cannot silently become APPLICABLE or NOT_APPLICABLE.
6. UNKNOWN import status cannot silently become DOMESTIC.
7. ESTIMATED measurement cannot be treated as VERIFIED.
8. A client-supplied "VERIFIED" measurement flag is not proof of verification.
9. An exemption requiring review cannot become a definitive EXEMPT result without preserving the review state.
10. OCR extraction alone does not establish legal compliance.
11. A package boundary or PDP candidate does not prove legal PDP placement.
12. A detected OCR box does not establish legal font-size compliance.
13. AI/VLM output cannot directly determine the legal verdict.
14. Similarity/tampering signals are advisory unless independently supported.
15. Missing evidence must not be silently ignored.
16. Original captured evidence must remain immutable.
17. Every legal finding must be traceable to evidence and a rule version.
18. If evidence is insufficient, the correct behaviour is UNCERTAIN, RECAPTURE, or HUMAN REVIEW.

Corollaries that have already prevented real defects: UNCERTAIN evidence must never directly become FAIL. Low OCR confidence must never itself become non-compliance. Poor image quality must never itself become non-compliance. Never average; never silently choose. Never invent invisible digits. Preserve the original image unchanged. Never rotate the whole image as the primary solution. Never claim actual ingredient composition from an image. Never assert COUNTERFEIT or CONFIRMED TAMPERING.

## Appendix B — Current inventory

**Backend** (18 modules, ~12,700 lines): `ocr_engine.py` 2151 · `region_detection.py` 1544 · `rule_engine.py` 1574 · `preprocess.py` 1424 · `ocr_extraction.py` 1240 · `main.py` 1235 · `schema.py` 535 · `orientation.py` 523 · `unit_price.py` 473 · `capture_session.py` 469 · `report.py` 450 · `sticker_detection.py` 441 · `vlm_verifier.py` 403 · `product_similarity.py` 394 · `exemption.py` 366 · `image_quality.py` 334 · `auth.py` 171 · `config.py` 147. Plus `db/persistence.py`, `db/schema.sql`.

**Tests** (12 files, ~5,250 lines): `test_ocr_engine.py` 1039 · `test_rule_engine.py` 791 · `test_preprocess.py` 704 · `test_region_detection.py` 624 · `test_report_evidence.py` 560 · `test_orientation.py` 499 · `test_capture_session.py` 357 · `test_persistence_evidence.py` 233 · `test_api_integration.py` 207 (all skipped) · `conftest.py` 136 · `test_exemption.py` 62 · `test_auth.py` 38 (fails on import).

**Absent from `backend/` but needed:** `geometry.py`, `calibration.py`, `measurement.py`, barcode decoding, `.env.example`, root `Dockerfile`.

**Useful tools:** `backend/tools/run_tests.py`, `pydantic_shim.py`, `probe_evidence_chain.py`, `bench_ocr.py` (`--indices 0 3 7`).

## Appendix C — A prompt template for coding models

> You are working on the SIH 2026 PS 26034 Legal Metrology compliance platform at `C:\Users\HP\SIH 2026`. Read `ENGINEERING_ASSESSMENT_AND_ROADMAP.md` first, in full.
>
> Your task is **Step N** of section 6. Do only that step. Its acceptance criterion is stated there; you are done when it is met and not before.
>
> Binding constraints: the 18 invariants in Appendix A have priority over features and may never be weakened to make a test pass. Never let AI output determine a legal verdict directly. Never substitute a plausible value for a missing one — use a conspicuous sentinel that fails safe. Enforce invariants at choke points, not at call sites. One canonical implementation per responsibility; do not create `*_v2.py`. Never commit secrets. Inspect `git status` before changing anything and do not destroy unrelated work.
>
> Before you claim a test proves something, reintroduce the defect and confirm the test fails; report how many tests failed. Do not write tests that accept any of PASS/FAIL/UNCERTAIN as success. Do not hide skipped tests.
>
> Report using the format in section 5.7, and use the five status words from section 0 with their exact meanings. Do not write "verified" for anything you did not execute, and do not state an accuracy figure — there is no labelled ground-truth set.
