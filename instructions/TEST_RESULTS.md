# TEST AND VERIFICATION RESULTS

## 1. Automated Test Suite Execution Summary

### Pytest Canonical Backend Suite
- **Command**: `python -m pytest backend/tests/`
- **Result**: `425 passed, 18 skipped, 0 failed in 22.23s`
- **Baseline Invariant**: Exceeded initial baseline (415 passed -> 425 passed). Zero regressions.

```
============================== test session starts ===============================
platform win32 -- Python 3.12.10, pytest-8.3.5, pluggy-1.5.0
rootdir: C:\Users\HP\SIH LATEST\backend
configfile: pytest.ini
collected 443 items

backend\tests\regulatory\test_versioning.py ....                         [  0%]
backend\tests\test_amendment_pipeline.py ........                        [  2%]
backend\tests\test_api.py ................                              [  6%]
backend\tests\test_audit.py .....                                       [  7%]
backend\tests\test_auth.py .......                                      [  9%]
backend\tests\test_barcode_decode.py .........................           [ 14%]
backend\tests\test_barcode_pdp_integration.py ...                       [ 15%]
backend\tests\test_bru_integration.py ..........                        [ 17%]
backend\tests\test_build01_audit_log.py ........                         [ 19%]
backend\tests\test_build02_api_auth.py ........                          [ 21%]
backend\tests\test_build03_visual_recovery.py ......                    [ 22%]
backend\tests\test_build04_postgres_schema.py ........                   [ 24%]
backend\tests\test_build05_rule_versioning.py ........                  [ 26%]
backend\tests\test_build06_rule_version_runtime.py .....                [ 27%]
backend\tests\test_build07_rag_corpus.py ........                       [ 29%]
backend\tests\test_build08_rag_retrieval.py .........                   [ 31%]
backend\tests\test_build09_amendment_publication.py .......             [ 32%]
backend\tests\test_build10_multi_framework.py ...........               [ 35%]
backend\tests\test_build11_versioning_safety.py .......                  [ 36%]
backend\tests\test_calibration.py ...................................   [ 44%]
backend\tests\test_capture_session.py ...........................        [ 50%]
backend\tests\test_declaration_pipeline.py ............................. [ 54%]
.................                                                        [ 58%]
backend\tests\test_orientation.py ..........................             [ 64%]
backend\tests\test_persistence_evidence.py ............                  [ 67%]
backend\tests\test_preprocess.py ...................................     [ 74%]
backend\tests\test_region_detection.py ..............................    [ 81%]
backend\tests\test_report_evidence.py ............................sssss  [ 89%]
backend\tests\test_rule_engine.py ...................................... [ 97%]
..                                                                       [ 98%]
backend\tests\test_scan_visual_recovery_integration.py ..                [ 98%]
backend\tests\test_visual_recovery_merge.py ..                           [ 99%]
backend\tests\test_vlm_visual_recovery.py ....                           [100%]

================ 425 passed, 18 skipped, 5 warnings in 22.23s =================
```

---

## 2. New Integration Tests (`backend/tests/test_bru_integration.py`)

All 10 dedicated integration tests passed with 100% success:

1. `test_bru_manufacturer_classification`: Verifies `MFG. BY` and `MFD. BY` regex extraction (`195/2A, B.D. SAWANT, FOODS LIMITED`).
2. `test_bru_marketer_classification`: Verifies `MKTD. BY` and `MKT. BY` regex extraction (`HINDUSTAN UNILEVER LIMITED`).
3. `test_bru_consumer_care_and_toll_free`: Verifies `Levercare` toll-free `1800-10-22-221` and email extraction.
4. `test_bru_net_quantity_contextual_recovery`: Verifies contextual `1509` -> `150 g` repair when adjacent to `NET WEIGHT`.
5. `test_bru_date_association_and_mm_yy_rate_collision`: Verifies that `= 2.80/g` is not parsed as Feb 1980 and dates enforce chronology (`13/05/26` PKD vs `12/10/27` USE BY).
6. `test_bru_unit_sale_price_classification`: Verifies `₹2.80/g` and `= 2.80/g` extraction into `unit_sale_price`.
7. `test_bru_batch_prefix_stripping`: Verifies label prefix stripping from `BATCH NO. HF130526 17:08` to `HF130526 17:08`.
8. `test_no_fabricated_quantity_fallback`: Verifies missing quantity remains `None` / `not_observed` and never defaults to `1.0 unit`.
9. `test_bru_reconstruct_split_fields`: Verifies cross-surface split-field reconstruction (`NET WT:` on Surface A + `150 g` on Surface B -> `net_quantity=150 g` with `UNCERTAIN` review state).
10. `test_rag_grounding_integration`: Verifies RAG statutory grounding resolves 12 provisions with citations and effective dates.

---

## 3. Real Photographs Benchmark Evaluation (`eval_pipeline.py`)

- **Multi-Surface Aggregation (BRU Panels 1 & 2)**:
  - Total Declarations Checked: 10
  - Applicable: 9, Detected: 9, Verified: 5, Review Required: 4, Non-Compliant: 0
  - Overall Legal Status: `UNCERTAIN` (Conservative absence / review required; zero false PASS).
  - MRP: `₹420` (Front Panel)
  - Net Quantity: `150 g` (Back Panel)
  - Manufacturer: `FOODS LIMITED` (Back Panel)
  - Use By: `13/05/26` (Front Panel)
  - Unit Sale Price: `₹2.8/g` (Front Panel)
  - Consumer Care Precision/Recall: 100% / 100% (F1 = 100%)

---

## 4. Real BRU Multi-Surface Production HTTP Inspection (`/scan`)

- **Endpoint**: `POST /scan` with multipart uploads of Panel 1 and Panel 2.
- **HTTP Status**: `200 OK`
- **Inspection ID**: `8909106043251:scan-820ecb53` (GTIN-13 derived)
- **Overall Status**: `UNCERTAIN`
- **Applicable Rule Version**: `MULTIPLE:2011 (amended),2011 as amended,2011 as amended by GSR 629(E) dated 2017-06-23`
- **Regulatory Scope**: `['lmpc', 'fssai']`, `is_food=True`
- **RAG Grounded Provisions**: 12 provisions grounded with source references
- **PDF Report Generation**: Generated valid PDF document with grounded statutory standards table.
