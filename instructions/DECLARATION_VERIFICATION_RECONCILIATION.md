# DECLARATION VERIFICATION RECONCILIATION & STATUS PROPAGATION REPORT
**Authoritative Architectural & Production Evaluation Report**
**Task:** P0 — Fix Declaration Verification Score / Status Propagation Without Regressing the Generalized Inspection Pipeline
**Date:** 2026-09-12
**System Posture:** Automated Screening / Pre-Inspection Aid under the Legal Metrology (Packaged Commodities) Rules, 2011 (LMPC 2011)

---

## 1. Executive Summary & Historical 1/9 Behavior

Historically, when inspecting multi-surface commodity packages (such as the standard BRU Instant Coffee 150g jar fixture across Panels 1 & 2), the user interface displayed an anomalous verification score:

```
1 / 9 VERIFIED
```

Despite the backend OCR and computer vision pipeline detecting declarations across both surfaces, the inspection result appeared severely deflated. Field inspectors and regulatory reviewers could not distinguish between genuine statutory non-compliance, unphotographed package surfaces, low-confidence OCR reads, and legitimate compliant declarations.

This forensic audit traced the entire end-to-end status propagation pipeline:
$$\text{OCR / CV Capture} \longrightarrow \text{Canonical Facts} \longrightarrow \text{Rule Evaluation} \longrightarrow \text{Canonical Declarations} \longrightarrow \text{API Serializer} \longrightarrow \text{Frontend Adapter} \longrightarrow \text{PDF Report}$$

### The Resolution
Rather than artificially forcing declarations to pass or relaxing legal standards, the pipeline was corrected to enforce **strict evidence truthfulness**:
1. High-quality extractions with valid provenance and verified regulatory requirements are accurately marked `VERIFIED`.
2. Partial, mangled, or low-confidence extractions are truthfully flagged as `REVIEW_REQUIRED`.
3. Obsolete or non-applicable provisions (such as Rule 5 standard pack sizes omitted under GSR 779(E)) are categorized as `NOT_APPLICABLE` and excluded from the active mandatory declaration denominator.
4. **Backend, Frontend, and PDF now agree completely: 4 of 9 Applicable Declarations Verified (44%)**, with 5 declarations accurately flagged for inspector review.

---

## 2. Root Cause Analysis

A multi-factor audit identified why the historical pipeline produced the 1/9 result:

| Subsystem | Root Cause | Consequence |
| :--- | :--- | :--- |
| **Date Association Confidence** | `date_association.py` assigned `assoc.association_score` (0.501) directly to `extraction.confidence`, disregarding the high OCR confidence of the date token (0.96) and label (0.61). | PKD (`13/05/26`) fell below the 0.55 confidence threshold and was downgraded to `UNCERTAIN` / `REVIEW_REQUIRED`. |
| **Manufacturer Address Overstatement** | The pipeline had no syntactic/semantic address completeness check; any detection starting with "MFG BY" was accepted, while mangled text fragments were either falsely verified or arbitrarily rejected. | Fragmented company names like `"195/2A,, B.D. SAWANT, FOODS LIMITED,"` lacked city/state/PIN, necessitating an explicit Rule 6(1)(a) completeness guard. |
| **Missing Batch Field Definition** | `schema.py` was missing `BATCH_NO = "batch_no"` in `CanonicalDeclarationField` and `CANONICAL_DECLARATION_DEFINITIONS`. | Batch numbers extracted by OCR were discarded or classified under generic facts without canonical evaluation. |
| **Statutory Applicability Denominator** | Rule 5 (Standard Pack Sizes under Second Schedule) was omitted via statutory amendment GSR 779(E) dated 2021-11-02. However, it was previously counted as an unevidenced requirement. | The denominator was distorted by obsolete statutory provisions. |
| **Frontend Mapping Flattening** | Frontend `mapCanonicalStatus` previously routed four distinct backend statuses (`INSUFFICIENT_EVIDENCE`, `PARTIALLY_DETECTED`, `REVIEW_REQUIRED`, `NON_COMPLIANT`) into `"REVIEW"`. | All nuance was collapsed into a generic "Review" bucket, masking whether evidence was absent, low-confidence, or non-compliant. |
| **PDF Reporting Disconnect** | `report.py` lacked a canonical declarations matrix table and did not include the declaration verification count in the summary table. | The PDF report showed only rule findings and facts, omitting the headline declaration score shown on the web UI. |

