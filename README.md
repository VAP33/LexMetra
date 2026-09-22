# LexMetra — Legal Metrology Compliance Inspection Platform
> **Statutory Packaged-Commodity Verification & Enforcement System**  
> *Statutory Legal Metrology Compliance Authority*

---

## 1. Executive Summary

**LexMetra** is an enterprise-grade statutory compliance platform engineered for Legal Metrology officers, state controllers, and field inspectors across India. It automates the verification of mandatory declarations on pre-packaged commodities using high-speed multimodal computer vision, optical character recognition (OCR), and an uncompromising, deterministic statutory rule engine.

Unlike generic LLM wrappers that hallucinate legal determinations, LexMetra operates on a strict **evidence-first separation of concerns**:
- **Perception Layer**: High-speed multimodal perception (Gemini Flash Lite accelerated with local dual-engine OCR) extracts and normalizes textual, numeric, and geometric evidence from packaging surfaces.
- **Rule Engine Layer**: Evaluates extracted evidence against versioned statutory rules (`rules.json`, LMPC Rules 2011). Legal status (`PASS`, `FAIL`, `UNCERTAIN`, `EXEMPT`) is computed strictly through mathematical, dimensional, and lexical algorithms with complete statutory citations.
- **Package Integrity Layer**: Detects counterfeit packaging, illicit sticker overlays, price alterations, and unauthorized batch re-labeling.
- **Regulatory Cross-Verification**: Corroborates declarations against national databases including FSSAI (Food Safety and Standards Authority of India) license registries, BIS standards, and consumer grievance databases.

### 1.1. Live Multi-Cloud Deployment Matrix

| Service | Target Platform | Address / Endpoint | Status | Capabilities |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend Web App** | Vercel Edge CDN | `https://lexmetra-ui.vercel.app` | **Active / Deployed** | React 18 + Vite PWA; zero horizontal scroll; mobile menu drawer; sticky CTA |
| **Backend API Gateway** | Render Cloud / Local | `http://0.0.0.0:8000` | **Active** | FastAPI, Python 3.12, Uvicorn, Tesseract OCR, YOLOv8, Pyzbar |
| **Secure Field Tunnel** | Ngrok Public Tunnel | `https://rise-sponsor-juvenile.ngrok-free.dev` | **Active** | Forwards public Vercel frontend requests to local/Render backend with warning bypass |
| **Statutory Database** | PostgreSQL 18 / 16 | `127.0.0.1:5433` (db: `lmpc`) | **Active** | 11 tables verified with seed demo credentials & inspection logs |
| **Dev / Preview Servers**| Local Vite Runtime | `http://localhost:5173` / `:4173` | **Active** | Hot Module Replacement (HMR) & production bundle preview |

### 1.2. Statutory Numeral & Letter Height Standards (LMPC Rules 2011, Table 1)

The platform evaluates Principal Display Panel (PDP) dimensions and automatically enforces statutory numeral height thresholds under Rule 7 and Table 1:

| Principal Display Panel (PDP) Area ($A$) | Minimum Height ($H_{\text{min}}$) — Normal Case | Minimum Height ($H_{\text{min}}$) — Blown / Formed / Moulded / Perforated | Statutory Clause | Non-Compliance Severity |
| :--- | :--- | :--- | :--- | :--- |
| **$A \le 50\text{ cm}^2$** | **$1.0\text{ mm}$** | **$2.0\text{ mm}$** | Rule 7(1), Table 1, Row 1 | Low / Technical Notice |
| **$50\text{ cm}^2 < A \le 100\text{ cm}^2$** | **$1.5\text{ mm}$** | **$3.0\text{ mm}$** | Rule 7(1), Table 1, Row 2 | Medium / Statutory Rectification |
| **$100\text{ cm}^2 < A \le 500\text{ cm}^2$** | **$2.0\text{ mm}$** | **$4.0\text{ mm}$** | Rule 7(1), Table 1, Row 3 | High / Section 36 Penalty |
| **$500\text{ cm}^2 < A \le 2500\text{ cm}^2$** | **$4.0\text{ mm}$** | **$6.0\text{ mm}$** | Rule 7(1), Table 1, Row 4 | High / Section 36 Penalty |
| **$A > 2500\text{ cm}^2$** | **$6.0\text{ mm}$** | **$6.0\text{ mm}$** | Rule 7(1), Table 1, Row 5 | Critical / Seizure & Compounding |

