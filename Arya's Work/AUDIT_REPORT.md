# LexMetra Product Compliance Engine — Deep Audit & Hardening Report

**Project**: LexMetra (SIH 2026)  
**Date**: September 2026  
**Status**: Completed & Verified  
**Authoritative Engine**: `backend/engine/` (Single Deterministic Python Data-Driven Compliance Engine)  

---

## 1. Architectural Summary & Mandates

1. **Zero OpenL Policy**: Verified that OpenL does not exist in the codebase, Docker services, configuration, or environment variables. No second rule engine or external rule service was added.
2. **Deterministic Legal Decision Layer**: OCR, CV, and VLM produce *evidence*. Ingestion pipelines produce *rule data*. Only `backend/engine/RuleEngine` produces the authoritative compliance decision. No LLM/RAG/Graph database logic participates in deterministic compliance evaluation.
3. **Single Compliance Execution Path**: All endpoints (`/inspect`, `/scan`, and multi-surface session finalization) delegate exclusively to `backend/engine/`. Legacy `rule_engine.py` remains only as an API-compatible adapter delegating to `backend/engine/`.
4. **Kleene K3 Three-Valued Logic**: All applicability, exemption, and requirement conditions adhere to strict three-valued logic (`TRUE`, `FALSE`, `UNKNOWN`). Missing context or insufficient evidence never silently converts to `FALSE` or `PASS`.
5. **Canonical Decision Package**: Inspection results output the canonical schema specified in Section 16, linking inspection ID, legal basis, active rule versions, summaries, rule findings, evidence provenance, calculations, dependencies, and audit logs.

---

## 2. Original Issues Found During Deep Audit

1. **Dual / Divergent Engine Paths**:
   - Earlier prototype relied on `backend/rule_engine.py` with hardcoded checks, while `backend/engine/` had generic declarative logic. In some legacy endpoints, rules were checked differently.
2. **Missing Regulatory Rule Implementations**:
   - Rules 4, 5, 25, 26(b), 26(c), 27, and 31 were either unmodelled, partially declared, or silently skipped without explicit `NOT_CONSIDERED` status.
   - Rule 5 (Standard Pack Sizes) was repealed/superseded as of 2022-08-19 (G.S.R. 577(E)), but lacked date-aware active rule resolution.
3. **Evidence Provenance Degradation**:
   - `build_raw_extraction` and `lexmetra_adapter.py` lost `image_id`, bounding boxes (`bbox`), and usability flags, causing findings to default to `UNATTRIBUTED_IMAGE_ID` and dropping spatial auditability.
4. **OCR Quality Assessment Bug**:
   - Heavily corrupted OCR text (e.g. `"Every perscn shail bear the decleration of the manufacturer."`) received an unpenalized quality score of `1.0` in fallback mode due to silent failure and missing spellchecker vocabulary.
5. **Amendment Metadata Normalization**:
   - Multi-line whitespace strings such as `"Second\nAmendment,   2022"` were un-normalized, causing discrepancies across legal metadata and version lookup.
6. **PostgreSQL JSONB Deserialization Vulnerabilities**:
   - JSONB columns already deserialized by `psycopg2` risk runtime `TypeError` when passed to `json.loads()`, and malformed JSON could silently crash without logging.
7. **Condition & Calculation Edge Cases**:
   - Unusable evidence (`usable=False`) previously bypassed presence checks instead of propagating `Tri.UNKNOWN`.
   - Division-by-zero in derived calculations could fail or default without explicit `UNCERTAIN` calculation traces.
8. **Frontend TypeScript & Status Discrepancies**:
   - `InspectionApp.tsx` had unused imports, untyped transition hooks, and lacked rendering support for newer states (`NOT_CONSIDERED`, `ENGINE_ERROR`, `NOT_APPLICABLE`).

---

## 3. Fixes Made

### A. Engine Core (`backend/engine/`)
- **`rule_model.py`**: Added `source_document` and `status` to `Rule` dataclass.
- **`evidence.py`**:
  - Enriched `EvidenceValue` with `normalized_value`, `image_id`, `bbox`, `verification_status`, `usable`, and `quality_state`.
  - Added `is_usable()` method enforcing `usable is not False` and `quality_state != "unusable"`.
  - Added `Evidence.get(path, default=None)` convenience resolver.