---

## 3. Complete 9-Declaration Matrix (BRU Instant Coffee Fixture)

The canonical evaluation across the two real-photo panels (`panel_1.jpg` and `panel_2.jpg`) of the BRU Instant Coffee 150g commodity establishes the following truthful 9-declaration matrix:

| # | Declaration Field | Ground Truth | Raw OCR Extracted | Normalized Value | Confidence | Evidence Status | Rule ID & Clause | Final Status | Frontend Status | Reason / Justification |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: | :--- | :---: | :---: | :--- |
| **1** | `common_name` | Flavoured Instant Coffee-Chicory Mixture | `FLAVOURED INSTANT COFFEE-CHICORY MDX` | Flavoured Instant Coffee-Chicory Mixture | 0.75 | PASS | LMPC-2011-R6 Rule 6(1)(b) | **VERIFIED** | **VERIFIED** | Commodity name verified; coffee-chicory mixture recognized under Food category. |
| **2** | `net_quantity` | 150 g | `150 g` | 150 g | 0.90 | PASS | LMPC-2011-R6 Rule 6(1)(e) | **VERIFIED** | **VERIFIED** | Net quantity matches declared unit; no fabricated fallback; area & font verified. |
| **3** | `mfg_date` | 13/05/26 | `13/05/26` | 13/05/2026 | 0.63 | PASS | LMPC-2011-R6 Rule 6(1)(d) | **VERIFIED** | **VERIFIED** | Composite confidence $\ge 0.55$; associated with PKD; chronology valid ($< \text{Use By}$). |
| **4** | `best_before_use_by` | 12/10/27 | `12/10/27` | 12/10/2027 | 0.96 | PASS | LMPC-2011-R6 Rule 6(1)(d) proviso | **VERIFIED** | **VERIFIED** | Expiry/Use-by date verified; associated with USE BY label; chronology valid. |
| **5** | `manufacturer_name_address` | 195/2A, B.D. Sawant Foods Ltd, Kudus, Tal. Wada, Dist. Palghar - 421312 | `195/2A,, B.D. SAWANT, FOODS LIMITED,` | 195/2A,, B.D. Sawant Foods Limited, | 0.45 | UNCERTAIN | LMPC-2011-R6 Rule 6(1)(a) | **REVIEW_REQUIRED** | **REVIEW** | Fragment ends in comma; missing city, district, state, and 6-digit PIN code. Requires inspector verification. |
| **6** | `mrp` | ₹420 | `₹420` (glyph broken) | ₹420.00 | 0.17 | UNCERTAIN | LMPC-2011-R6 Rule 6(1)(da) | **REVIEW_REQUIRED** | **REVIEW** | Numerical value recovered, but currency glyph OCR confidence (0.17) is below 0.55 threshold. |
| **7** | `unit_sale_price` | ₹2.80/g | `₹2.8/g` | ₹2.80/g | 0.42 | UNCERTAIN | LMPC-2011-R6-11 Rule 6(11) | **REVIEW_REQUIRED** | **REVIEW** | Legally depends on MRP verification ($\text{MRP} / 150\text{g}$). Unverified MRP prevents automated USP clearance. |
| **8** | `consumer_care` | 1800-10-22-221, care@unilever.com, PO Box 14760 | `bake, PRES: 1800-10-22-2` | 1800-10-22-2 | 0.36 | UNCERTAIN | LMPC-2011-R6 Rule 6(1)(f) | **REVIEW_REQUIRED** | **REVIEW** | Telephone number truncated (missing final digits); email/address not read in crop. |
| **9** | `batch_no` | HF 130526 17:08 | `HF 130526 17:08` | HF 130526 17:08 | 0.52 | UNCERTAIN | LMPC-2011-R6 / FSSAI 2.2.2 | **REVIEW_REQUIRED** | **REVIEW** | Value extracted accurately, but extraction confidence 0.52 is marginally below 0.55 threshold. |
| *—* | `standard_pack_size` | Non-mandatory | `None` | `None` | 1.00 | EXEMPT | LMPC-2011-R5 Rule 5 | **NOT_APPLICABLE** | **EXEMPT** | Rule 5 omitted by statutory amendment GSR 779(E); excluded from denominator. |
| *—* | `country_of_origin` | India (Domestic) | `None` | `None` | 1.00 | EXEMPT | LMPC-2011-R6 Rule 6(1)(a) proviso | **NOT_APPLICABLE** | **EXEMPT** | Commodity is domestically manufactured; import origin declaration not applicable. |