---

## 2. Actors, User Roles & Workflows

LexMetra implements Role-Based Access Control (RBAC) with cryptographic JWT authentication and immutable audit logs:

| Role Identifier | Role Title | Portal / View Access | Primary Responsibility |
| :--- | :--- | :--- | :--- |
| `inspector` | Field Inspector | Command Center (`#home`), Scanner (`#scan`), Register (`#register`) | On-site package capture, OCR verification, Panchnama export |
| `authority` | Statutory Authority | Review Queue (`#review-queue`), Cases (`#authority`), Rules (`#regulatory`) | Case adjudication, compounding notices, FSSAI verification |
| `senior_inspector`| Regional Controller | Regional Intelligence (`#regional`), Heatmaps, Analytics | District compliance oversight, repeat offender tracking |
| `customer` / Public | Citizen / Consumer | Citizen Portal (`#customer`), Grievances, Public Verification | MRP verification, public complaints, National Consumer Helpline 1915 |
| `admin` | System Administrator | User Management, Audit Logs (`#profile`), System Health | Officer onboarding, security telemetry, rule updates |

```
                  ┌────────────────────────────────────────────────────────┐
                  │                 System Administrator                   │
                  │  (User Lifecycle, Security Audits, Rule Base Updates)  │
                  └───────────────────────────┬────────────────────────────┘
                                              │
         ┌────────────────────────────────────┼────────────────────────────────────┐
         │                                    │                                    │
         ▼                                    ▼                                    ▼
┌──────────────────┐               ┌──────────────────────┐             ┌─────────────────────┐
│  Field Inspector │               │ Statutory Authority  │             │   Senior Regional   │
│  (Enforcement)   │               │ (Officer/Controller) │             │     Controller      │
└────────┬─────────┘               └──────────┬───────────┘             └──────────┬──────────┘
         │                                    │                                    │
         │ • Mobile/Desktop Capture           │ • Case Adjudication                │ • State/District    │
         │ • Multi-Surface Scans              │ • Compound Notice Issuance         │   Analytics         │
         │ • PDP Measurement                  │ • Hearing Scheduling               │ • Offender Tracking │
         │ • PDF Inspection Reports           │ • Cross-Agency Appeals             │ • Market Oversight  │
         └────────────────────────────────────┴────────────────────────────────────┘
                                              ▲
                                              │ Public Grievances
                                   ┌──────────┴──────────┐
                                   │  Citizen / Consumer │
                                   │  (Public Portal)    │
                                   └─────────────────────┘
```

### 2.1. Field Inspector (`inspector`)
- **Primary Goal**: Rapid on-site market inspection at retail stores, godowns, e-commerce fulfillment centers, and customs ports.
- **Core Workflows**:
  1. **Multi-Surface Capture**: Take photos of the Principal Display Panel (PDP), back panel, and side panels of packaged commodities using mobile device camera or desktop upload.
  2. **Automated Surface Normalization**: Package boundary detection, perspective unwarping, and specular glare reduction.
  3. **High-Speed Statutory Verification**: Instant evaluation (< 2 seconds) of all mandatory declarations:
     - Manufacturer / Packer / Importer Name & Complete Address (Rule 6(1)(a))
     - Generic / Common Commodity Name (Rule 6(1)(b))
     - Net Quantity with Standard Units of Measurement (Rule 6(1)(c) & Rule 13)
     - Month & Year of Manufacture / Packing / Import (Rule 6(1)(d))
     - Maximum Retail Price (MRP) inclusive of all taxes (Rule 6(1)(e))
     - Unit Sale Price (USP) in Rupees per gram/ml/piece (Rule 6(11))
     - Consumer Care Details (Name, Address, Telephone, Email) (Rule 6(1)(n))
     - Country of Origin for imported goods (Rule 6(1)(f))
  4. **Principal Display Panel (PDP) Verification**: Area calculation ($A = H \times W$ for rectangular packs, $0.4 \times H \times C$ for cylindrical packs) and font/numeral height compliance (Rule 7, Table 1).
  5. **Inspection Report Generation**: Download tamper-evident, watermarked PDF inspection reports on the spot for seizure memos and panchnamas.

