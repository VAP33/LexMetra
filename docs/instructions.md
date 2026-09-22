# LEXMETRA MASTER ENGINEERING INSTRUCTIONS & IMPLEMENTATION BLUEPRINT
**India Legal Metrology Packaged Commodities Compliance Engine**
**Authoritative Ground-Truth Audit, Generalized Reasoning Architecture, and Phased Roadmap**
*Generated: 2026-09-12 | Version: 2.0 (Post-Audit Amendments Incorporated)*

---

## 0. MASTER ARCHITECTURAL AMENDMENTS & GOVERNING CONSTRAINTS

Before any implementation, the following fifteen mandatory architectural amendments govern all subsystems:

1. **Regression Fixtures, Not Blind Ground Truth:**
   The 9 images in `images new/` (`BRU`, `GOOD KNIGHT`, `TRAYA`, `VASELINE`) are real-world regression fixtures. Expected declarations are verified directly from visible package pixels, not blindly assumed.
2. **Evidence-Driven Surface Priority (No Hardcoded "BACK"):**
   Surface priority is dynamically determined by regulatory declaration density:
   $$\text{PriorityScore}(S) = \sum_{f \in \text{RegulatoryDeclarations}} w_f \cdot \text{EvidenceConfidence}(f, S)$$
   Surfaces with higher evidence density receive inspection priority. `BACK`, `FRONT`, or upload order are never hardcoded as inherently primary.
3. **Heterogeneous Declaration Graph (Beyond Pure Bipartite Matching):**
   The declaration graph models heterogeneous relationships:
   - **1 : 1** relationships (e.g., Net Quantity Label $\leftrightarrow$ Value, MRP Label $\leftrightarrow$ Value)
   - **1 : N** relationships (e.g., Manufacturer Role $\rightarrow$ Company Name + Address Lines + Pin Code)
   - **Structured / Compound** relationships (e.g., MRP $\leftrightarrow$ Value + Tax Qualifier `(Incl. of all taxes)`)
   Bipartite matching is used solely as a solver for 1:1 subproblems within a declaration block.
4. **No Premature Candidate Consumption:**
   During candidate value generation, candidate OCR lines are **never** consumed (`used_line_idx` is forbidden during candidate discovery). All plausible interpretations are retained until global resolution.
5. **Abstention-Aware Global Resolution:**
   Resolution is not winner-take-all. If the margin between the top two hypotheses is below an ambiguity threshold, or if the top affinity score is below acceptable confidence, the engine **abstains** and yields `UNCERTAIN` / `REVIEW_REQUIRED`.
6. **Explicit Sequence Reasoning Signal:**
   Sequence is an explicit, weighted signal integrated alongside spatial proximity, semantic type compatibility, numerical format, unit consistency, block clustering, and regulatory expectations.
7. **Explainable Provenance & Candidate Alternatives:**
   Every resolved declaration persists:
   - The selected value and its bounding box
   - Competing candidate alternatives
   - The full score breakdown (spatial, sequence, format, semantic, block)
   - The reasoning explaining why the candidate was selected or why the engine abstained
8. **Cross-Surface & Cross-Declaration Contradiction Detection:**
   The engine actively flags contradictions (e.g., conflicting prices across panels, net quantity discrepancies, dates where manufacturing succeeds expiry). Contradictions yield explicit `CONFLICTING` evidence states rather than silent averaging.
9. **Structured Temporal Evidence (Separation of Evidence and Law):**
   Temporal reasoning parses dates, durations, and anchors into structured `TemporalEvidence` (manufacturing date, relative duration, anchor, derived endpoint). Legal compliance (Rule 6(1)(c) and Rule 6(1)(d)) remains exclusively within `rule_engine.py`.
10. **Multi-Surface Attribution & Source Image Preservation:**
    When declarations are aggregated at the inspection level, each declaration retains attribution to its exact source image and surface ID. Raw captures are immutable.