---

## 4. Backend Status Before and After

```
                                  [BEFORE FIX]
========================================================================================
Declaration Field            | Extracted Value             | Status          | Reason
========================================================================================
manufacturer_name_address    | 195/2A,, B.D. SAWANT, FO... | VERIFIED        | Falsely verified mangled fragment
common_name                  | FLAVOURED INSTANT COFFEE... | VERIFIED        | Compliant
net_quantity                 | 150 g                       | REVIEW_REQUIRED | Dropped or fabricated fallback 1 unit
mfg_date                     | 13/05/26                    | REVIEW_REQUIRED | Confidence 0.501 < 0.55 (suppressed)
best_before_use_by           | 12/10/27                    | REVIEW_REQUIRED | Label collision with 2.80/g
mrp                          | ₹420                        | REVIEW_REQUIRED | Low OCR confidence
consumer_care                | bake, PRES: 1800-10-22-2    | REVIEW_REQUIRED | Truncated OCR
unit_sale_price              | ₹2.8/g                      | REVIEW_REQUIRED | Unclassified
batch_no                     | [Not Defined]               | NOT_DETECTED    | Missing from canonical schema
standard_pack_size           | None                        | REVIEW_REQUIRED | Evaluated under omitted Rule 5
country_of_origin            | None                        | NOT_APPLICABLE  | Domestic
========================================================================================
Summary: 1 or 2 Verified / 9 or 10 Applicable (Inconsistent)

                                  [AFTER FIX]
========================================================================================
Declaration Field            | Extracted Value             | Status          | Reason
========================================================================================
manufacturer_name_address    | 195/2A,, B.D. SAWANT, FO... | REVIEW_REQUIRED | Missing city/state/PIN; trailing comma
common_name                  | FLAVOURED INSTANT COFFEE... | VERIFIED        | Legally compliant & high confidence
net_quantity                 | 150 g                       | VERIFIED        | Correctly extracted & validated
mfg_date                     | 13/05/26                    | VERIFIED        | Composite conf 0.63 >= 0.55; valid date
best_before_use_by           | 12/10/27                    | VERIFIED        | Conf 0.96 >= 0.55; chronological order
mrp                          | ₹420                        | REVIEW_REQUIRED | Conf 0.17 < 0.55; glyph broken
consumer_care                | bake, PRES: 1800-10-22-2    | REVIEW_REQUIRED | Conf 0.36 < 0.55; partial phone digits
unit_sale_price              | ₹2.8/g                      | REVIEW_REQUIRED | Dependent on unverified MRP
batch_no                     | HF 130526 17:08             | REVIEW_REQUIRED | Conf 0.52 < 0.55; truth preserved
standard_pack_size           | None                        | NOT_APPLICABLE  | GSR 779(E) statutory omission
country_of_origin            | None                        | NOT_APPLICABLE  | Domestic commodity
========================================================================================
Summary: Exactly 4 Verified / 9 Applicable (44%)
```

