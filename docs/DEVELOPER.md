# LexMetra Developer & Contributor Guide

This document contains detailed engineering instructions, development setup steps, database operations, testing procedures, and architectural constraints for developers contributing to or maintaining the **LexMetra** platform.

---

## 1. Architectural Principles & Coding Standards

### 1.1. Core Invariants (Do Not Break)
1. **Evidence-First Separation of Concerns**:
   - Perception (OCR/CV/multimodal perception) extracts and transcribes evidence with bounding boxes and provenance.
   - The Rule Engine (`rule_engine.py`) determines legal status (`PASS`, `FAIL`, `UNCERTAIN`, `EXEMPT`). AI never decides legal compliance directly.
2. **Strict File Line Limit (< 1600 Lines)**:
   - **No file in the repository may exceed 1600 lines of code.**
   - Modularize large files by domain (e.g. `routes_*.py`, `ocr_*.py`, `integrity_*.py`, `rule_*.py`).
3. **Strict Naming Conventions**:
   - **Frontend files & web assets**: `kebab-case.tsx`, `kebab-case.ts`, `kebab-case.css`.
   - **Backend Python files & database scripts**: `snake_case.py`, `snake_case.sql`.
   - **Internal functions & methods**: `camelCase` for frontend components/hooks/methods, standard Python naming conventions for backend modules with descriptive, human-readable function signatures.
4. **Browser Navigation & History**:
   - All modal views, details views, evidence views, and reports must push hash history (`#detail/<id>`, `#evidence/<id>`, `#report/<id>`).
   - The native browser **Back** and **Forward** buttons must transition between views without exiting the platform.
5. **Mobile-First & Zero Horizontal Scroll**:
   - All components must render cleanly on mobile viewports down to 320px width without horizontal blowout (`overflow-x: hidden`).
   - Touch targets must adhere to a minimum size of 44x44px.
   - All images must include meaningful, descriptive `alt` attributes.

### 1.2. Responsive Breakpoints & Viewport Matrix

| Breakpoint | Minimum Width | Target Devices | Layout Behavior |
| :--- | :--- | :--- | :--- |
| **`xs`** | `320px - 479px` | Compact smartphones (iPhone SE, Galaxy S) | Single-column, stacked CTAs, sticky mobile CTA bar |
| **`sm`** | `640px` | Large smartphones, mini tablets | 2-column stat cards, expanded header buttons |
| **`md`** | `768px` | Tablets, iPad Mini | Desktop rail navigation activates, bottom nav hidden |
| **`lg`** | `1024px` | Laptops, desktop monitors | Full 12-column grid, split-screen live scanner simulation |
| **`xl`** | `1280px+` | Wide monitors, command centers | High-density multi-panel evidence inspector |

### 1.3. Page Metadata & Telemetry Architecture

- **Page Metadata**: Managed dynamically by `src/lib/page-metadata.ts` on every view transition. Updates `document.title`, `<meta name="description">`, `og:title`, and `twitter:title`.
- **Analytics & Telemetry**: Managed by `src/lib/analytics.ts`. Dispatches `lexmetra_telemetry` events while strictly respecting user cookie preferences configured via `CookieBanner`.

### 1.4. Frontend Design Tokens & Custom CSS Utilities Matrix

The UI design system in `frontend/react-app/src/index.css` implements specific utility classes for responsive behavior, accessibility, and statutory feedback:

