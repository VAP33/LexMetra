# STATE — FE-01
Last updated: 2026-09-16

## Current phase
done (parity implemented + build verified; live authenticated API round-trip still outstanding)

## What exists right now (verified by me, not assumed)
- `frontend/dashboard.html`: inventoried from source. Three tabs (Scan / Inspections / Review Queue), JWT login, POST `/scan`, GET `/inspections`, GET `/inspections/{id}`, POST `/inspections/{id}/review`. README's "raw OCR shown next to every field" is **not** what the file does — it renders `facts[].extracted_value` and never reads `raw_ocr_fields`.
- `frontend/react-app/`: Vite + React 18 + TypeScript + Tailwind. `npm run build` (`tsc && vite build`) succeeded 2026-09-16: `dist/assets/index-Dj6wW3ji.js` 249.11 kB. Preview served `200` at `http://127.0.0.1:5174/app/`. Login screen + Quick Admin connection-error path verified in the browser.
- Integration layer (`src/lib/api-client.ts`, `adapters.ts`, `types.ts`) already talked to `/auth/login`, `/scan`, `/sessions*`, `/inspections*`, `/extract-preview`, `/health`. Extended, not replaced.
- Component split: `InspectionApp.tsx` is now a thin orchestrator. Screens live under `components/{auth,home,history,scan,result,evidence,report}/`. EVID-01 hook is `components/evidence/EvidenceView.tsx`.
- `frontend/dashboard.html` is **not deleted**. Marked FROZEN in `docs/cdd/00-REPOSITORY-BASELINE.md`.
- `frontend/capture.html` left in place (out of FE-01 scope — calibrated mm capture, not the Inspector dashboard).

## What is NOT done yet
- Live side-by-side against a running FastAPI+Postgres instance (backend was down this session: `curl localhost:8000/health` failed). Authenticated Scan → History → Review Queue → Mark reviewed has not been HTTP-verified.
- TEST-01 has not signed a frontend regression gate (none exists yet; TEST-BASELINE is backend pytest).
- EVID-01's `GET /inspections/{id}/evidence` is not built — EvidenceView currently overlays bboxes already present on the scan/session payload.

## Blocked on
- nothing for the remaining FE-01 code work
- live parity confirmation waits on a running backend (DEVOPS-01 / local `docker compose up`)

## Next action
Start the FastAPI backend, sign in as `admin` / `password123` (demo bootstrap), run one package photo through Scan, confirm it appears on History, confirm Review Queue is `GET /inspections?needs_review=true`, and mark one row reviewed with a typed note. Then ask TEST-01 to record that check. Do not delete `dashboard.html`.
