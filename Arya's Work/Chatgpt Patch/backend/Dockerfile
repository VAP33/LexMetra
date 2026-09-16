# LMPC Compliance Inspection API — backend container image.
#
# Build context must be the repository root (so ../rules and ../dataset are
# reachable at the paths backend/*.py already expect):
#   docker build -f backend/Dockerfile -t lmpc-backend .
# or simply use docker-compose.yml from the repo root.

FROM python:3.12-slim AS base

# Tesseract is a native binary dependency of pytesseract (see
# backend/requirements.txt) and is NOT installable via pip.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Repository layout matters: backend/*.py resolves rules/rules.json and
# dataset/ via relative paths (Path(__file__).resolve().parent.parent), so
# the whole repo (minus .dockerignore exclusions) is copied in, not just
# backend/.
COPY . /app

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    LMPC_DEV_MODE=false

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# JWT_SECRET_KEY and DATABASE_URL MUST be supplied at runtime (see
# docker-compose.yml / backend/.env.example). The app intentionally refuses
# to start with an insecure default secret when LMPC_DEV_MODE=false.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
