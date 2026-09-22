# LexMetra Production Deployment & Infrastructure Guide

> **Official Multi-Cloud & Local Tunnel Deployment Guide**
> Deploying the **React 18 + Vite Frontend** on **Vercel** via Vercel CLI, the **FastAPI + OCR + Pyzbar Backend** on **Render** (or Ngrok Tunnel), and **Managed PostgreSQL 16/18**.

---

## Architecture Overview

```
 ┌─────────────────────────────────────────────────────────┐
 │               Vercel Edge Network (CDN)                 │
 │                                                         │
 │  React 18 + Vite SPA · Hash/History PWA Routing         │
 │  Live URL: https://lexmetra-ui.vercel.app               │
 └────────────────────────────┬────────────────────────────┘
                              │
               HTTPS API (JSON / Multipart)
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
 ┌──────────────────────────┐   ┌──────────────────────────┐
 │      Render (Cloud)      │   │   Ngrok Secure Tunnel    │
 │                          │   │   (Local Field Backend)  │
 │  FastAPI Docker Service  │   │  https://...ngrok-free.dev│
 │  Tesseract OCR + OpenCV  │   │  Forwarding to :8000     │
 └────────────┬─────────────┘   └─────────────┬────────────┘
              │                               │
              ▼                               ▼
 ┌──────────────────────────┐   ┌──────────────────────────┐
 │  Render Managed Postgres │   │ Local PostgreSQL 18 DB   │
 │  Database: lmpc_db       │   │ 127.0.0.1:5433 (11 tbls) │
 └──────────────────────────┘   └──────────────────────────┘
```

---

## Multi-Cloud Service Status Matrix

| Component | Target Platform | Port / URL | Health Endpoint | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend Web App** | Vercel Edge | `https://lexmetra-ui.vercel.app` | `GET /` (HTTP 200) | Built with Vite; zero horizontal scroll; mobile PWA |
| **Backend API Engine** | Render Cloud | `https://lexmetra-backend.onrender.com` | `GET /health` | FastAPI, Python 3.12, Tesseract OCR, YOLOv8 |
| **Local Field Tunnel** | Ngrok | `https://rise-sponsor-juvenile.ngrok-free.dev` | `GET /health` | Bridges live Vercel frontend to local Python backend |
| **Primary Database** | Render PostgreSQL | `postgres://lmpc_user:...@dpg-xxx:5432/lmpc_db` | `SELECT 1` | Managed cloud PostgreSQL with automated backups |
| **Local Database** | PostgreSQL 18 | `127.0.0.1:5433` (db: `lmpc`) | `psql -p 5433` | 11 tables verified with seed demo credentials |

---

## PART 1: Deploy Frontend on Vercel via Vercel CLI

The frontend is already configured with `.vercel` project linkages and dynamic API resolution in `src/lib/api-client.ts`.

### Step 1: Install & Authenticate Vercel CLI
```bash
npm install -g vercel
vercel login
```

### Step 2: Build the Production Bundle
From `frontend/react-app/`:
```bash
cd frontend/react-app
npm install
npm run build
```
This runs `tsc && vite build`, creating the optimized distribution bundle in `dist/`.

### Step 3: Deploy to Production
```bash
vercel deploy --prebuilt --prod
```
The output will display the production alias:
```text
Production: https://lexmetra-ui.vercel.app [copied to clipboard]
Status: Ready
```

### Step 4: Environment Variables on Vercel
In the Vercel Dashboard (or via `vercel env add`):
| Variable | Value | Description |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | `https://rise-sponsor-juvenile.ngrok-free.dev` (or Render backend URL) | Backend API endpoint |

---

## PART 2: Deploy Backend & Database on Render

Render provides native Docker container hosting (which includes Tesseract OCR binaries, OpenCV shared libraries, and pyzbar) and Managed PostgreSQL.

### Method A: One-Click Render Blueprint (`render.yaml`)

We have placed an Infrastructure-as-Code `render.yaml` in the root of the repository:

1. Push this repository to GitHub / GitLab.
2. Log into [dashboard.render.com](https://dashboard.render.com).
3. Click **"Blueprints"** $\rightarrow$ **"New Blueprint Instance"**.
4. Connect your `LexMetra` repository.
5. Render will detect `render.yaml` and provision:
   - **`lexmetra-db`**: Managed PostgreSQL database.
   - **`lexmetra-backend`**: Docker Web Service running the FastAPI app.
6. Click **"Apply"**. Both services will build and deploy automatically.

---

### Method B: Manual Deployment on Render

#### Step 1: Create PostgreSQL Database on Render
1. In Render Dashboard, click **"New +"** $\rightarrow$ **"PostgreSQL"**.
2. Set:
   - **Name**: `lexmetra-db`
   - **Database**: `lmpc_db`
   - **User**: `lmpc_user`
   - **Region**: `Oregon (US West)` (or your preferred region)
   - **Plan**: `Free`
3. Click **"Create Database"**.
4. Copy the **Internal Database URL** (for Render web service) and **External Database URL** (for local migrations).

#### Step 2: Create Web Service (Docker) on Render
1. Click **"New +"** $\rightarrow$ **"Web Service"**.
2. Select **"Build and deploy from a Git repository"** and select your `LexMetra` repository.
3. Configure the settings:
   - **Name**: `lexmetra-backend`
   - **Region**: Same as your database (e.g. `Oregon`)
   - **Branch**: `main`
   - **Root Directory**: Leave blank (uses repository root)
   - **Runtime**: `Docker`
   - **Dockerfile Path**: `./backend/Dockerfile`
   - **Docker Context**: `.`
   - **Instance Type**: `Starter` or `Standard` (needs at least 512MB RAM for OCR models)

#### Step 3: Configure Environment Variables in Render
Go to the **"Environment"** tab of your `lexmetra-backend` service and configure:

| Key | Value / Source | Purpose |
| :--- | :--- | :--- |
| `DATABASE_URL` | From Database (`lexmetra-db` $\rightarrow$ connection string) | PostgreSQL connection |
| `PORT` | `8000` | Web server listening port |
| `ENVIRONMENT` | `production` | Enables production security & caching |
| `CORS_ORIGINS` | `https://lexmetra-ui.vercel.app,http://localhost:5173,http://localhost:4173` | Allowed frontend domains |
| `SECRET_KEY` | *(Click "Generate" for random 64-char string)* | JWT authentication signing |
| `OCR_ENGINE` | `tesseract` | Primary OCR engine |
| `DEV_MODE` | `true` | Bootstraps demo inspector and rules |
| `BOOTSTRAP_DEMO_USERS`| `true` | Seeds demo accounts (`inspector`, `admin`) |

#### Step 4: Health Check Verification
Render will ping `GET /health`. Once complete, the service will show **"Live"**.
- Health check: `https://lexmetra-backend.onrender.com/health`
- Swagger docs: `https://lexmetra-backend.onrender.com/docs`

---

## PART 3: Ngrok Secure Tunnel Setup (Local to Cloud Bridge)

If you are running the high-performance local backend (with local GPU or local database) and want the public Vercel frontend to seamlessly talk to it:

### Step 1: Start PostgreSQL and Backend Locally
```bash
# Terminal 1: Start PostgreSQL 18
./start_postgres.sh

# Terminal 2: Start FastAPI Backend
cd backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### Step 2: Launch Ngrok Tunnel
```bash
# Terminal 3: Start Ngrok on port 8000
ngrok http 8000
```
Or with a static custom domain:
```bash
ngrok http --domain=rise-sponsor-juvenile.ngrok-free.dev 8000
```

### Step 3: Transparent Ngrok Warning Bypass
The LexMetra frontend in `src/lib/api-client.ts` automatically attaches the required header `ngrok-skip-browser-warning: true` to every outgoing request, ensuring zero interstitial blocking on the free tier of Ngrok.

---

## Summary of Useful Commands

| Task | Command | Directory | Purpose |
| :--- | :--- | :--- | :--- |
| **Check Local Ports** | `ss -tulpn \| grep -E '8000\|5433\|4040\|5173'` | Root / Anywhere | Verify active listeners on backend, DB, tunnel, and Vite |
| **Frontend Dev Server** | `npm run dev` | `frontend/react-app/` | Starts Vite HMR dev server on port 5173 |
| **Frontend Preview** | `npm run preview` | `frontend/react-app/` | Tests compiled production distribution on port 4173 |
| **Build Frontend** | `npm run build` | `frontend/react-app/` | Runs `tsc && vite build` generating optimized bundle |
| **Vercel Prod Deploy** | `vercel deploy --prod` | `frontend/react-app/` | Deploys directly to Vercel production edge |
| **Vercel Set Alias** | `vercel alias set <deploy-url> lexmetra-ui.vercel.app` | `frontend/react-app/` | Binds custom production alias to deployment |
| **Backend Health Check**| `curl -s http://localhost:8000/health` | Anywhere | Verifies FastAPI Uvicorn engine and DB status |
| **Backend Swagger Docs**| `http://localhost:8000/docs` | Browser | Interactive OpenAPI specification and test console |
| **Start Local PostgreSQL**| `./start_postgres.sh` (or `pg_ctlcluster 18 main start`) | Root | Launches PostgreSQL on port 5433 with `lmpc` database |

---

## Vercel CLI Complete Command Reference

| Command | Flags / Arguments | Description & Operational Impact |
| :--- | :--- | :--- |
| `vercel login` | `--github` / `--token` | Authenticates Vercel developer CLI session. |
| `vercel link` | `--yes` | Links local directory to active project (`lexmetra-ui`). |
| `vercel build` | `--prod` | Compiles optimized serverless edge distribution locally. |
| `vercel deploy` | `--prod` / `--prebuilt` | Uploads and activates production release across Vercel Global Edge. |
| `vercel alias set` | `<deployment-url> <domain>` | Points production domain (`lexmetra-ui.vercel.app`) to deploy hash. |
| `vercel env add` | `<KEY> <production\|preview>` | Sets production environment variables (`VITE_API_BASE_URL`). |
| `vercel env ls` | None | Lists configured environment variables across environments. |
| `vercel inspect` | `<url> --logs` | Streams live build and edge function execution logs. |

---

## Render Cloud Container Specifications & Resource Matrix

| Setting / Metric | Recommended Value | Free Tier Limits | Starter / Production Spec |
| :--- | :--- | :--- | :--- |
| **Runtime Engine** | Docker (`./backend/Dockerfile`) | Debian 12 / Python 3.12 | Dedicated Container |
| **CPU Allocation** | 0.5 - 1.0 vCPU | Shared CPU | 1.0 vCPU Dedicated |
| **Memory Allocation** | 512 MB - 1 GB RAM | 512 MB (Spins down on idle) | 1 GB - 2 GB RAM (Zero sleep) |
| **Cold Start Latency** | Instant (Starter) | ~45-50s on initial wake | < 1s sustained |
| **Disk Storage** | Ephemeral / Render Disk | 512 MB ephemeral | 10 GB Persistent Disk (Optional) |
| **Health Check Path** | `/health` | Verified every 60s | Continuous liveness probe |
| **Database Binding** | Internal URL (`dpg-...:5432`) | 1 GB storage, 97 connections | Automated continuous backups |

---

## Production Troubleshooting & Error Resolution Matrix

| Symptom / Error | Root Cause | Diagnosis Command | Resolution Procedure |
| :--- | :--- | :--- | :--- |
| **HTTP 401 Unauthorized** during Vercel CLI deploy | Expired token or mismatched team scope | `vercel whoami && vercel teams ls` | Run `vercel link --yes` to select active team, then retry deploy. |
| **HTTP 429 Too Many Requests** from Groq / Gemini | Public rate limit reached on vision perception | Check backend logs: `docker logs` / Uvicorn stdout | Ensure `GEMINI_API_KEY` is set; the system will use Gemini Flash Lite (~1.4s) with fallbacks. |
| **HTTP 502 Bad Gateway** on Render backend | Render container cold start or out-of-memory | `curl -i https://lexmetra-backend.onrender.com/health` | Allow 45s for free-tier spin-up, or upgrade web service to Starter tier for zero idle sleep. |
| **CORS Blocked by Origin** in browser console | Frontend domain not present in backend CORS allowlist | Inspect browser DevTools Network tab | Verify `CORS_ORIGINS` in Render includes `https://lexmetra-ui.vercel.app`. |
| **Ngrok Browser Interstitial Warning** | Free tier Ngrok displays confirmation page | `curl -sI https://...ngrok-free.dev` | Frontend automatically sends `ngrok-skip-browser-warning: true` in `api-client.ts`. |
| **Database Connection Refused** (Port 5433/5432) | PostgreSQL daemon is not listening | `ss -tulpn \| grep 5433` | Run `./start_postgres.sh` locally or verify Render Internal Database URL. |

---

## Production Pre-Flight Checklist

- [x] **Frontend Assets Built**: Clean TypeScript compilation (`npm run build` exits with code 0).
- [x] **Favicons & Manifest Present**: `favicon.ico`, PNG touch icons, and `site.webmanifest` loaded in `public/`.
- [x] **Search Engine Crawlers**: `robots.txt` and `sitemap.xml` accessible at root URLs.
- [x] **Open Graph Meta**: `og:image` (1200x630), `og:title`, and `og:description` dynamically populated.
- [x] **Zero Horizontal Scroll**: Verified on mobile viewports (320px to 414px) with no layout clipping.
- [x] **API Connectivity**: Frontend client resolves `VITE_API_BASE_URL` with automatic Ngrok bypass header.
- [x] **Database Migrations**: 11 PostgreSQL tables initialized and verified with seed inspector accounts.
- [x] **Statutory Citations**: All verdicts and reports cite Section 18/36 and LMPC Rules 2011 with zero placeholder text.