### 2.2. Statutory Authority (`authority`)
- **Primary Goal**: Review field inspection violations, adjudicate compounding proceedings, and issue legal notices.
- **Core Workflows**:
  1. **Authority Case Management**: Review flagged cases with severity classifications (HIGH, MEDIUM, LOW) and review reasons.
  2. **Regulatory Cross-Verification**: Verify 14-digit FSSAI licenses against food safety registries; detect invalid license formats and state-of-origin mismatches.
  3. **Legal Notice Generation**: Issue automated Show-Cause Notices and Compounding Orders under Sections 36 & 48 of the Legal Metrology Act, 2009.
  4. **Multi-Agency Escalation**: Dispatch enforcement records to Central Consumer Protection Authority (CCPA) or FSSAI enforcement wings.

### 2.3. Senior Regional Controller (`senior_inspector`)
- **Primary Goal**: High-level jurisdictional intelligence, district-level compliance monitoring, and repeated offender analysis.
- **Core Workflows**:
  1. **Regional Intelligence Dashboard**: Real-time violation heatmaps across states and districts.
  2. **Repeat Offender Tracking**: Identify brands, manufacturers, and packagers with recurring non-compliance across multiple locations.
  3. **Social & Grievance Intelligence**: Monitor public consumer complaints, overpricing hashtags, and counterfeit alerts in real time.

### 2.4. Citizen / Consumer (`public`)
- **Primary Goal**: Empower everyday consumers to verify pre-packaged goods and report violations.
- **Core Workflows**:
  1. **Public Verification**: Scan packaging to verify whether MRP, Unit Sale Price, and manufacturing dates are valid under law.
  2. **Consumer Grievance Reporting**: Submit reports on dual MRP, missing customer care details, or sticker alterations directly to the nearest Legal Metrology controller.

### 2.5. System Administrator (`admin`)
- **Primary Goal**: User lifecycle management, platform monitoring, and configuration oversight.
- **Core Workflows**:
  1. **User Account Provisioning**: Onboard inspectors and authorities with appropriate role assignments.
  2. **Audit Logging**: Review tamper-proof activity logs for all login attempts, scans, case actions, and fact modifications.

---

## 3. Platform Architecture