11. **Rigorous Coordinate Spaces & Homography Tracking:**
    Coordinates explicitly declare their reference frame:
    - `ORIGINAL_PIXEL`: Raw camera photograph dimensions
    - `CANONICAL_RECTIFIED`: Perspective-corrected, cropped, upright coordinate space
    - `OCR_EXTRACTED`: Coordinate space returned by the OCR engine
    - `DISPLAY_PERCENT`: Normalized [0, 100]% coordinates for web rendering
    Forward and inverse transformation matrices ($H, H^{-1}$) are preserved for bidirectional mapping.
12. **Full-Trace Evidence Persistence Model:**
    Database persistence strictly models the ten-layer evidence chain:
    $$\text{Inspection} \rightarrow \text{Surface} \rightarrow \text{ImageAsset} \rightarrow \text{Transformation} \rightarrow \text{OCR} \rightarrow \text{EvidenceRegion} \rightarrow \text{Declaration} \rightarrow \text{Association} \rightarrow \text{Rule} \rightarrow \text{Finding}$$
13. **Generalized Reasoning (No Package-Specific Hacks):**
    The Traya expected output (`MRP = ₹800`, `USP = ₹26.67/ml`, `MFD = 03/2026`, `Batch = C26HN005`) must emerge naturally from generalized principles (unit rate discrimination, block sequence, character confusion repair, global consistency). No hardcoded strings, filenames, or coordinate shortcuts are permitted.
14. **Universal Packaging Standards:**
    All heuristics and algorithms must be domain-general across food, beverage, personal care, and household commodities.
15. **Subsystem Regression Protocol:**
    After each subsystem is implemented, the complete `images new/` dataset must be re-run and verified against the established BEFORE baseline.

---

## 1. RUNTIME FLOW: ACTUAL VS TARGET

### 1.1 Current Actual Execution Flow (Code Trace)

```
[UPLOAD / WEBCAM] (Raw JPEG/PNG)
       │
       ▼
main.py: _read_image_upload()
       │ Decodes raw bytes to np.ndarray and PIL.Image
       │ No boundary detection, No perspective rectification, No chrome crop
       │
       ▼
main.py: Evidence Retention
       │ Saves raw bytes to uploads/<uuid>_<filename>
       │
       ▼
ocr_extraction.py: run_ocr(pil_img)
       │ 1. Whole-image OCR: _run_ocr_whole_image()
       │    Runs Tesseract 2x PSM (6, 11) on 3 variants (RGB, enlarged, autocontrast) = 6 passes
       │ 2. Region-first OCR: ocr_engine.read_image(bgr)
       │    Runs region_detection.py -> orientation.py -> Tesseract/Paddle ensemble
       │ 3. _dedupe_lines() merges bounding boxes via IoU >= 0.35
       │
       ▼
ocr_extraction.py: classify_fields(ordered_ocr_lines)
       │ 1. Scans lines for FIELD_PATTERNS (regex) to find label lines
       │ 2. GREEDY candidate association: _candidate_value_lines()
       │    Sorts by vertical distance dy, same_row, right_side
       │    FIRST match wins -> used_line_idx.add(j)
       │    *CRITICAL FAILURE POINT: MRP greedily steals ₹26.67/ml!*
       │ 3. date_association.py: associate_date_fields()
       │    Runs bipartite matching on date candidates
       │    *CRITICAL FAILURE POINT: Anchors to "MFG" at y=1199 instead of "MFG. DATE" at y=2524*
       │
       ▼
main.py: _infer_applicability_context() & _resolve_quantity() & _resolve_mrp()
       │ Resolves numbers; falls back to form inputs
       │
       ▼
rule_engine.py: run_inspection()
       │ Evaluates rules.json sequentially:
       │  - Rule 3 (Scope)
       │  - Rule 26 (Small package exemptions)
       │  - Rule 6(1) Mandatory Declarations (a, b, c, d, e, f, g)
       │  - Rule 6(11) Unit Sale Price
       │  - Rule 7 (PDP area & font height)
       │ Returns ProductInspection (status: PASS/FAIL/UNCERTAIN/EXEMPT)
       │
       ▼
db/persistence.py: save_inspection()
       │ Inserts into inspections, inspection_facts, inspection_findings
       │ Stores declarations_json JSONB
       │
       ▼
FastAPI response -> React App (InspectionApp.tsx)
       │ Displays Summary, Declarations table, Issues list, AI signals
       │ View Evidence renders bounding boxes on the original photo
```