| CSS Selector / Utility | Styling Rules Applied | Functional & Accessibility Impact |
| :--- | :--- | :--- |
| `.no-horizontal-scroll` | `max-width: 100vw; overflow-x: hidden;` | Prevents mobile horizontal scrolling and layout clipping on small viewports. |
| `.touch-target` | `min-height: 44px; min-width: 44px;` | Enforces WCAG 2.1 AA touch target sizing for buttons and interactive controls. |
| `.sticky-mobile-cta` | `position: fixed; bottom: 0; z-index: 50; backdrop-filter: blur(12px);` | Provides instant one-tap scanning accessibility when scrolling through long pages. |
| `.table-responsive-container` | `overflow-x: auto; -webkit-overflow-scrolling: touch;` | Enables smooth kinetic touch scrolling for dense tabular inspection data. |
| `.loading-skeleton` | `background: linear-gradient(...); animation: shimmer 1.5s infinite;` | High-fidelity shimmer skeleton placeholder during async vision perception runs. |
| `.form-input-error` | `border-color: #ef4444; box-shadow: 0 0 0 1px #ef4444;` | Highlights invalid fields with accessible ARIA invalid feedback and red focus rings. |
| `.form-input-success` | `border-color: #10b981; box-shadow: 0 0 0 1px #10b981;` | Confirms valid statutory entries (e.g., compliant 14-digit FSSAI licenses). |
| `.badge-violation` | `background: #fef2f2; color: #991b1b; border: 1px solid #fecaca;` | Standardized statutory non-compliance callout badge. |
| `.badge-pass` | `background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0;` | Standardized statutory compliance verification badge. |

---

## 2. System Prerequisites

Ensure the following system dependencies are installed:

| Tool | Minimum Version | Installation Command (Ubuntu/Debian) |
|---|---|---|
| **Python** | 3.11+ (Tested on 3.14) | `sudo apt install python3 python3-pip python3-venv` |
| **Node.js** | 18.0+ (LTS 20 Recommended) | `curl -fsSL https://deb.nodesource.com/setup_20.x \| sudo -E bash - && sudo apt install nodejs` |
| **PostgreSQL** | 14.0+ (Tested on 16) | `sudo apt install postgresql postgresql-contrib` |
| **Tesseract OCR** | 5.0+ | `sudo apt install tesseract-ocr libtesseract-dev` |
| **OpenCV Libs** | System C++ libs | `sudo apt install libgl1 libglib2.0-0` |

---

## 3. Local Environment Setup

### 3.1. Clone and Virtual Environment
```bash
git clone https://github.com/your-org/LexMetra.git
cd LexMetra

# Create Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip & install backend dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 3.2. Backend Environment Variables (`backend/.env`)
Create `backend/.env` (or set environment variables in your terminal):
```ini
# Server Configuration
PORT=8000
DEV_MODE=true
BOOTSTRAP_DEMO_USERS=true

# Database (PostgreSQL)
# Default port 5433 if running via custom docker/local instance; otherwise 5432
DATABASE_URL=postgresql://lmpc:lmpc@localhost:5433/lmpc

# Multimodal Vision & OCR Perception
# Primary high-speed vision model (executes in ~1.4s)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_OCR_MODEL=gemini-3.5-flash-lite

# Fallback Vision Providers (Optional)
GROQ_API_KEY=gsk_your_groq_key_here
OPENROUTER_API_KEY=sk-or-your_openrouter_key_here

# Security & CORS
JWT_SECRET=your_super_secret_jwt_key_here
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:8000,http://127.0.0.1:5500
```

### 3.3. Database Initialization
Verify PostgreSQL is active and initialize the schema:
```bash
# Verify postgres is running
sudo systemctl status postgresql

# Initialize database schema and default tables
python3 -c "import sys; sys.path.insert(0, 'backend'); from db import persistence as db; db.init_schema(); print('Schema initialized successfully!')"
```

### 3.4. Frontend Dependencies Setup
```bash
cd frontend/react-app
npm install
```

Create `frontend/react-app/.env.local`:
```ini
# Points to local FastAPI backend
VITE_API_BASE_URL=http://localhost:8000
```

---

## 4. Running the Platform Locally

### 4.1. Run Backend Server
From the repository root:
```bash
source .venv/bin/activate
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
- API Documentation (Swagger UI): `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`
- Readiness Check: `http://localhost:8000/ready`

### 4.2. Run Frontend Server
In a second terminal:
```bash
cd frontend/react-app
npm run dev
```
- Frontend Application: `http://localhost:5173/`