```
                               ┌────────────────────────────────────────────────────────────┐
                               │             Modern Web Client (React 18 + Vite)            │
                               │  - Mobile & Desktop Responsive (100dvh, Touch Optimized)   │
                               │  - Browser Navigation History (Native Back/Forward popstate)│
                               │  - Role-Based Dynamic Dashboards                           │
                               └─────────────────────────────┬──────────────────────────────┘
                                                             │ HTTPS / REST (JSON + Multipart)
                                                             ▼
                               ┌────────────────────────────────────────────────────────────┐
                               │                    FastAPI Gateway Engine                  │
                               │  - Dynamic CORS (Railway / Vercel Production Interop)      │
                               │  - JWT Authentication & RBAC Middleware                    │
                               │  - Structured Error Handling & Request Validation          │
                               └───────┬──────────────┬──────────────┬──────────────┬───────┘
                                       │              │              │              │
                     ┌─────────────────┘              │              │              └──────────────────┐
                     ▼                                ▼              ▼                                 ▼
       ┌───────────────────────────┐    ┌──────────────────┐ ┌───────────────────┐       ┌─────────────────────────┐
       │   Routes: Auth & Users    │    │ Routes: Sessions │ │ Routes: Inspection│       │    Routes: Authority    │
       │   (/auth, /audit-log)     │    │ (/sessions)      │ │ (/inspections)    │       │ (/cases, /reports, etc.)│
       └─────────────┬─────────────┘    └────────┬─────────┘ └─────────┬─────────┘       └────────────┬────────────┘
                     │                           │                     │                              │
                     └───────────────────────────┼─────────────────────┼──────────────────────────────┘
                                                 ▼                     ▼
                     ┌─────────────────────────────────────────────────────────────────────────┐
                     │                           Core Engine Pipeline                          │
                     ├───────────────────────────┬─────────────────────────────────────────────┤
                     │  1. Surface Geometry      │  cv2 perspective transform, PDP area, glare │
                     │  2. High-Speed Vision     │  Gemini Flash Lite (1.4s) + Qwen fallback   │
                     │  3. Multi-Variant OCR     │  Tesseract dual-engine ensemble + fusion    │
                     │  4. Rule Engine           │  Deterministic LMPC 2011 rule evaluation    │
                     │  5. Package Integrity     │  Reference matching & sticker detection     │
                     │  6. Regulatory Cross-Verif│  FSSAI validation & National Consumer Help  │
                     └───────────────────────────┴─────────────────────────────────────────────┘
                                                 │
                                                 ▼
                     ┌─────────────────────────────────────────────────────────────────────────┐
                     │                         PostgreSQL Persistence                          │
                     │  - Inspections, Sessions & Captures                                     │
                     │  - Authority Cases & Officer Actions                                    │
                     │  - Users, Audit Trail & Historical Reference Packages                   │
                     └─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Key Statutory Modules

### 4.1. High-Speed Perception & Dual OCR Fusion
- **Ultra-Fast Vision Perception**: Prioritizes `gemini-3.5-flash-lite` direct multimodal acceleration (benchmarked at ~1.4 seconds per multi-surface package) for instantaneous declaration extraction with bounding-box coordinates.
- **Failover Chain**: Automatic controlled failover to Groq `qwen/qwen3.8-27b`, OpenRouter, and local classical OCR ensures high availability even during external API throttling.
- **Multi-Pass OCR Fusion**: Integrates adaptive thresholding, morphological illumination correction, and orientation detection (0°, 90°, 180°, 270°) to eliminate orientation-dependent recognition failures.

### 4.2. Deterministic Rule Engine (`LMPC 2011`)
- **Zero Hallucination Principle**: Mathematical compliance checking based entirely on gazetted legal limits.
- **Rule 3 (Exemptions)**: Evaluates packages > 25 kg / 25 L (or > 50 kg for cement/fertilizer) and export-only consignments before declaration checks.
- **Rule 6 (Mandatory Declarations)**: Enforces presence, completeness, and non-ambiguity of all statutory fields.
- **Rule 7 & Table 1 (Numeral Heights)**: PDP area calculation mapped against statutory numeral height thresholds (1.0 mm to 6.0 mm).
- **Rule 12 & Rule 6(11) (Unit Sale Price)**: Verifies USP calculation with 2% tolerance across standard units (`per g`, `per kg`, `per ml`, `per litre`, `per item`).

#### Statutory Declarations Verification Matrix (LMPC Rules 2011)

| Statutory Rule | Declaration Parameter | Verification Logic | Mandatory Formats / Thresholds | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **Rule 6(1)(a)** | Manufacturer / Packer Address | Complete postal address, PIN code, city, state | Must include city & valid 6-digit postal code | `PASS` / `VIOLATION` |
| **Rule 6(1)(b)** | Generic / Common Commodity Name | Prominent naming on Principal Display Panel | Plain font, not overshadowed by trademark | `PASS` / `VIOLATION` |
| **Rule 6(1)(c)** | Net Quantity & Standard Units | Legal units: `g`, `kg`, `ml`, `l`, `m`, `cm`, `N` | Non-standard abbreviations (`gms`, `ml.`) flagged | `PASS` / `VIOLATION` |
| **Rule 6(1)(d)** | Month & Year of Packing / Import | Dual date association, format normalization | `MM/YYYY`, `Month YYYY`, or `DD/MM/YYYY` | `PASS` / `VIOLATION` |
| **Rule 6(1)(e)** | Maximum Retail Price (MRP) | "MRP ₹ ... incl. of all taxes" | Explicit tax inclusion clause required | `PASS` / `VIOLATION` |
| **Rule 6(11) / R12**| Unit Sale Price (USP) | $\text{USP} = \frac{\text{MRP}}{\text{Declared Quantity}}$ | Max 2% arithmetic rounding tolerance | `PASS` / `VIOLATION` |
| **Rule 6(1)(n)** | Consumer Care Details | Name, phone/toll-free, email, postal address | Phone must have valid STD/toll-free format | `PASS` / `VIOLATION` |
| **Rule 6(1)(f)** | Country of Origin | Imported commodities declaration | Mandatory for non-domestic manufacturers | `PASS` / `VIOLATION` |
| **Rule 7 & Table 1**| Numeral Height Compliance | $H_{\text{min}}$ determined by packaging PDP area | Rectangular: $A = H \times W$; Cylindrical: $0.4 \times H \times C$ | `PASS` / `VIOLATION` |

### 4.3. Anti-Counterfeit & Package Integrity
- **Baseline Comparison**: Compares inspected package declarations against manufacturer reference specifications stored in the system.
- **Variable vs. Static Segregation**: Distinguishes between legitimate production updates (Batch Number, MFD, Expiry) and non-compliant discrepancies (MRP tampering, altered Net Quantity, fabricated manufacturer addresses).
- **Advisory Sticker Detection**: Evaluates edge step-gradients and print sharpness differences to detect illicit physical sticker overlays on mandatory panels.

---

## 5. Repository Directory Structure

```
LexMetra/
├── backend/                               # Python FastAPI backend
│   ├── config.py                          # Unified environment configuration
│   ├── main.py                            # FastAPI application gateway (<1600 lines)
│   ├── inspection_helpers.py              # Common models & image validation utilities
│   ├── routes_auth.py                     # Authentication & audit trail router
│   ├── routes_sessions.py                 # Multi-surface capture session router
│   ├── routes_inspections.py              # Inspection review, CRUD & report router
│   ├── routes_authority.py                # Cases, FSSAI verification & assistant router
│   ├── rule_engine.py                     # Deterministic legal rule engine
│   ├── rule_common.py                     # Rule definitions, constants & condition mapping
│   ├── rule_evaluators.py                 # Specialized statutory evaluators (font, USP, etc.)
│   ├── ocr_engine.py                      # Region-first OCR fusion orchestrator
│   ├── ocr_readers.py                     # Tesseract & PaddleOCR engine drivers
│   ├── ocr_extraction.py                  # Field classification & regex parsing
│   ├── ocr_patterns.py                    # Statutory regex patterns & date extractors
│   ├── package_integrity.py               # Reference package comparison orchestrator
│   ├── integrity_matching.py              # Semantic declaration matching & sticker detection
│   ├── integrity_comparison.py            # Canonical field comparison logic
│   ├── qwen_perception.py                 # Multimodal perception & Gemini acceleration
│   ├── fast_vision_service.py             # Direct Gemini Flash perception service
│   ├── perception_parsers.py              # Bounding box & coordinate transform utilities
│   ├── geometry.py                        # Surface rectification & calibration
│   ├── report.py                          # Legal inspection report PDF generator
│   ├── db/
│   │   ├── persistence.py                 # PostgreSQL database access layer
│   │   └── schema.sql                     # Database schema definitions
│   ├── regulatory/                        # Regulatory RAG & rule versioning runtime
│   ├── Procfile                           # Railway deployment process descriptor
│   ├── railway.json                       # Railway service deployment configuration
│   └── nixpacks.toml                      # Nixpacks build manifest (Tesseract, libGL)
│
├── frontend/                              # Frontend web applications
│   ├── react-app/                         # Production React 18 + Vite SPA
│   │   ├── src/
│   │   │   ├── components/                # Kebab-case modular UI components (<1600 lines)
│   │   │   │   ├── app-header.tsx         # Responsive header & user profile
│   │   │   │   ├── app-navigation.tsx     # Role-based navigation bar & view router
│   │   │   │   ├── home-view.tsx          # Inspector home view & quick actions
│   │   │   │   ├── scan-capture-view.tsx  # Multi-surface camera & upload interface
│   │   │   │   ├── scan-details-view.tsx  # Interactive packaging inspection dashboard
│   │   │   │   ├── result-view.tsx        # Statutory compliance verdict breakdown
│   │   │   │   ├── evidence-view.tsx      # Multi-face visual evidence reviewer
│   │   │   │   ├── report-view.tsx        # Formal inspection report preview & download
│   │   │   │   ├── history-view.tsx       # Searchable inspection registry
│   │   │   │   ├── review-queue-view.tsx  # Human verification & escalation queue
│   │   │   │   ├── authority-dashboard-view.tsx # Authority case adjudication
│   │   │   │   ├── auth-views.tsx         # Login, registration & credential management
│   │   │   │   ├── package-integrity-card.tsx   # Integrity & tamper analysis card
│   │   │   │   ├── departmental-verification-card.tsx # FSSAI cross-check card
│   │   │   │   ├── consumer-report-modal.tsx    # Citizen grievance submission modal
│   │   │   │   └── multilingual-assistant-widget.tsx # Voice/chat statutory assistant
│   │   │   ├── lib/
│   │   │   │   ├── api-client.ts          # Strongly-typed API client with JWT support
│   │   │   │   ├── nav-history.ts         # Browser popstate & hash history manager
│   │   │   │   ├── types.ts               # Core TypeScript interface definitions
│   │   │   │   └── adapters.ts            # Data transformation & normalization
│   │   │   ├── index.css                  # Responsive design tokens & touch utilities
│   │   │   └── main.tsx                   # React root entrypoint
│   │   ├── vercel.json                    # Vercel SPA build & routing configuration
│   │   └── package.json                   # Dependencies & build scripts
│   ├── capture.html                       # Calibrated standalone capture tool
│   └── dashboard.html                     # Legacy single-file dashboard
│
├── rules/
│   └── rules.json                         # Codified Legal Metrology (LMPC) Rules 2011
├── scripts/
│   ├── e2e_bru_acceptance_test.py         # End-to-end verification acceptance script
│   └── e2e_real_verification.py           # Real package validation script
├── Procfile                               # Root Procfile for repository-root deployment
├── railway.json                           # Root Railway configuration
├── DEVELOPER.md                           # Comprehensive Developer & Contributor Guide
├── DEPLOYMENT_GUIDE.md                    # Blind-executable Railway & Vercel deployment guide
└── CHANGELOG_AND_STEPS.md                 # Complete audit log of project improvements
```

### 5.1. Backend REST API Endpoints Specification Matrix

The FastAPI backend exposes authenticated and public statutory endpoints:

| HTTP Method | Route / Endpoint | Auth / Role | Request Payload / Format | Statutory Function & Response Description |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/auth/login` | Public | JSON (`username`, `password`) | Issues signed HS256 JWT access token with user role and full name. |
| `POST` | `/auth/register` | Admin | JSON (`username`, `password`, `role`, `full_name`) | Provisions officer account with RBAC constraints in `users` table. |
| `GET` | `/auth/me` | Authenticated | Bearer JWT Header | Returns current officer profile, active role, and system permissions. |
| `GET` | `/auth/audit-log` | Admin / Authority | Query params (`limit`, `offset`) | Returns immutable audit events log from `audit_events` table. |
| `POST` | `/sessions` | Inspector / Officer | JSON (`product_name`, `sale_type`) | Initializes multi-surface inspection capture session (`session_id`). |
| `GET` | `/sessions/{id}` | Inspector / Officer | Path parameter `id` | Retrieves uploaded faces (`Face 1`, `Face 2`, `Face 3`) & metadata. |
| `POST` | `/sessions/{id}/upload` | Inspector / Officer | Multipart Form (`face_index`, `image_file`) | Uploads and normalizes a specific surface image in the session. |
| `POST` | `/sessions/{id}/process`| Inspector / Officer | JSON session trigger | Runs multi-variant OCR + Gemini Flash perception and rule engine. |
| `POST` | `/scan` | Inspector / Citizen | Multipart Form (`image`, `product_id`) | Direct single-shot high-speed package evaluation (< 1.5s). |
| `GET` | `/inspections` | Authenticated | Query params (`status`, `search`) | Returns paginated list of inspected packages and legal verdicts. |
| `GET` | `/inspections/{id}` | Authenticated | Path parameter `id` | Fetches complete facts, OCR bounding boxes, and statutory citations. |
| `GET` | `/inspections/{id}/report`| Authenticated | Path parameter `id` | Generates and streams formal watermarked PDF Panchnama report. |
| `GET` | `/authority/cases` | Authority / Controller | Query params (`status`, `severity`) | Returns pending legal review cases requiring compounding or notice. |
| `POST` | `/authority/cases/{id}/action` | Authority | JSON (`action_type`, `comments`) | Records statutory officer action (Notice Issued, Compounded, Dismissed). |
| `POST` | `/authority/cross-verify` | Authority / Officer | JSON (`license_number`, `system`) | Corroborates 14-digit FSSAI or BIS license against central registries. |
| `POST` | `/integrity/compare` | Authority / Inspector | JSON / Multipart (`test_facts`, `ref`) | Compares test packaging against reference package specifications. |
| `GET` | `/health` | Public | None | Liveness health check returning status, uptime, and database ping. |
| `GET` | `/ready` | Public | None | Readiness probe validating OCR engines, vision API, and DB connection. |