### 1.2 Target Architectural Flow

```
CAMERA / MULTI-IMAGE UPLOAD
            │
            ▼
[STAGE 1: CANONICAL SURFACE NORMALIZATION]
  - Background separation / Letterbox stripping (geometry.py)
  - Package boundary contour detection & quadrilateral fitting
  - Perspective rectification (homography warp to frontal plane)
  - Canonical orientation normalization (0°, 90°, 180°, 270°)
  - Illumination normalization & CLAHE enhancement
  - Track forward/inverse homography matrices: H, H_inv
  - Output: CanonicalSurface(original, rectified, enhanced, H, H_inv)
            │
            ▼
[STAGE 2: MULTI-SURFACE REGULATORY PRIORITIZATION]
  - Compute text density & declaration keyword density per surface
  - Dynamic PriorityScore(S) = sum(w_f * Conf(f, S))
  - Surfaces ranked dynamically by evidence density (never hardcoded "BACK")
  - Aggregate surfaces into unified InspectionEvidenceSet
            │
            ▼
[STAGE 3: MULTI-ENGINE OCR & BARCODE EXTRACTION]
  - Tesseract (PSM 6, 11) + PaddleOCR ensemble on canonical surfaces
  - Barcode / QR machine decoding (cv2.barcode + pyzbar)
  - Output: Stream of OcrToken, OcrLine, BarcodeSymbol with exact bboxes
            │
            ▼
[STAGE 4: LAYOUT GRAPH & DECLARATION BLOCK FORMATION]
  - Spatial adjacency analysis (horizontal lines, vertical columns, gutters)
  - Group lines into DeclarationBlocks:
      * Price/Pack Block (MRP, USP, Net Qty, Batch, MFD, Best Before)
      * Company/Address Block (Manufacturer, Marketer, Addresses, Pin)
      * Consumer Care Block (Helpline, Email, Phone)
            │
            ▼
[STAGE 5: HETEROGENEOUS DECLARATION GRAPH & RESOLVER]
  - Candidate generation without premature consumption (NO used_line_idx)
  - Specialized Semantic Parsers:
      * MoneyParser: Distinguishes plain ₹800 from unit rate ₹26.67/ml
      * DateParser: Resolves calendar dates and relative shelf-life durations
      * BatchParser: Tolerant to OCR glyph confusion (O/0, I/1, S/5, B/8, H/N)
      * RoleParser: Multi-line address continuation (1:N graph mapping)
  - Multi-Signal Scoring:
      * Spatial proximity + Row alignment + Sequence consistency +
        Semantic type match + Unit compatibility + Block membership
  - Heterogeneous Graph Solver:
      * 1:1 subproblems solved via Hungarian algorithm / constrained search
      * 1:N subproblems solved via role continuation clustering
      * Contradiction detection across declarations and surfaces
      * Abstention support: Yields UNCERTAIN when confidence/margin is low
  - Explanations & Alternatives: Persists top alternative candidates and scores
            │
            ▼
[STAGE 6: STRUCTURED TEMPORAL EVIDENCE ENGINE]
  - Normalizes temporal evidence:
      MFD (03/2026) + Duration (24 months) -> Derived Endpoint (03/2028)
  - Generates structured TemporalEvidence object
  - Hands evidence to rule engine (engine retains legal verdict responsibility)
            │
            ▼
[STAGE 7: DETERMINISTIC LEGAL VALIDATION (rules.json)]
  - Evaluates applicable rules against structured declarations
  - Produces RuleFinding: PASS | FAIL | UNCERTAIN | EXEMPT
  - Decomposed Confidence: OCR Conf x Spatial Conf x Semantic Conf
            │
            ▼
[STAGE 8: AUDITABLE PERSISTENCE & BIDIRECTIONAL EVIDENCE VIEWER]
  - 10-layer evidence graph persisted to PostgreSQL
  - Full coordinate space transformation mapping (ORIGINAL <-> CANONICAL <-> DISPLAY)
  - Bidirectional UI Navigation: Finding -> Region AND Region -> Declaration -> Rule
```

