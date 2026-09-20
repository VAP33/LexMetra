# LexMetra Production Deployment Guide
> **Blind-Executable Step-by-Step Instructions for Deploying:**
> - **Backend (FastAPI + PostgreSQL + Tesseract)** on **Railway**
> - **Frontend (React 18 + Vite SPA)** on **Vercel**

---

## Architecture Overview

```
 ┌──────────────────────────────┐                ┌───────────────────────────────────┐
 │        Vercel (Edge)         │                │          Railway (Cloud)          │
 │                              │  HTTPS / JSON  │                                   │
 │  React 18 + Vite SPA         ├───────────────►│  FastAPI Backend Engine           │
 │  Domain:                     │                │  Domain:                          │
 │  https://lexmetra.vercel.app │                │  https://backend.up.railway.app   │
 └──────────────────────────────┘                └─────────────────┬─────────────────┘
                                                                   │ Internal Network
                                                                   ▼
                                                 ┌───────────────────────────────────┐
                                                 │   Railway Managed PostgreSQL 16   │
                                                 │   Database: lmpc                  │
                                                 └───────────────────────────────────┘
```

---

## PART 1: Deploy Backend & Database on Railway

### Step 1: Sign up & Create Project on Railway
1. Navigate to [railway.app](https://railway.app/) and sign in using your GitHub account.
2. Click the **"New Project"** button in the dashboard.
3. Select **"Provision PostgreSQL"**.
   - Railway will instantly provision a dedicated PostgreSQL database container.

### Step 2: Retrieve PostgreSQL Connection String
1. Click on the newly created **Postgres** service box.
2. Go to the **"Variables"** tab.
3. Copy the value of `DATABASE_URL` (it will look like `postgresql://postgres:password@junction.proxy.rlwy.net:12345/railway`).
   *(Save this URL; you will paste it into your backend environment variables in Step 4).*

### Step 3: Deploy the Backend Service
1. In the same Railway project canvas, click **"+ New"** (or **"Add Service"**).
2. Select **"GitHub Repo"** and pick your `LexMetra` repository.
3. Railway will open the settings panel for the newly added service:
   - Go to **Settings** $\rightarrow$ **General**:
     - **Service Name**: Change to `lexmetra-backend`.
     - **Root Directory**: Set to `/backend` (or leave as `/` since root `Procfile` is also provided).
     - **Build Pack**: Ensure `Nixpacks` is selected (Nixpacks will automatically detect our `nixpacks.toml` and install `tesseract`, `libGL`, and Python dependencies).
   - Go to **Settings** $\rightarrow$ **Networking**:
     - Click **"Generate Domain"** (e.g. `lexmetra-backend.up.railway.app`).
     - Save this domain URL! This is your backend public URL.

### Step 4: Configure Backend Environment Variables in Railway
Go to your `lexmetra-backend` service $\rightarrow$ **"Variables"** tab $\rightarrow$ Click **"New Variable"** (or **"Raw Editor"**) and configure the following:

```ini
# Server Port (Railway injects PORT automatically, but default is 8000)
PORT=8000

# Database Connection (Paste your Postgres URL from Step 2)
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@junction.proxy.rlwy.net:12345/railway

# Vision & OCR Perception
GEMINI_API_KEY=YOUR_ACTUAL_GEMINI_API_KEY
GEMINI_OCR_MODEL=gemini-3.5-flash-lite

# Fallback Vision Providers (Optional)
GROQ_API_KEY=YOUR_GROQ_API_KEY_IF_ANY
OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY_IF_ANY

# Security & CORS
JWT_SECRET=generate_a_long_random_string_here_e.g_9823fha98dshf928h
ALLOW_ALL_CORS=true
FRONTEND_URL=https://YOUR_VERCEL_APP_NAME.vercel.app

# Bootstrapping (Creates default admin and inspector accounts on first launch)
DEV_MODE=true
BOOTSTRAP_DEMO_USERS=true
```

### Step 5: Verify Backend Deployment
1. Go to the **"Deployments"** tab in Railway.
2. Click on the latest deployment and inspect the **Deploy Logs**.
3. You should see:
   ```text
   INFO:     Started server process
   INFO:     Waiting for application startup.
   [+] [PaddleTextDetector] Using YOLOv8 + OpenCV Region Proposer engine.
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://0.0.0.0:8000
   ```
4. Open your browser and visit:
   `https://lexmetra-backend.up.railway.app/health` $\rightarrow$ Returns `{"status": "ok", "app": "LMPC Compliance Inspection API"}`.
   `https://lexmetra-backend.up.railway.app/docs` $\rightarrow$ Interactive OpenAPI Swagger Documentation.

---

## PART 2: Deploy Frontend on Vercel

### Step 1: Sign up & Import Repository on Vercel
1. Navigate to [vercel.com](https://vercel.com/) and sign in with GitHub.
2. Click **"Add New..."** $\rightarrow$ **"Project"**.
3. Locate your `LexMetra` repository and click **"Import"**.

### Step 2: Configure Vercel Project Settings
On the **Configure Project** screen:
1. **Framework Preset**: Select **Vite**.
2. **Root Directory**: Click **Edit** and select `frontend/react-app`.
3. **Build and Output Settings**:
   - **Build Command**: `npm run build` (Pre-filled)
   - **Output Directory**: `dist` (Pre-filled)
   - **Install Command**: `npm install` (Pre-filled)

### Step 3: Configure Environment Variables in Vercel
Expand the **"Environment Variables"** section and add:

| Key | Value | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | `https://lexmetra-backend.up.railway.app` | **Your exact Railway backend URL** (without trailing slash) |

### Step 4: Deploy & Launch
1. Click **"Deploy"**.
2. Vercel will build the React application (typically finishes in ~25–35 seconds).
3. Once completed, Vercel will display your live production URL (e.g. `https://lexmetra.vercel.app`).

---

## PART 3: Post-Deployment Interconnection & Testing

### Step 1: Update Frontend URL in Railway
1. Return to your Railway dashboard $\rightarrow$ `lexmetra-backend` $\rightarrow$ **Variables**.
2. Update `FRONTEND_URL` to your live Vercel URL (e.g. `https://lexmetra.vercel.app`).
3. Railway will automatically perform a zero-downtime redeploy.

### Step 2: Live Verification Walkthrough
1. Open `https://your-app.vercel.app/` in your desktop or mobile browser.
2. **Login Verification**:
   - Username: `admin`
   - Password: `password123`
   - Click **Login**. You are directed to the **Legal Metrology Inspection Dashboard**.
3. **Navigation / Browser History Verification**:
   - Click **Start Inspection** or select an existing inspection from the table.
   - Click **View Evidence** $\rightarrow$ URL updates to `#evidence/<id>`.
   - Click the **Back** button on your browser $\rightarrow$ Seamlessly returns to `#detail/<id>` without reloading or exiting the site.
4. **Perception & Speed Verification**:
   - Upload sample package photographs (e.g. Bru Coffee or Hershey's).
   - Click **Run Statutory Inspection**.
   - Inspection completes in ~1.5–2 seconds with Gemini Flash acceleration.
5. **Report Download Verification**:
   - In the inspection details view, click **Generate Official Report**.
   - Download the statutory PDF report; verify all stamps, findings, and statutory citations appear clearly.

---

## PART 4: Troubleshooting Common Issues

### Issue 1: Tesseract Missing on Railway
- **Symptom**: Logs display `TesseractNotFound` or `tesseract is not installed or it's not in your PATH`.
- **Solution**:
  - Verify that `backend/nixpacks.toml` is present with `nixPkgs = ["tesseract", "libGL", "glib"]`.
  - In Railway $\rightarrow$ Settings, ensure the Builder is set to **NIXPACKS**.

### Issue 2: CORS Network Error on Vercel
- **Symptom**: Browser console displays `Access to fetch at ... has been blocked by CORS policy`.
- **Solution**:
  - In Railway backend variables, verify `ALLOW_ALL_CORS=true` is set, OR `FRONTEND_URL` exactly matches your Vercel domain.
  - Make sure `VITE_API_BASE_URL` in Vercel does **NOT** end with a trailing slash (`https://backend.up.railway.app`, not `.../`).

### Issue 3: Page Reload on Vercel Returns 404
- **Symptom**: Navigating directly to a sub-URL or refreshing returns a Vercel 404.
- **Solution**:
  - Handled automatically by `frontend/react-app/vercel.json`, which redirects all routes `/(.*)` to `/index.html`.

---

## Summary of Production Endpoints

| Service | Host Provider | URL / Resource |
|---|---|---|
| **Frontend Web App** | Vercel | `https://<your-project>.vercel.app` |
| **Backend API Gateway** | Railway | `https://<your-project>.up.railway.app` |
| **Interactive API Docs** | Railway | `https://<your-project>.up.railway.app/docs` |
| **PostgreSQL Database** | Railway | Dedicated PostgreSQL instance with TLS |