### 5.2. PostgreSQL Database Schema (11 Verified Tables)

The statutory persistence layer runs on PostgreSQL with 11 production tables:

| Table Name | Entity / Domain | Primary Key | Key Relational Columns & Constraints | Statutory Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **`users`** | Identity & RBAC | `user_id` (UUID) | `username` (UNIQUE), `hashed_password`, `role` | Stores officer credentials, role assignments, and active status. |
| **`audit_events`** | Audit & Compliance | `event_id` (UUID) | `actor_username`, `action`, `resource_id`, `timestamp` | Tamper-proof log of logins, scans, verdicts, and compounding actions. |
| **`inspections`** | Inspection Records | `inspection_id` (UUID) | `product_id`, `product_name`, `overall_status`, `created_at` | Primary record for each packaging evaluation and overall status. |
| **`inspection_facts`**| Extracted Evidence | `fact_id` (UUID) | `inspection_id` (FK), `field_name`, `raw_value`, `confidence` | Normalized values and spatial bounding boxes for each declaration. |
| **`inspection_findings`**| Legal Findings | `finding_id` (UUID) | `inspection_id` (FK), `rule_id`, `status`, `severity` | Detailed per-rule statutory determinations (Rule 6, Rule 7, Rule 12). |
| **`sessions`** | Capture Sessions | `session_id` (UUID) | `inspector_id` (FK), `status`, `product_type`, `created_at` | Multi-surface capture workflow sessions for packaging inspections. |
| **`captures`** | Raw Package Faces | `capture_id` (UUID) | `session_id` (FK), `face_index`, `image_url`, `rectified_url` | Surface images (PDP, Back, Sides), rectified crops, and lighting stats. |
| **`package_integrity_records`**| Anti-Counterfeit | `record_id` (UUID) | `barcode`, `brand_name`, `canonical_facts`, `updated_at` | Reference packaging specifications provided by registered brand owners. |
| **`authority_cases`** | Legal Proceedings | `case_id` (UUID) | `inspection_id` (FK), `status`, `severity`, `hearing_date` | Statutory cases under adjudication for compounding or prosecution. |
| **`officer_actions`**| Judicial Audit | `action_id` (UUID) | `case_id` (FK), `officer_id` (FK), `action_type`, `timestamp` | Immutable trail of notices issued, compounding fees, and hearings. |
| **`consumer_grievances`**| Citizen Reports | `docket_id` (UUID) | `consumer_phone`, `retailer_name`, `violation_type`, `status` | Public complaints on dual MRP, missing declarations, or overpricing. |