---

## 2. EXISTING CAPABILITY INVENTORY (AUDIT CLASSIFICATION)

Each capability in the repository is classified into:
- **A**: Fully implemented and actively used in production.
- **B**: Implemented, but partially wired / disconnected in runtime flow.
- **C**: Implemented, but incorrect or incomplete in logic.
- **D**: Present in codebase, but dead / unreferenced.
- **E**: Completely missing.

### 2.1 Computer Vision & Preprocessing
| Capability | Status | Location | Notes |
|---|:---:|---|---|
| Package/Document boundary detection | **B** | `backend/geometry.py:174`, `backend/preprocess.py:40` | Fully implemented using contour hierarchy & approxPolyDP, but **never executed in `/scan` before OCR**. |
| Content crop / letterbox removal | **B** | `backend/geometry.py:123`, `backend/preprocess.py:461` | Implemented in tests and `region_detection.py`, but skipped in main pipeline. |
| Perspective correction (Homography) | **B** | `backend/geometry.py:270` (`rectify_perspective`) | Computes inverse warp perspective matrix. Unwired in `/scan`. |
| Rotation / Orientation detection | **B** | `backend/orientation.py` (Hough + projection profile) | Only invoked inside `ocr_engine.py` per text region, not for canonical package surface. |
| Illumination normalization / CLAHE | **B** | `backend/preprocess.py:320` (`_apply_clahe`, `ILLUMINATION_NORMALIZE`) | Implemented as recipe steps in `preprocess.py`; main pipeline passes raw PIL image. |
| Blur / Glare detection | **A** | `backend/image_quality.py:38` | Actively used in `/scan` and `/sessions` to compute quality scores. |
| Canonical surface acquisition | **E** | — | **Missing.** Raw photo is treated directly as canonical surface. |

### 2.2 OCR & Layout Analysis
| Capability | Status | Location | Notes |
|---|:---:|---|---|
| Whole-image OCR ensemble | **A** | `backend/ocr_extraction.py:282` | Tesseract with PSM 6 & 11 across 3 variants. Actively runs. |
| Region-first OCR | **A** | `backend/ocr_engine.py:1722` (`read_image`) | Text region detection + per-region orientation + fusion. Actively runs when enabled. |
| PaddleOCR integration | **A** | `backend/paddle_worker.py`, `backend/ocr_engine.py` | Local PaddleOCR fallback/ensemble is wired and operational. |
| Line grouping & Bounding boxes | **A** | `backend/ocr_extraction.py:99` | Preserves word/line bboxes in original coordinates. |
| Declaration Block detection | **E** | — | **Missing.** Lines are treated as an unordered list; no layout graph grouping related declarations. |
| Layout Graph representation | **E** | — | **Missing.** Spatial relationships are computed on the fly via pairwise Euclidean distances. |

### 2.3 Semantic Association & Extraction
| Capability | Status | Location | Notes |
|---|:---:|---|---|
| Greedy spatial label-value matching | **C** | `backend/ocr_extraction.py:845` (`_candidate_value_lines`) | **Critically flawed.** Picks nearest numerical line regardless of units/block structure. |
| Date association engine | **C** | `backend/date_association.py` | Implements bipartite matching, but vulnerable to false label anchors (e.g., license `MFG`). |
| Relative shelf-life parsing | **C** | `backend/date_association.py:137`, `ocr_extraction.py:488` | Parses text string ("24 months from mfd"), but **does not derive absolute endpoint** or link to MFD. |
| MRP / USP semantic separation | **C** | `backend/ocr_extraction.py:418`, `573` | Treats both as generic monetary matches. Lacks denominator verification for MRP. |
| Batch / Lot code parsing | **C** | `backend/ocr_extraction.py:1046` | Too rigid for dot-matrix OCR errors (0/O, 1/I, 5/S, 8/B). No fuzzy repair. |
| Role-aware manufacturer/marketer | **C** | `backend/ocr_extraction.py:1116` | Slices lines arbitrarily (+1 to +4); breaks on multi-company addresses or inline headings. |
| Heterogeneous declaration graph | **E** | — | **Missing.** Supports 1:1, 1:N, compound associations, and abstention. |