### 4.3. Default Demo Accounts
When `BOOTSTRAP_DEMO_USERS=true` and `DEV_MODE=true`, the following accounts are initialized automatically:

| Role | Username | Password | Access Level |
|---|---|---|---|
| **System Administrator** | `admin` | `password123` | Full access, user management, audit trail |
| **Statutory Authority** | `authority` | `password123` | Case adjudication, compounding, FSSAI |
| **Senior Regional Officer**| `senior_inspector` | `password123` | State/district analytics, market overview |
| **Field Inspector** | `inspector` | `password123` | Multi-surface capture, scan, PDP analysis |

---

## 5. Testing & Verification

Always run test suites before committing code.

### 5.1. Backend Unit & Integration Tests
```bash
# Run all test suites
pytest backend/tests/

# Run specific domain test suites
pytest backend/tests/test_rule_engine.py                  # Statutory rule engine tests
pytest backend/tests/test_qwen_perception_v1.py           # Multimodal perception tests
pytest backend/tests/test_generalized_date_association.py # OCR date and pattern parsing
pytest backend/tests/test_three_additions.py              # Package integrity & anti-tamper
```

### 5.2. Frontend Build Verification
Verify that TypeScript compiles with 0 errors and production assets bundle successfully:
```bash
cd frontend/react-app
npm run build
```

### 5.3. Line Count Enforcement Check
Run this shell one-liner to verify no file exceeds 1600 lines:
```bash
find backend frontend -type f \( -name "*.py" -o -name "*.tsx" -o -name "*.ts" \) -not -path "*/node_modules/*" -not -path "*/dist/*" -not -path "*/.venv/*" | xargs wc -l | sort -nr | head -n 15
```
*Expected: The highest line count must be under 1600 lines.*

### 5.4. Test Suite & Automated Coverage Matrix

| Test Suite File | Domain / Component Tested | Test Scenarios & Cases | Execution Command | Status |
| :--- | :--- | :--- | :--- | :--- |
| `test_rule_engine.py` | LMPC 2011 Rule Evaluation | 40 unit tests covering MRP, USP math, PDP height, Country of origin | `pytest backend/tests/test_rule_engine.py` | ✅ **40/40 Passed** |
| `test_qwen_perception_v1.py` | Multimodal Vision Perception | 17 tests covering bounding box parsing, surface alignment, failovers | `pytest backend/tests/test_qwen_perception_v1.py` | ✅ **17/17 Passed** |
| `test_generalized_date_association.py` | Regex & Date Classification | 30 tests covering dual dates, month-year normalization, batch extractors | `pytest backend/tests/test_generalized_date_association.py` | ✅ **30/30 Passed** |
| `test_three_additions.py` | Anti-Tamper & Package Integrity | 4 integration tests on sticker overlay detection and spec comparison | `pytest backend/tests/test_three_additions.py` | ✅ **4/4 Passed** |
| `e2e/lexmetra.spec.ts` | Playwright E2E UI Suite | 3 browser end-to-end tests: inspector login, mobile 390x844, citizen portal | `npx playwright test` | ✅ **3/3 Passed** |

---

## 6. Database Schema & Architecture

The PostgreSQL database (`lmpc`) contains 11 production-verified tables:

### 6.1. Database Tables & Key Columns Matrix