### 5.3. Frontend Page & Route Directory Matrix

The single-page application uses browser hash routing for deep links and popstate navigation:

| Route Path | View Component | Target Audience | Dynamic Page Title | Canonical Search Indexing |
| :--- | :--- | :--- | :--- | :--- |
| `/#landing` | `landing-page.tsx` | General Public & Officials | *LexMetra — Statutory Legal Metrology Compliance Platform* | Indexed (`index, follow`) |
| `/#home` | `home-view.tsx` | Field Inspectors (`inspector`) | *Field Inspector Command Center \| LexMetra* | Private (`noindex`) |
| `/#scan` | `scan-capture-view.tsx` | Field Inspectors & Officers | *Statutory Package Scanner \| LexMetra* | Private (`noindex`) |
| `/#detail/{id}` | `scan-details-view.tsx` | Inspectors & Authorities | *Packaging Compliance Review \| LexMetra* | Private (`noindex`) |
| `/#evidence/{id}`| `evidence-view.tsx` | Inspectors & Authorities | *Visual Evidence & Coordinate Inspector \| LexMetra* | Private (`noindex`) |
| `/#report/{id}` | `report-view.tsx` | Inspectors & Courts | *Inspection Panchnama & Seizure Report \| LexMetra* | Private (`noindex`) |
| `/#history` | `history-view.tsx` | Field Officers | *Statutory Inspection Register \| LexMetra* | Private (`noindex`) |
| `/#review-queue`| `review-queue-view.tsx`| Senior Inspectors | *Human-in-the-Loop Review Queue \| LexMetra* | Private (`noindex`) |
| `/#authority` | `authority-dashboard-view.tsx`| Statutory Authorities | *Legal Metrology Authority Enforcement Center \| LexMetra* | Private (`noindex`) |
| `/#customer` | `landing-page.tsx` (Citizen)| Consumers & General Public | *Citizen Packaging Verification & Grievance Portal \| LexMetra* | Indexed (`index, follow`) |
| `/#regulatory` | `regulatory-view.tsx` | Legal Officers & Public | *LMPC Rules 2011 Regulatory Reference \| LexMetra* | Indexed (`index, follow`) |
| `/#privacy` | `privacy-policy-view.tsx` | All Users | *Privacy Policy & Data Protection (DPDPA 2023) \| LexMetra* | Indexed (`index, follow`) |
| `/#terms` | `terms-view.tsx` | All Users | *Statutory Terms of Enforcement Service \| LexMetra* | Indexed (`index, follow`) |
| `/#thank-you` | `thank-you-view.tsx` | Citizens / Complainants | *Submission Confirmation & Docket Receipt \| LexMetra* | Private (`noindex`) |
| `/#empty` | `empty-state-view.tsx` | New Inspectors | *Getting Started — Zero State Guidance \| LexMetra* | Private (`noindex`) |
| `/#404` | `not-found-view.tsx` | All Users | *404 — Statutory Notice: Page Not Found \| LexMetra* | Private (`noindex`) |