### 2.4 Legal Rules & Regulatory Reasoning
| Capability | Status | Location | Notes |
|---|:---:|---|---|
| Deterministic legal evaluation | **A** | `backend/rule_engine.py` | Comprehensive implementation of Rules 3, 5, 6, 7, 8, 9, 24, 26. |
| Rule 6(11) Unit Sale Price arithmetic | **A** | `backend/unit_price.py` | Precise Decimal math for standard unit prices across mass, volume, length, and count. |
| Structured temporal evidence | **E** | — | **Missing.** Temporal resolution must produce structured evidence for the rule engine. |
| Cross-surface contradiction check | **C** | `backend/capture_session.py:114` | Partial numeric conflict check; lacks cross-declaration semantic contradiction checks. |

---

## 3. REAL-WORLD REGRESSION FIXTURES AUDIT (`images new/`)

Physical inspection of the 9 regression fixtures in `images new/`:

| Image Filename | Physical Product | Resolution | Aspect Ratio | Physical Layout & Verified Expected Declarations |
|---|---|:---:|:---:|---|
| **`BRU FRONT.jpg`** | Bru Instant Coffee 150g Jar | 1080 × 2392 | Portrait (0.45) | Marketing face: Brand logo, "Instant Coffee-Chicory Mix". Zero legal declarations. |
| **`BRU BACK.jpg`** | Bru Instant Coffee 150g Jar | 1080 × 2392 | Portrait (0.45) | Two-column panel: `MRP = ₹420`, `Batch = HF 130526`, `MFD = 13/05/26`, `Use By = 12/10/27`, `USP = ₹2.80/g`. |
| **`BRU BACK 2.jpg`** | Bru Instant Coffee 150g Jar | 1080 × 2392 | Portrait (0.45) | Manufacturer panel: `Net Quantity = 150g`, `Hindustan Unilever Ltd`, Consumer care toll-free. |
| **`GOOD KNIGHT FRONT.jpg`** | Good Knight Liquid Vaporizer | 1080 × 2392 | Portrait (0.45) | Marketing face: "Good Knight Gold Flash". Zero mandatory declarations. |
| **`GOOD KNIGHT BACK.jpg`** | Good Knight Liquid Vaporizer | 1080 × 2392 | Portrait (0.45) | Declaration block: `MRP = ₹50`, `Batch = AA260411`, `Expiry = 2 years`, `Godrej Consumer Products Ltd`. |
| **`TRAYA FRONT.jpg`** | Traya Hair Actives 30ml | 1856 × 4096 | Portrait (0.45) | Marketing front: "TRAYA Hair Actives 30ml". Common name and volume only. |
| **`TRAYA BACK.jpg`** | Traya Hair Actives 30ml | 1856 × 4096 | Portrait (0.45) | Primary declaration block: MFD 03/2026, MRP ₹800.00, USP ₹26.67/ml, Batch C26HN005, Net Volume 30ml, Manufacturer, Marketer, Consumer care. |
| **`VASELINE FRONT.jpg`** | Vaseline Body Lotion | 2392 × 1080 | Landscape (2.21) | **Rotated 90°**. Minimal declarations. |
| **`VASELINE BACK.jpg`** | Vaseline Body Lotion | 2392 × 1080 | Landscape (2.21) | **Rotated 90°**. Curved back panel: `Net Wt = 24g`, `Country = India`, HUL details. |