- **`conditions.py`**:
  - Added `__eq__` on `ConditionTrace` for direct comparison with `Tri` values (`ConditionTrace == Tri.TRUE`).
  - Added `in` and `not_in` aliases for `in_list` and `not_in_list`, supporting both `"values"` and `"value"` arrays.
  - Hardened `_resolve_operand`: returns `Tri.UNKNOWN` when evidence is marked unusable (`is_usable() is False`).
  - Hardened `_op_exists`: returns `Tri.UNKNOWN` when evidence exists but is unusable.
  - Hardened `_op_missing`: returns `Tri.UNKNOWN` when target condition is `UNKNOWN`.
  - Recursed both `"args"` and `"conditions"` / `"condition"` keys in `evaluate_condition`.
- **`calc.py`**:
  - Enriched `CalcTrace` with `expression`, `inputs`, `normalized_values`, `output`, `status`, and `explanation`.
  - Guaranteed division-by-zero or missing input returns `CalcTrace(ok=False, status="UNCERTAIN", output=None)`.
- **`results.py`**:
  - Added `ComplianceStatus.NOT_CONSIDERED`.
  - Enriched `EvidenceCitation` with `image_id`, `bbox`, `raw_text`, `confidence`, `verification_status`, and `usable`.
  - Enriched `RuleResult` with `calculations`, `dependencies`, and `review_required`.
  - Added canonical `ComplianceDecisionPackage` dataclass conforming to Section 16 specification.
- **`aggregate.py`**: Supported configurable `policy.allow_exempt_overall`.
- **`evaluator.py`**:
  - Guaranteed terminal audit trace (`stage("rule_result", ...)`) on every return path without early exits bypassing trace.
  - Implemented date-based active rule version filtering: rules superseded before or effective after `as_of_date` / `inspection_date` evaluate to `NOT_CONSIDERED`.
  - Merged `evidence.context` with context dictionary so scope checks (`applies_to`) and condition evaluations seamlessly access product metadata.
  - Ensured exemptions evaluate to `applicability = APPLICABLE` with `status = EXEMPTED`.

### B. Adapter & Integration (`backend/engine/lexmetra_adapter.py` & `backend/schema.py`)
- **`schema.py`**:
  - Added `FactStatus.NOT_CONSIDERED`.
  - Enriched `InspectionSummary` with `not_applicable`, `engine_error`, and `not_considered` fields.
  - Added `decision_package` dictionary field to `ProductInspection`.
- **`lexmetra_adapter.py`**:
  - Added `ComplianceStatus.NOT_CONSIDERED: FactStatus.NOT_CONSIDERED` mapping.
  - Preserved real `image_id`, `bbox`, `usable`, `quality_state`, and `verification_status` when converting extractions to `Evidence`.
  - Stamped canonical `ComplianceDecisionPackage` onto `ProductInspection.decision_package`.
  - Populated complete evaluation context (`product_category`, `is_imported`, `trade_type`, `is_multipack`, `is_advertisement`, `is_export_only`, etc.).

### C. Multi-Surface Capture Sessions (`backend/capture_session.py`)
- Extended `stamp_provenance` to accept `surface_type` / `surface_id` and preserve original image attribution during cross-surface merges.
- Confirmed disjoint front/back captures merge correctly and evaluate to compliant without false-negative absence errors.

### D. OCR Quality & Spellchecker (`backend/lexmetra_rules/ocr_quality.py`)
- Added `is_spellchecker_active()` and `get_ocr_quality_mode()` to explicitly expose dictionary vs fallback mode.
- Added legal vocabulary baseline and impossible consonant cluster / garble detection to fallback mode.
- Verified: `"Every perscn shail bear the decleration of the manufacturer."` is flagged with score `0.625` (never 1.0) in both dictionary and fallback heuristic modes.

### E. Amendment Metadata Normalization (`backend/lexmetra_rules/amendment_metadata.py`)
- Added `normalize_whitespace()` to normalize newlines, tabs, and multi-spaces.
- Auto-normalized fields in `AmendmentMetadata.__post_init__`.

### F. PostgreSQL JSONB Safety (`backend/db/persistence.py`)
- Enhanced `decode_json_column` to handle pre-deserialized dicts/lists, JSON strings, empty/None values, and log malformed text without throwing uncaught exceptions.
- Updated `list_session_captures` to use `decode_json_column`.

### G. Frontend Build (`frontend/react-app/`)
- Resolved all TypeScript compiler errors in `src/components/InspectionApp.tsx`.
- Extended `src/lib/types.ts` with all 7 fact statuses.
- Production build (`tsc && vite build`) executes cleanly with 0 errors.

---

## 4. Rule Coverage Audit