### 5.4. Responsive Breakpoints & Device Adaptation Matrix

The application layout dynamically adapts across all device form factors:

| Breakpoint | Minimum Width | Target Device Class | Navigation Layout | Scanner & Grid Layout | Mobile Optimizations |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`xs`** | `320px - 479px` | Compact Smartphones (iPhone SE) | Collapsed hamburger menu drawer | Single-column stacked cards | Sticky mobile CTA; $\ge 44\text{px}$ touch targets |
| **`sm`** | `480px - 639px` | Standard Smartphones (iPhone 14/15) | Collapsed hamburger menu drawer | 2-column KPI stats; stacked panels | Zero horizontal scroll; dynamic safe-area insets |
| **`md`** | `640px - 767px` | Large Phablets & Mini Tablets | Compact top navigation bar | 2-column cards; expandable trays | Kinetic touch scrolling on data tables |
| **`lg`** | `768px - 1023px`| Tablets & Small Laptops (iPad) | Full desktop header navigation | Split-screen scanner + live results | Multi-surface side-by-side evidence preview |
| **`xl`** | `1024px+` | Desktop Monitors & Command Displays | Full enterprise dashboard rail | Multi-column 12-grid evidence suite | High-density audit tables with inline filters |

---

## 6. Regulatory References & Gazette Standards

