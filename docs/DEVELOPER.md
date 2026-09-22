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

---

## 6. Database Schema & Architecture

The PostgreSQL database (`lmpc`) contains the following primary tables:

1. **`users`**:
   - `user_id` (UUID), `username`, `hashed_password`, `role`, `full_name`, `created_at`
2. **`audit_events`**:
   - `event_id`, `action`, `actor_username`, `resource_type`, `resource_id`, `detail`, `timestamp`
3. **`inspections`**:
   - `inspection_id`, `product_id`, `product_name`, `sale_type`, `overall_status`, `facts`, `findings`, `created_at`
4. **`sessions` & `captures`**:
   - Stores multi-surface capture sessions, face images (`Face 1`, `Face 2`, `Face 3`), canonical rectified textures, and calibration metadata.
5. **`package_integrity_records`**:
   - Historical manufacturer reference declarations, version history, and difference logs.
6. **`authority_cases`**:
   - Enforcement case IDs, violation classifications, status (`PENDING_REVIEW`, `NOTICE_ISSUED`, `COMPOUNDED`), and officer actions.

You can inspect and query the database using TablePlus, DBeaver, or `psql`:
```bash
psql -h localhost -p 5433 -U lmpc -d lmpc
```

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
