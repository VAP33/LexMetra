# WORKLOG — FE-01

## 2026-09-16 — Inventory dashboard.html vs React, then consolidate
- What I did:
  - Read the FE-01 package, `_TEMPLATES.md`, `AGENT-EXECUTION-GUIDE.md`, `00-REPOSITORY-BASELINE.md`, `01-CONTRACTS.md`, ARCH-01 D-02, and EVID-01's package (so the component split has a place for the evidence viewer).
  - Inventoried `frontend/dashboard.html` from source (313 lines). Actual tabs/features:
    1. **Auth** — POST `/auth/login` as `application/x-www-form-urlencoded`; Quick Admin / Quick Inspector (`password123`); Sign Out; Bearer on subsequent calls. Token key `lmpc_token`.
    2. **Scan** — file input + product_id / sale_type / category / net qty / MRP → POST `/scan` multipart. Result: overall_status badge, `price_or_label_change_flag`, facts table (field, status, extracted_value truncated to 60 chars, reason), `nearest_matches` pills, disclaimer.
    3. **Inspections** — GET `/inspections?limit=100`. Columns: ID, Product, Status, MRP, Scanned, Reviewed. Click → GET `/inspections/{id}` facts table + reviewer note + POST `/inspections/{id}/review`.
    4. **Review Queue** — GET `/inspections?needs_review=true&limit=100` (backend filters on `inspection_facts.review_required = TRUE`, not `reviewed = FALSE`).
  - README claim "raw OCR text shown next to every field": **not accurate**. Dashboard never reads `data.raw_ocr_fields`. It shows `f.extracted_value`.
  - Audited `frontend/react-app/`: already a full Inspector (login, home, history, register, review queue, camera scan, session finalize, evidence overlay, report). Gaps vs dashboard: hardcoded review note, client-side review-queue filter (not the API), no MRP in list rows, no raw OCR next to values, Quick Admin only filled the form, everything lived in one 1,882-line `InspectionApp.tsx`.
  - Closed those gaps and split the monolith into bounded screens. Extended `api-client.ts` (`markReviewed` now returns the JSON body; `reportPdfAvailable` sends the Bearer token) and mapped `mrp` / fact `raw_text` through `adapters.ts`.
  - Marked `dashboard.html` FROZEN (not deleted) in `docs/cdd/00-REPOSITORY-BASELINE.md`.
- What I verified (tests run, commands executed, actual output):
  - `cd frontend/react-app && npm install` → "added 135 packages".
  - `cd frontend/react-app && npm run build` → `tsc && vite build` **exit 0**. Vite: `dist/index.html` 0.77 kB, `index-C3UyELl0.css` 27.76 kB, `index-Dj6wW3ji.js` 249.11 kB, "built in 4.55s".
  - `curl -sS -w "%{http_code}" http://127.0.0.1:5174/app/` → `200 text/html`; JS asset `200` / 249168 bytes.
  - Browser at `http://127.0.0.1:5174/app/`: Sign in, Quick Admin, Quick Inspector, Sign in disabled until credentials. Clicked Quick Admin → filled `admin` / `password123` → "Could not reach the inspection service. Check your connection." (backend down — honest failure).
  - `curl localhost:8000/health` → connection refused (`000down`). No live Scan/Inspections/Review round-trip this session.
- What I did NOT verify (assumed, or deferred):
  - Did **not** open `dashboard.html` against a live API. Inventory is source-read, not a running-browser confirmation of the three tabs.
  - Did **not** POST `/scan` or `/sessions/*/finalize` with a real photo.
  - Did **not** confirm `needs_review=true` SQL against Postgres.
  - Did **not** confirm reviewer-role 403 vs inspector for POST `/inspections/{id}/review` (backend `require_reviewer` — the UI surfaces the error).
- Files touched:
  - `frontend/react-app/src/components/InspectionApp.tsx` (rewritten as orchestrator)
  - `frontend/react-app/src/components/{ui,layout}.tsx`
  - `frontend/react-app/src/components/auth/{LoginView,ProfileView}.tsx`
  - `frontend/react-app/src/components/home/HomeView.tsx`
  - `frontend/react-app/src/components/history/ListViews.tsx`
  - `frontend/react-app/src/components/scan/ScanFlow.tsx`
  - `frontend/react-app/src/components/result/ResultView.tsx`
  - `frontend/react-app/src/components/evidence/EvidenceView.tsx`
  - `frontend/react-app/src/components/report/ReportView.tsx`
  - `frontend/react-app/src/lib/{api-client,adapters,types,views,format}.ts`
  - `frontend/react-app/src/index.css`, `frontend/react-app/tailwind.config.js`
  - `docs/cdd/00-REPOSITORY-BASELINE.md`
  - `docs/cdd/agents/FE-01/*`