---

## 4. BEFORE-STATE BASELINE EXECUTION RESULTS

Baseline execution on all 9 images (persisted in `baseline_images_new.json`):

```
====================================================================================================
IMAGE: BRU FRONT.jpg (Lines: 37 | Time: 17.7s)
  common_name               : DETECTED        conf=0.55 val="? Instant"
----------------------------------------------------------------------------------------------------
IMAGE: BRU BACK.jpg (Lines: 139 | Time: 24.7s)
  mrp                       : DETECTED        conf=0.17 val="₹420"
  batch_no                  : DETECTED        conf=0.52 val="HF 130526 17:08"
  mfg_date                  : DETECTED        conf=0.63 val="13/05/26"
  expiry_date               : DETECTED        conf=0.96 val="12/10/27"
  unit_sale_price           : DETECTED        conf=0.42 val="₹2.8/g"
----------------------------------------------------------------------------------------------------
IMAGE: BRU BACK 2.jpg (Lines: 194 | Time: 34.5s)
  net_quantity              : DETECTED        conf=0.90 val="150 g"
  common_name               : DETECTED        conf=0.75 val="FLAVOURED INSTANT COFFEE-CHICORY MIX"
  manufacturer_name         : OK              conf=0.78 val="195/2A, B.D. SAWANT, FOODS LIMITED"
  marketer_name             : OK              conf=0.62 val="HINDUSTAN UNILEVER HOUSE, ANDHERI"
  consumer_care             : OK              conf=0.36 val="1800-10-22-221"
----------------------------------------------------------------------------------------------------
IMAGE: GOOD KNIGHT FRONT.jpg (Lines: 87 | Time: 19.0s)
  [NO DECLARATIONS DETECTED]
----------------------------------------------------------------------------------------------------
IMAGE: GOOD KNIGHT BACK.jpg (Lines: 261 | Time: 20.0s)
  mrp                       : DETECTED        conf=0.82 val="₹50"
  expiry_date               : DETECTED        conf=0.90 val="2 years"
  manufacturer_name         : OK              conf=0.45 val="Godrej Consumer Products Ltd"
  consumer_care             : OK              conf=0.35 val="care@godrejcp.com"
  batch_no                  : REVIEW_REQUIRED conf=0.73 val=None
  mfg_date                  : REVIEW_REQUIRED conf=0.28 val=None
----------------------------------------------------------------------------------------------------
IMAGE: TRAYA FRONT.jpg (Lines: 60 | Time: 29.4s)
  [NO DECLARATIONS DETECTED]
----------------------------------------------------------------------------------------------------
IMAGE: TRAYA BACK.jpg (Lines: 139 | Time: 40.1s)
  mrp                       : DETECTED        conf=0.48 val="₹26.67"   <-- STOLE USP!
  unit_sale_price           : REVIEW_REQUIRED conf=0.22 val=None       <-- MISSING!
  batch_no                  : REVIEW_REQUIRED conf=0.90 val=None       <-- MISSING!
  mfg_date                  : REVIEW_REQUIRED conf=0.31 val=None       <-- MISSING!
  expiry_date               : DETECTED        conf=0.96 val="24 months"
  net_quantity              : OK              conf=0.80 val="Net Volume: 30ml"
  manufacturer_name         : DETECTED        conf=0.81 val="a |"       <-- TRUNCATED
  marketer_name             : DETECTED        conf=0.78 val="me"        <-- TRUNCATED
  consumer_care             : OK              conf=0.56 val="customercare@traya.health"
----------------------------------------------------------------------------------------------------
IMAGE: VASELINE FRONT.jpg (Lines: 54 | Time: 15.9s)
  [NO DECLARATIONS DETECTED - ROTATED 90 DEGREES]
----------------------------------------------------------------------------------------------------
IMAGE: VASELINE BACK.jpg (Lines: 103 | Time: 18.2s)
  country_of_origin         : OK              conf=0.64 val="MADE IN INDIA"
  net_quantity              : DETECTED        conf=0.84 val="24 g"
  mfg_date                  : REVIEW_REQUIRED conf=0.28 val=None
  expiry_date               : REVIEW_REQUIRED conf=0.30 val=None
  mrp                       : NOT DETECTED    conf=0.00 val=None
====================================================================================================
```

