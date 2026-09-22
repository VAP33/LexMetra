# PRODUCTION LINE INTEGRATION: CANONICAL RUNTIME ARCHITECTURE

## 1. Canonical Production Flow

The canonical production pipeline integrates all verified capabilities into a single, cohesive, non-duplicative execution path:

```
                          Inspection Request (/scan or /sessions)
                                            │
                                            ▼
                           Product Classification & Context
                    (Category, Commodity, Sale Type, Net Qty Hint)
                                            │
                                            ▼
                                  Surface Capture(s)
                              (Front, Back, Side Panels)
                                            │
                                            ▼
                                Image Quality Assessment
                                            │
                                            ▼
                          Geometry / PDP Area / Calibration
                            (Bounding Box, Shape, Aspect)
                                            │
                                            ▼
                                    Barcode Decoding
                                  (GTIN-13 / EAN / QR)
                                            │
                                            ▼
                            Region Detection & Prioritization
                          (Max 24 regions, prioritized text)
                                            │
                                            ▼
                               Orientation Rectification
                                 (PP-LCNet doc_ori 0/90/180/270)
                                            │
                                            ▼
                                 OCR Engine Execution
                         (PaddleOCR PP-OCRv6 + Tesseract Fallback)
                                            │
                                            ▼
                               Field Classification
               (Manufacturer, Marketer, MRP, Net Qty, Dates, Care, USP)
                                            │
                                            ▼
                         Claude 2 Split-Field Reconstruction
                       (Cross-surface label + fragment fusion)
                                            │
                                            ▼
                            Cross-Surface Evidence Fusion
                       (Merge observations, stamp provenance)
                                            │
                                            ▼
                                   Canonical Facts
                         (Deduplicated, typed, evidence-backed)
                                            │
                                            ▼
                              Regulatory Scope Engine
                       (Determine LMPC vs FSSAI vs CDSCO/Cosmetics)
                                            │
                                            ▼
                                  RAG Legal Knowledge
                   (Retrieve statutory provisions, clauses, versions)
                                            │
                                            ▼
                          Applicable Rules + Version Registry
                      (Check effective dates against inspection date)
                                            │
                                            ▼
                           Deterministic Rule Engine
                     (Evaluate evidence against legal thresholds)
                                            │
                                            ▼
                           Legal Metrology Rule Findings
                      (PASS / FAIL / UNCERTAIN / EXEMPT)
                                            │
                                            ▼
                              Persistence & Audit Trail
                         (PostgreSQL products/inspections)
                                            │
                                            ▼
                          Evidence-Backed Report Generation
                       (PDF with grounded provisions & citations)
                                            │
                                            ▼
                              Frontend Response & UI
                         (React UI, Declaration review queue)
```

---

## 2. Decision Boundaries & Architecture Safeguards

### A. RAG vs. Rule Engine Boundary
1. **RAG Scope**: Answers the question: *"Which legal provisions, versions, clauses, and evidence requirements are relevant to this product, packaging, and date?"*
   - RAG provides: `LegalKnowledgeResult` containing `module`, `regulation`, `rule_id`, `rule_version`, `effective_date`, `applicability`, `evidence_requirements`, and `source_reference`.
   - RAG **NEVER** decides compliance verdicts (PASS/FAIL).
2. **Rule Engine Scope**: Answers the question: *"Given the verified evidence and the applicable statutory provision, does the package satisfy the legal requirement?"*
   - The deterministic Rule Engine (`backend/rule_engine.py`) remains 100% authoritative for all legal decisions.
   - Evaluates numeric thresholds, mandatory declaration presence, character height requirements, and date formats deterministically.

### B. Safe Fallback Behavior
- **If RAG is unavailable or fails**: Fallback grounding supplies standard active LMPC rules with `REVIEW_REQUIRED` grounding status. The deterministic Rule Engine continues without crash.
- **If PaddleOCR is unavailable**: Tesseract OCR automatically continues with region-first processing.
- **If Split-field reconstruction is ambiguous**: Flags `UNCERTAIN / REVIEW_REQUIRED` with detailed explanation. Never guesses values.
- **If Quantity is absent**: Remains `None` / `not_observed`. Never fabricated as `1.0 unit`.
- **If Dates are contradictory**: Enforces physical chronology check (`mfg_date <= expiry_date`). If ambiguous, returns `REVIEW_REQUIRED`.
- **If OCR conflicts**: Downgrades confidence and records alternative readings in `alternative_values`.

---

## 3. Provenance & Traceability Guarantee

Every declaration fact surviving to the API and report preserves:
1. `image_id`: Original filename of the photograph.
2. `surface_id`: Specific surface identifier (Front, Back, Side).
3. `bbox`: Integer pixel coordinates `(x, y, w, h)` in the original image.
4. `confidence`: Extractor confidence score.
5. `raw_text`: Exact uncorrected text extracted by OCR.
6. `normalized_value`: Normalized date or monetary value.
7. `status`: Extraction and verification state (`DETECTED`, `VERIFIED`, `UNCERTAIN`, `REVIEW_REQUIRED`).
8. `rule_id` and `applicable_rule_version`: Grounded statutory provision applied during legal evaluation.
9. `citations`: Direct reference to the gazette or rules document (e.g. `rules.json:LMPC-2011-R6-DECLARATIONS`).
