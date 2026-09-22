# Running the full stack locally

## 1. Environment

Copy `backend/.env.example` to `backend/.env` and provide real local values.
Never commit `.env` or API credentials. The default development JWT secret is
not suitable for deployment.

## 2. Docker Compose

The preferred local stack is PostgreSQL + Redis + backend:

```bash
docker compose up --build
```

The backend expects `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, and related
settings from the Compose environment. Redis is operational cache only. It is
never the source of legal truth.

## 3. Backend without Docker

```bash
cd backend
pip install -r requirements.txt
# Tesseract OCR engine is a system dependency, not a Python package.
sudo apt-get install tesseract-ocr
uvicorn main:app --reload --port 8000
```

The PostgreSQL schema is in `backend/db/schema.sql`. Use a PostgreSQL database
for persistent inspection/audit data.

## 4. Frontend

`frontend/dashboard.html` is a static browser dashboard. `frontend/capture.html`
is the calibrated capture tool. The React application under
`frontend/react-app/` is the richer application surface and uses the package
manifest/lockfile in that directory.

## 5. Regulatory safety model

The pipeline is intentionally split into separate authorities:

1. AI/OCR extracts evidence.
2. Regulatory RAG retrieves dated, source-linked knowledge.
3. Applicability determines whether a requirement is in scope.
4. The deterministic rule engine determines compliance.
5. A human resolves material uncertainty and authorizes legal activation.

Effective dates do not automatically activate scheduled legal amendments.
Runtime rule selection uses only explicitly `ACTIVE` versions. Historical rule
versions remain immutable and are selected by the inspection date.

## 6. Optional providers

PaddleOCR is isolated in a child process because native ML runtimes can fail at
process level. Tesseract remains the fallback. Anthropic and Gemini are optional
VLM providers for ambiguity review only. A VLM failure must never create a legal
PASS or FAIL.

## 7. Important demo/legal limitation

`rules/rules.json` contains records whose `verification_status` is still
`needs_official_verification`. Those thresholds must be checked against primary
government sources before being presented as legally verified. This repository
must not silently convert commentary-derived values into authoritative law.