---

## 5. ROOT CAUSES OF THE TRAYA REGRESSION

| Field | Visible Package Value | System Baseline Output | Status | Technical Root Cause in Code |
|---|---|---|:---:|---|
| **MRP** | `₹800.00` | `₹26.67` | **FAIL** | `_extract_money` treats any decimal (`26.67`) as price. Greedy matching binds nearest value (dy=16px from label), stealing it from USP. |
| **USP** | `₹26.67/ml` | `None` | **FAIL** | Value `26.67` was consumed by MRP in `used_line_idx`. Unit denominator (`= perml:`) is decoupled. |
| **MFD** | `03/2026` | `None` | **FAIL** | Regex anchors to `MFG` in license text at y=1199 (1,300px away). True date `03-2026` at y=2524 orphaned into auxiliary dates. |
| **BATCH** | `C26HN005` | `None` | **FAIL** | Dot-matrix OCR noise (`c26Ho0s`) fails strict regex; line 78 matches label and blocks candidate line. |
| **EXPIRY** | `Use before 24 months` | `24 months` | **PASS (PARTIAL)** | Extracts duration string, but does not compute endpoint (`03/2028`) or link to MFD. |
| **MANUFACTURER** | Cheryl Laboratories Pvt Ltd | `"a |"` | **FAIL** | `_inline_label_value` extracts `"a |"`, executes early `continue`, bypassing multi-line address loop. |

---

## 6. TARGET COMPONENT SPECIFICATIONS

### 6.1 Heterogeneous Declaration Graph Architecture (`backend/declaration_graph.py`)
- **Block Formation:** Segments lines into spatial blocks by vertical gaps, horizontal bounds, and line heights.
- **Candidate Discovery Without Consumption:** Identifies all candidate labels and values. No candidates are consumed or removed.
- **Scoring Signals:**
  $$S(L, V) = w_{\text{spatial}} S_{\text{spatial}} + w_{\text{seq}} S_{\text{seq}} + w_{\text{type}} S_{\text{type}} + w_{\text{unit}} S_{\text{unit}} + w_{\text{block}} S_{\text{block}}$$
- **Constraint Matrix:**
  - Rate values (`amount/unit`) cannot bind to MRP.
  - Plain money values (`amount`) cannot bind to USP.
  - Alphanumeric codes cannot bind to date labels.
- **Heterogeneous Mapping:**
  - 1:1 subproblems resolved via Hungarian algorithm.
  - 1:N address blocks resolved via role continuation clustering.
  - Compound structures (MRP + Tax qualifier) grouped as single semantic entity.
- **Abstention Logic:** If $S(L, V_1) - S(L, V_2) < \delta_{\text{margin}}$ or $S(L, V_1) < \tau_{\text{confidence}}$, assign `UNCERTAIN` / `REVIEW_REQUIRED`.

### 6.2 Specialized Semantic Parsers (`backend/semantic_parsers.py`)
- **`MoneyValue`**: Encapsulates `amount: Decimal, currency: str, is_rate: bool, denominator: Optional[str]`.
- **`BatchParser`**: Performs character confusion repair (`c` -> `C`, `oo` -> `00`, `s` -> `5`) while retaining raw OCR text.
- **`DateValue`**: Encapsulates absolute dates and relative shelf-life durations.
- **`RoleParser`**: Gathers company names and multi-line addresses across continuation lines until the next structural boundary.

### 6.3 Structured Temporal Evidence Engine (`backend/temporal_reasoning.py`)
- Resolves anchor dates and relative durations:
  $$\text{DerivedEndpoint} = \text{MFD} + \text{DurationMonths}$$