---

## 5. Frontend Status Before and After

The frontend receives the canonical `declarations` array and `declaration_summary` from the backend API:

### Frontend Mapping Logic (`frontend/react-app/src/lib/types.ts` & `adapters.ts`):
```typescript
export function mapCanonicalStatus(status: RawCanonicalStatus): DeclarationStatus {
  switch (status) {
    case "VERIFIED": return "VERIFIED";
    case "NOT_APPLICABLE": return "EXEMPT";
    case "NON_COMPLIANT": return "MISSING";
    case "NOT_DETECTED_IN_PROVIDED_IMAGES": return "UNOBSERVED";
    case "INSUFFICIENT_EVIDENCE": return "UNOBSERVED";
    case "PARTIALLY_DETECTED": return "REVIEW";
    case "DETECTED": return "REVIEW";
    case "REVIEW_REQUIRED": return "REVIEW";
    default: return "REVIEW";
  }
}
```

### Score Computation:
```typescript
const applicable = declarations.filter((d) => d.status !== "EXEMPT");
const verified = applicable.filter((d) => d.status === "VERIFIED").length;
const verifiedScore = Math.round((verified / applicable.length) * 100);
```

### Before vs. After:
* **Before:** `1 / 9 VERIFIED` (or `1 / 10`), with all other fields lumped into ambiguous "Review" states.
* **After:**
  * **Verified Count:** 4
  * **Review Required Count:** 5
  * **Exempt / Not Applicable:** 2 (excluded from denominator)
  * **Applicable Denominator:** 9
  * **Headline Score:** **4 / 9 Verified (44%)**

---

## 6. PDF Status Before and After

### Changes in `backend/report.py`:
1. **Summary Table Alignment:**
   Added declaration verification score row to the executive summary table:
   ```python
   ["Declarations verified", f"{v_count} of {app_count} applicable declarations verified ({pct:.0f}%)"]
   ```
   Renders as: `Declarations verified: 4 of 9 applicable declarations verified (44%)`.

2. **Canonical Mandatory Declarations Matrix:**
   A dedicated PDF table now renders all 11 canonical declarations directly below the executive summary:
   * **Columns:** Declaration Field, Extracted Value, Status, Clause / Rule, Verification Reason
   * **Status Colors:** Green (`VERIFIED`), Amber (`REVIEW_REQUIRED`), Muted Grey (`NOT_APPLICABLE`), Red (`NON_COMPLIANT`).

### Output:
```
Backend Verified Count:  4 / 9
Frontend Verified Count: 4 / 9
PDF Verified Count:      4 of 9 (44%)
--> All three representations are in 100% agreement.
```

---

## 7. Verification-Count Calculation & Denominator Principles

### Denominator Rule:
The denominator must represent the number of declarations **statutorily applicable** to the commodity being inspected.
$$\text{Denominator} = \sum_{d \in \text{Declarations}} [\text{Status}(d) \neq \text{NOT\_APPLICABLE}]$$

### Inclusions and Exclusions:
1. **Omitted Rule 5 (Standard Pack Sizes):**
   * Rule 5 and the Second Schedule of the Legal Metrology (Packaged Commodities) Rules, 2011 were omitted by the Ministry of Consumer Affairs via statutory notification **G.S.R. 779(E) dated 2nd November 2021**.
   * For modern packaged goods inspected under current law, standard pack sizes are no longer mandatory.
   * `standard_pack_size` is therefore marked `NOT_APPLICABLE` and excluded from the denominator.
2. **Country of Origin:**
   * Rule 6(1)(a) proviso mandates Country of Origin declarations only for **imported** commodities.
   * For domestic products (`is_imported = False`), this declaration is `NOT_APPLICABLE` and excluded.
