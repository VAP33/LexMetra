# =============================================================================
# LexMetra / LMPC Compliance Platform — Multi-Stage Dockerfile
#
# Stage 1 (frontend-builder): Node 20 — installs deps, runs `vite build`
# Stage 2 (backend):          Python 3.12-slim — installs system + pip deps,
#                             copies in the compiled React bundle, runs uvicorn
#
# Build context MUST be the repository root (not backend/):
#   docker build -f backend/Dockerfile -t lmpc-backend .
#   docker compose up --build        ← preferred
#
# The backend mounts the compiled frontend at /app/ via FastAPI StaticFiles,
# so no separate frontend container is needed at runtime.
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1 — Build the React frontend
# -----------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder

ARG NODE_ENV=production
ENV NODE_ENV=$NODE_ENV

WORKDIR /frontend

# Copy only package files first so Docker layer-caches the npm install
# and only re-runs it when dependencies actually change.
COPY frontend/react-app/package.json frontend/react-app/package-lock.json ./

# Clean install — uses package-lock.json for exact, reproducible versions.
# --ignore-scripts prevents any postinstall hooks from running as root.
RUN npm ci --ignore-scripts

# Copy the rest of the frontend source
COPY frontend/react-app/ ./

# Run TypeScript type-check then Vite production build.
# Output lands in /frontend/dist
RUN npm run build


# -----------------------------------------------------------------------------
# Stage 2 — Python backend
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS backend

# ---------------------------------------------------------------------------
# System dependencies
#
#   tesseract-ocr / tesseract-ocr-eng  — OCR binary required by pytesseract
#   libgl1                             — OpenCV runtime (headless still needs it)
#   libglib2.0-0                       — OpenCV runtime
#   curl                               — used by HEALTHCHECK
#   libzbar0                           — barcode decoding (pyzbar)
# ---------------------------------------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
        libzbar0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Python dependencies
# Install before copying source so Docker can cache this layer.
# ---------------------------------------------------------------------------
WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

# ---------------------------------------------------------------------------
# Copy project source
# The entire repo is needed because backend/*.py resolves:
#   rules/rules.json      → Path(__file__).parent.parent / "rules"
#   dataset/              → Path(__file__).parent.parent / "dataset"
#   frontend/             → Path(__file__).parent.parent / "frontend"
# .dockerignore keeps this lean (no node_modules, __pycache__, .git, etc.)
# ---------------------------------------------------------------------------
COPY . /app

# ---------------------------------------------------------------------------
# Drop the compiled React bundle from Stage 1 into the location FastAPI
# mounts as StaticFiles at /app/ — i.e. frontend/react-app/dist/
# ---------------------------------------------------------------------------
COPY --from=frontend-builder /frontend/dist /app/frontend/react-app/dist

# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------
WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LMPC_DEV_MODE=false

# Runtime secrets (JWT_SECRET_KEY, DATABASE_URL, etc.) must be supplied via
# docker-compose.yml environment section or a .env file — never baked in here.

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run as non-root for defence-in-depth.
# Create a dedicated user with no login shell and no home directory writes.
RUN groupadd --system lmpc && useradd --system --gid lmpc --no-create-home lmpc \
    && chown -R lmpc:lmpc /app/backend/uploads 2>/dev/null || true \
    && chown -R lmpc:lmpc /app/backend/reports 2>/dev/null || true

USER lmpc

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