- Produces structured `TemporalEvidence(mfg_date, best_before_duration, anchor, derived_endpoint, contradiction_flag)`.
- Hands evidence to `rule_engine.py` for deterministic legal validation under Rule 6(1)(c) and Rule 6(1)(d).

### 6.4 Canonical Image Normalization (`backend/geometry.py` & `backend/preprocess.py`)
- Background separation, letterbox strip, quadrilateral contour detection, homography perspective rectification, 90° orientation correction, and CLAHE.
- Tracks coordinate spaces: `ORIGINAL_PIXEL`, `CANONICAL_RECTIFIED`, `OCR_EXTRACTED`, `DISPLAY_PERCENT`.
- Forward/inverse homography matrices ($H, H^{-1}$) stored for bidirectional coordinate mapping.

### 6.5 Dynamic Multi-Surface Prioritization (`backend/main.py`)
- Computes declaration density per surface.
- Sorts and prioritizes surfaces dynamically based on regulatory evidence weight.
- Aggregates all surfaces into an `InspectionEvidenceSet` with full provenance.

### 6.6 Full-Trace Evidence Persistence Model (`backend/db/`)
- Persists the complete evidence chain:
  $$\text{Inspection} \rightarrow \text{Surface} \rightarrow \text{ImageAsset} \rightarrow \text{Transformation} \rightarrow \text{OCR} \rightarrow \text{EvidenceRegion} \rightarrow \text{Declaration} \rightarrow \text{Association} \rightarrow \text{Rule} \rightarrow \text{Finding}$$
- New `inspection_surfaces` table stores surface type, image paths, transformation matrices, and declaration density.

---

## 7. STEP-BY-STEP IMPLEMENTATION ROADMAP

### PHASE 1: Semantic Parsers & Heterogeneous Declaration Graph (P0)
1. Implement `backend/semantic_parsers.py` (Money, Rate, Batch, Date, Role parsers).
2. Implement `backend/declaration_graph.py` (Block formation, multi-signal scoring, heterogeneous graph resolver, abstention).
3. Implement `backend/temporal_reasoning.py` (Anchor resolution, derived endpoints, contradiction detection).
4. Refactor `backend/ocr_extraction.py` to delegate to the new architecture.
5. **Verify:** Unit tests in `test_semantic_parsers.py` and `test_declaration_graph.py`.

### PHASE 2: Canonical Image Normalization & Coordinate Spaces (P0)
1. Expose `normalize_package_surface()` in `backend/geometry.py`.
2. Connect `backend/preprocess.py` to produce `CanonicalSurface`.
3. Integrate canonical normalization into `backend/main.py` before OCR.
4. Save original and canonical image assets with homography metadata.
5. **Verify:** Test Vaseline 90° rotation correction and Traya perspective rectification.

### PHASE 3: Dynamic Multi-Surface Prioritization & Rule Engine Integration (P0)
1. Implement dynamic surface density scoring in `backend/main.py`.
2. Integrate `TemporalEvidence` and package structure context into `backend/rule_engine.py`.
3. Update `backend/db/schema.sql` and `backend/db/persistence.py` with `inspection_surfaces`.
4. **Verify:** Re-run `images new/` baseline; verify Traya and Bru multi-surface resolutions.

### PHASE 4: Frontend Evidence Viewer Overhaul (P1)
1. Update `InspectionApp.tsx` with surface tabs (`[Front] [Back] [Side]`).
2. Add view toggles (`[Original Capture] [Canonical Rectified] [OCR Regions]`).
3. Implement bidirectional evidence navigation (Finding $\leftrightarrow$ Bounding Box).
4. Display association rationale, score breakdown, and candidate alternatives.

### PHASE 5: Regression Verification & Acceptance Matrix (P0)
1. Run full test suite:
   - `test_declaration_pipeline.py`
   - `test_generalized_date_association.py`
   - `test_rule_engine.py`
   - New `test_master_regressions.py` (Cases A through N)
2. Execute end-to-end evaluation on `images new/` and compare against the BEFORE baseline.