3. **Mandatory 9 Declarations for Retail Packaged Food:**
   1. Manufacturer Name & Address (Rule 6(1)(a))
   2. Common / Generic Name (Rule 6(1)(b))
   3. Net Quantity (Rule 6(1)(e))
   4. Manufacturing Date (Rule 6(1)(d))
   5. Best Before / Expiry Date (Rule 6(1)(d) proviso)
   6. Maximum Retail Price (Rule 6(1)(da))
   7. Consumer Care Details (Rule 6(1)(f))
   8. Unit Sale Price (Rule 6(11))
   9. Batch / Lot / Code Number (Rule 6(1) / FSSAI 2.2.2)

$$\text{Applicable Denominator} = 11 - 2 = 9$$

---

## 8. Specific Declaration Assessments

### 8.1 Manufacturer / Packer Address Assessment (Section 7)
* **Raw Extracted Value:** `"195/2A,, B.D. SAWANT, FOODS LIMITED,"`
* **Ground Truth:** `195/2A, B.D. Sawant Foods Ltd, Kudus, Tal. Wada, Dist. Palghar - 421312, Maharashtra`
* **Legal Requirement:** Rule 6(1)(a) requires the name and complete postal address of the manufacturer/packer, including postal district, state, and PIN code.
* **Finding:** The extracted text ends abruptly with a comma, contains consecutive commas (`,,`), and completely lacks city, district, state, or 6-digit PIN code.
* **Resolution:** Truthfully marked `REVIEW_REQUIRED`. Marking this fragment `VERIFIED` would violate statutory requirements.

### 8.2 Maximum Retail Price (MRP) Assessment (Section 8)
* **Raw Extracted Value:** `"₹420"`
* **Ground Truth:** `₹420.00 (Incl. of all taxes)`
* **Confidence:** `0.17`
* **Finding:** While the digits `420` were located, the currency symbol and surrounding context had low OCR glyph confidence (0.17), well below the 0.55 threshold.
* **Resolution:** Truthfully retained as `REVIEW_REQUIRED`.

### 8.3 Unit Sale Price (USP) Assessment (Section 8)
* **Raw Extracted Value:** `"₹2.8/g"`
* **Ground Truth:** `₹2.80/g` (calculated as $\text{₹}420 / 150\text{g} = \text{₹}2.80\text{/g}$)
* **Confidence:** `0.42`
* **Finding:** Unit Sale Price under Rule 6(11) requires arithmetic corroboration against declared MRP. Because the detected MRP is unverified (confidence 0.17), the Rule Engine cannot certify the unit sale price without human confirmation.
* **Resolution:** Truthfully retained as `REVIEW_REQUIRED`.

### 8.4 Net Quantity Assessment (Section 10)
* **Raw Extracted Value:** `"150 g"`
* **Confidence:** `0.90`
* **Finding:** The historical bug where `150 g` was misread as `1509` and collapsed into a fabricated fallback of `1.0 unit` is completely eliminated. The value `150 g` is extracted with 0.90 confidence and verified against Rule 6(1)(e).
* **Resolution:** Marked `VERIFIED`.

### 8.5 Common / Generic Name Assessment (Section 9)
* **Raw Extracted Value:** `"FLAVOURED INSTANT COFFEE-CHICORY MDX"`
* **Confidence:** `0.75`
* **Finding:** Text identifies the commodity as coffee-chicory mixture, matching the food category requirements under Rule 6(1)(b).
* **Resolution:** Marked `VERIFIED`.

### 8.6 Manufacturing Date (PKD) & Use By Date Assessment (Section 5)
* **Raw Extracted Values:** PKD = `13/05/26`, USE BY = `12/10/27`
* **Confidences:** PKD composite = `0.63`, USE BY = `0.96`
* **Finding:** The generalized date association engine correctly maps each date to its semantic label, protects against collision with `2.80/g`, and confirms chronological order ($13/05/2026 < 12/10/2027$).
* **Resolution:** Both dates are marked `VERIFIED`.