All verification parameters in LexMetra are grounded in published Indian statutory authorities:
- **The Legal Metrology Act, 2009** (No. 1 of 2010), specifically:
  - Section 18 (Mandatory Declarations on Pre-packaged Commodities)
  - Section 36 (Penalties for Quote of Non-Standard Units & Non-Declaration)
  - Section 48 (Compounding of Offences by Authorised Controllers)
- **The Legal Metrology (Packaged Commodities) Rules, 2011 (LMPC Rules)**:
  - Rule 3 (Exemptions & Scope)
  - Rule 6(1)(a)-(p) (Mandatory Declarations on Retail Packages)
  - Rule 6(11) (Unit Sale Price Specification)
  - Rule 7 & Table 1 (Principal Display Panel Dimensions & Numeral Height)
  - Rule 8 (Grouping of Declarations)
  - Rule 12 (Net Quantity Stated in Standard Metric Units)
  - Rule 24 (Wholesale Package Declarations)
  - Rule 26 (Small Package Relaxations)
  - Rule 27 (Registration of Manufacturers and Packers)
  - Rule 31 (Advertisements of Pre-Packaged Goods)
  - Second Schedule (Standard Pack Quantities for Specified Commodities)

---

## 7. License & Rights

Published for statutory packaging compliance operations. All rights reserved.