| Rule ID | Legal Provision | Subject | Status | Outcome / Behavior |
|---|---|---|---|---|
| `LMPC-4-MULTIPACK` | Rule 4 | Multi-piece and combination packages | Active / Evaluated | PASS when inner pack declarations present; NOT_APPLICABLE for single pack |
| `LMPC-5-STANDARD-PACK-SIZE` | Rule 5 / Second Sched. | Standard pack sizes | Superseded / Filtered | NOT_CONSIDERED for inspections on/after 2022-08-19; evaluated for past dates |
| `LMPC-6-1-A-MANUFACTURER` | Rule 6(1)(a) | Manufacturer/packer name & address | Active / Evaluated | Deterministic PASS / FAIL / UNCERTAIN |
| `LMPC-6-1-B-COMMON-NAME` | Rule 6(1)(b) | Generic / common name of commodity | Active / Evaluated | Deterministic PASS / FAIL / UNCERTAIN |
| `LMPC-6-1-C-NET-QUANTITY` | Rule 6(1)(c)/(f) | Net quantity declaration | Active / Evaluated | Deterministic PASS / FAIL / UNCERTAIN |
| `LMPC-6-1-D-MFG-DATE` | Rule 6(1)(d) | Month and year of manufacture | Active / Evaluated | Deterministic PASS / FAIL / UNCERTAIN |
| `LMPC-6-1-E-MRP` | Rule 6(1)(e) | Maximum retail price (inclusive of taxes) | Active / Evaluated | Deterministic PASS / FAIL / UNCERTAIN |
| `LMPC-6-1-F-CONSUMER-CARE` | Rule 6(1)(f) | Consumer care contact details | Active / Evaluated | Deterministic PASS / FAIL / UNCERTAIN |
| `LMPC-6-1-G-COUNTRY-ORIGIN` | Rule 6(10) | Country of origin for imported goods | Active / Evaluated | NOT_APPLICABLE for domestic; evaluated for imported |
| `LMPC-6-11-UNIT-PRICE` | Rule 6(11) | Unit sale price declaration & tolerance | Active / Evaluated | Deterministic arithmetic validation |
| `LMPC-NUMERAL-HEIGHT` | First Sched. | Net quantity numeral font height | Active / Evaluated | Checked against quantity bands |
| `LMPC-25-EXPORT` | Rule 25 | Export packages sold in India | Active / Evaluated | PASS when repacking evidence verified; NOT_APPLICABLE for non-export |
| `LMPC-26-B-FAST-FOOD` | Rule 26(b) | Fast food / restaurant dispatches | Active / Exempted | EXEMPTED when packer is restaurant/hotel; NOT_APPLICABLE otherwise |
| `LMPC-26-C-DRUG-FORMULATIONS`| Rule 26(c) | Scheduled formulations under DPCO | Active / Exempted | EXEMPTED when under DPCO; NOT_APPLICABLE otherwise |
| `LMPC-27-REGISTRATION` | Rule 27 | Enterprise registration under Ch. VI | Active / Evaluated | PASS when registration number evidenced; NOT_APPLICABLE for package label |
| `LMPC-31-ADVERTISEMENT` | Rule 31 | Retail price declarations in ads | Active / Evaluated | PASS when net quantity declared; NOT_APPLICABLE for physical packaging |

### Rules Still Not Implemented
- **Third Schedule commodities with special declaration requirements** (e.g. specific industrial yarn, raw unbleached cloth): Explicitly marked `NOT_CONSIDERED` or `NOT_APPLICABLE` unless product category triggers them.
- **Rule 28 & 29 (Registration of Importers & Powers of Inspection)**: Administrative/officer search-and-seizure workflow, outside product label compliance scope.

---

## 5. Test Suite Metrics

- **Total Unit & Integration Tests**: 676
- **Passed**: 666
- **Skipped**: 10 (external network tests / mock services)
- **Failed**: 0
- **Duration**: ~69 seconds
- **New Hardened Engine Tests (`backend/tests/test_hardened_engine.py`)**: 18 tests, 100% passing.

---

## 6. Known Limitations & Conservatism Guarantees

1. **Conservative Absent vs. Missing Semantics**:
   - Absence of a declaration in a single-view photo is treated as `UNKNOWN` until adequate surface coverage is established. Only multi-surface sessions with complete coverage can conclude a declaration is absent (`FAIL`).
2. **Deterministic Engine Non-Compromise**:
   - No LLM prompt or embeddings are used to determine legal compliance. All compliance verdicts emerge strictly from boolean/tri-state evaluation of verified evidence against structured rules.