| Table Name | Primary Key | Key Relational Columns & Constraints | Purpose & Storage Content |
| :--- | :--- | :--- | :--- |
| **`users`** | `user_id` (UUID) | `username` (UNIQUE), `hashed_password`, `role` | Stores officer and administrator accounts with password hashes. |
| **`audit_events`** | `event_id` (UUID) | `actor_username`, `action`, `resource_id`, `timestamp` | Append-only audit trail recording every state change and legal action. |
| **`inspections`** | `inspection_id` (UUID) | `product_id`, `product_name`, `overall_status`, `created_at` | Primary record for each packaging evaluation and overall status. |
| **`inspection_facts`** | `fact_id` (UUID) | `inspection_id` (FK), `field_name`, `raw_value`, `confidence` | Normalized values and spatial bounding boxes for each declaration. |
| **`inspection_findings`**| `finding_id` (UUID) | `inspection_id` (FK), `rule_id`, `status`, `severity` | Detailed per-rule statutory determinations (Rule 6, Rule 7, Rule 12). |
| **`sessions`** | `session_id` (UUID) | `inspector_id` (FK), `status`, `product_type`, `created_at` | Multi-surface capture workflow sessions for packaging inspections. |
| **`captures`** | `capture_id` (UUID) | `session_id` (FK), `face_index`, `image_url`, `rectified_url` | Surface images (PDP, Back, Sides), rectified crops, and lighting stats. |
| **`package_integrity_records`**| `record_id` (UUID)| `barcode`, `brand_name`, `canonical_facts`, `updated_at` | Reference packaging specifications provided by registered brand owners. |
| **`authority_cases`** | `case_id` (UUID) | `inspection_id` (FK), `status`, `severity`, `hearing_date` | Statutory cases under adjudication for compounding or prosecution. |
| **`officer_actions`** | `action_id` (UUID) | `case_id` (FK), `officer_id` (FK), `action_type`, `timestamp` | Immutable trail of notices issued, compounding fees, and hearings. |
| **`consumer_grievances`**| `docket_id` (UUID) | `consumer_phone`, `retailer_name`, `violation_type`, `status` | Public complaints on dual MRP, missing declarations, or overpricing. |

### 6.2. Multi-Lingual Statutory Dictionaries Matrix

LexMetra supports statutory inspection across three official languages:

| Language Code | Language Name | Primary Usage Surface | Covered Statutory Terminology |
| :--- | :--- | :--- | :--- |
| **`en`** | English | Technical inspection reports & gazette rules | Rule 6 mandatory declarations, USP, FSSAI verification, Panchnama |
| **`hi`** | Hindi (हिन्दी) | Citizen grievance portal & mobile UI | कानूनी मापविज्ञान, शुद्ध मात्रा, अधिकतम खुदरा मूल्य, उपभोक्ता शिकायत |
| **`mr`** | Marathi (मराठी) | State controller dashboard & field alerts | कायदेशीर मापशास्त्र, निव्वळ वजन, किरकोळ विक्री किंमत, तपासणी अहवाल |

### 6.3. Supabase CLI & Database Synchronization
LexMetra supports cloud-hosted PostgreSQL via Supabase using Supabase CLI and migrations:
```bash
# Push schema migrations to Supabase:
npx supabase db push --db-url="postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres?sslmode=require"

# Migrate local inspections and users into Supabase:
python3 scripts/migrate_to_supabase.py --target-url="postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres?sslmode=require"
```

### 6.4. Official PDF Generation & Layout Invariants
- `frontend/react-app/src/lib/pdf-generator.ts` executes `exportElementAsPdf()` using jsPDF and html2canvas.
- **Full-Width Fitting**: The export engine scales elements to fill 100% of the printable page width (`pageW = A4_W - MARGIN * 2`) rather than shrinking horizontally.
- **Vertical Pagination**: Overheight dockets are cleanly paginated across pages at full scale, preserving crisp font readability without requiring zoom.

---

## 7. Contributing Guidelines

1. **Create a Feature Branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. **Maintain Modular Structure**:
   - If adding new routes, attach them to the appropriate `routes_*.py` router or create a new router under 1600 lines.
   - If adding new UI components, place them in `frontend/react-app/src/components/` in `kebab-case.tsx`.
3. **Preserve Regulatory Integrity**:
   - Never weaken LMPC 2011 compliance algorithms or tolerances without referencing official gazette notifications.
4. **Submit Pull Request**:
   - Document changes made, attach test run logs, and ensure all CI checks pass.