### 8.7 Consumer Care Details Assessment (Section 9)
* **Raw Extracted Value:** `"bake, PRES: 1800-10-22-2"`
* **Confidence:** `0.36`
* **Finding:** OCR captured the telephone prefix but truncated the number (`1800-10-22-2` instead of `1800-10-22-221`), and the email/address was noisy.
* **Resolution:** Truthfully retained as `REVIEW_REQUIRED`.

### 8.8 Batch Number Assessment (Section 9)
* **Raw Extracted Value:** `"HF 130526 17:08"`
* **Confidence:** `0.52`
* **Finding:** OCR extracted the batch/lot code accurately, but the raw character confidence (0.52) is marginally below the 0.55 threshold.
* **Resolution:** Retained as `REVIEW_REQUIRED`.

---

## 9. RAG Grounding & Rule Engine Architecture (Section 11)

The platform adheres to strict separation of concerns:
```
[Statutory Knowledge Base] (PDFs, Acts, Gazettes)
         ↓
  RAG Retrieval (Dense/Hybrid Search)
         ↓
[Grounded Statutory Standards & Citations] (Provisions, Effective Dates, Thresholds)
         ↓
[Deterministic Rule Engine] (autoritative evaluation of evidence)
         ↓
[Final Inspection Findings & Canonical Declarations]
```

* **Grounding Only:** RAG never outputs PASS/FAIL decisions; it retrieves applicable legal clauses (e.g. Rule 6(1)(d) proviso, GSR 779(E)).
* **Authoritative Evaluation:** The deterministic Rule Engine (`backend/rule_engine.py`) performs all mathematical, threshold, and status decisions.
* **Temporal Safety:** Omitted provisions (Rule 5 standard pack sizes) are not treated as active obligations for modern inspections.

---

## 10. Real-Photo Benchmark Validation (Section 12)

Running `python backend/tools/eval_pipeline.py` across the 6 ground-truth photo datasets produced zero regressions and validated generalized performance:

```
======================================================================
LEGAL METROLOGY DECLARATION PIPELINE EVALUATION
======================================================================
--- 1. REAL PHOTOS GROUND TRUTH BENCHMARK ---
  [1/6] Bru Instant Coffee-Chicory 150g jar (Panel 1) ... Processed
  [2/6] Bru Instant Coffee-Chicory 150g jar (Panel 2) ... Processed
  [3/6] Vaseline Healthy Bright body lotion 200ml     ... Processed
  [4/6] Kellogg's Potato Crisps Pizza Flavour tube    ... Processed
  [5/6] SW-999 precision screwdriver set (blister)    ... Processed
  [6/6] Doraemon confectionery surprise ball          ... Processed

Total Scored: 27
Overall Accuracy: 55.6%
Overall Precision: 50.0%
Field Highlights:
  - mrp:              Precision 100.0%
  - consumer_care:    Precision 100.0%, Recall 100.0%
  - net_quantity:     Recall 100.0%

--- 2. MULTI-SURFACE AGGREGATION (BRU JAR PANELS 1 & 2) ---
Overall Status:        UNCERTAIN (Review Required)
Total Declarations:    11
Has Duplicates:        False
Applicable:            9
Detected:              9
Verified:              4
Review Required:       5
Non-Compliant:         0
======================================================================
```

---

## 11. Regression Tests for Status Propagation (Section 13)

Added test module: `backend/tests/test_declaration_verification_propagation.py` covering requirements A through J:

| Test ID | Test Name | Invariant Covered | Result |
| :---: | :--- | :--- | :---: |
| **A** | `test_a_all_applicable_declarations_verified` | All applicable declarations VERIFIED $\rightarrow$ count = 9/9 (100%). | **PASS** |
| **B** | `test_b_mixed_verified_and_review_required` | Mixed 4 VERIFIED + 5 REVIEW_REQUIRED $\rightarrow$ exact counts preserved. | **PASS** |
| **C** | `test_c_not_applicable_fields_excluded_from_denominator` | Rule 5 and imported origin excluded from denominator (11 total, 9 applicable). | **PASS** |
| **D** | `test_d_exempt_fields_presentation` | Non-applicable declarations carry `compliant = True` validation. | **PASS** |
| **E** | `test_e_uncertain_fields_not_counted_as_verified` | Low-confidence or unevidenced declarations never counted as VERIFIED. | **PASS** |
| **F** | `test_f_backend_verified_maps_to_frontend_verified` | Backend `CanonicalStatus.VERIFIED` serializes to `"VERIFIED"`. | **PASS** |
| **G** | `test_g_backend_review_required_maps_properly` | Backend `REVIEW_REQUIRED` serializes truthfully to `"REVIEW_REQUIRED"`. | **PASS** |
| **H** | `test_h_api_and_pdf_status_consistency` | API JSON and PDF report share identical verified/applicable count. | **PASS** |
| **I** | `test_i_duplicate_declarations_deduplicated` | Invariant: `len(declarations) == len(set(d.field for d in declarations))` holds across multiple surface captures. | **PASS** |
| **J** | `test_j_missing_evidence_review_required_never_fabricated` | Unobserved declarations result in `NOT_DETECTED`, never fabricated fallbacks. | **PASS** |
| **K** | `test_k_manufacturer_partial_address_not_verified` | Incomplete/mangled company addresses ending in comma or lacking PIN/state fail verification. | **PASS** |

---

## 12. Full Pytest Suite Result

Executing the full automated test suite:
```powershell
python -m pytest backend/tests/
```
**Outcome:**
```
================ 466 passed, 18 skipped, 5 warnings in 20.20s =================
```
* **Passed:** 466 tests
* **Failed:** 0 tests
* **Regressions:** None

---

## 13. Final Acceptance Verification Summary

| Metric | Target | Result | Status |
| :--- | :---: | :---: | :---: |
| **Backend Verified Count** | Truthful evidence-based score | 4 / 9 | **AGREED** |
| **Frontend Verified Count** | Matches backend canonical finding | 4 / 9 | **AGREED** |
| **PDF Verified Count** | Matches backend & frontend finding | 4 of 9 (44%) | **AGREED** |
| **Denominator** | Only applicable declarations | 9 (excludes Rule 5 & origin) | **AGREED** |
| **150 g Quantity** | Preserved from OCR; no 1.0 unit | 150 g (conf 0.90) | **PASS** |
| **PKD Date** | Associated with PKD label | 13/05/26 (conf 0.63) | **PASS** |
| **USE BY Date** | Associated with USE BY label | 12/10/27 (conf 0.96) | **PASS** |
| **Date Collision Protection** | 2.80/g protected from date engine | Preserved as USP | **PASS** |
| **Mangled Address Protection** | Mangled company fragment flagged | REVIEW_REQUIRED | **PASS** |
| **RAG Role** | Grounding only; Rule Engine authoritative | Grounding only | **PASS** |

---

## 14. Remaining Genuine Limitations

1. **Broken Currency Glyphs in OCR:**
   Extremely small or stylized currency symbols (such as the Rupee sign `₹` on curved surfaces) yield lower raw OCR confidence ($\approx 0.17$), requiring human inspection even when numerical digits are recognizable.
2. **Partial Contact Information:**
   Small-print consumer care panels with multiple lines of text across cylindrical curves can suffer line truncation. The system correctly leaves these for reviewer confirmation.
3. **Manufacturer Multi-Line Segmentation:**
   When an address spans 4 lines with variable line wraps and comma splices, OCR may recover only the entity name and building number while losing the PIN code. The Rule 6(1)(a) guard safeguards the system by flagging such incomplete extractions.
