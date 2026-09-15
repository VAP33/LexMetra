# CDD Package — FE-01 (Inspector Frontend — Consolidation onto React)

(Verbatim from `CDD/Wave 1/4 FE-01.md`, copied here for persistent context.)

**Agent ID:** FE-01
**Role:** Execute the project owner's decision to standardize the Inspector frontend on the React app, retiring `dashboard.html` once parity is reached.

**Purpose:** Bring `frontend/react-app/` up to feature parity with `frontend/dashboard.html`, then keep it as the single Inspector surface going forward.

**You must:**
1. Inventory `dashboard.html`'s actual features first (per README: Scan tab — photo → pipeline → verdict with raw OCR shown next to fields; Inspections tab — Postgres-backed history; Review Queue tab — filters to `review_required=true`, lets a human mark reviewed with a note). Verify each of these actually works in the current dashboard before treating it as a parity target — don't assume the README description is still accurate without checking.
2. Look at what the React app already has: `InspectionApp.tsx` plus `lib/api-client.ts`, `adapters.ts`, `types.ts`. This is real scaffolding, not empty — understand what it already talks to before adding to it.
3. Build out the React app to cover all three dashboard.html tabs' functionality, using the existing `api-client.ts` as the integration layer to the FastAPI backend (extend it, don't replace it, unless it's genuinely inadequate — check first).
4. Once parity is reached and confirmed (ideally by having TEST-01 or a manual side-by-side check), mark `dashboard.html` as frozen in `docs/cdd/00-REPOSITORY-BASELINE.md` (coordinate with ARCH-01) — do not delete it until EVID-01 and other agents relying on it as a reference during their own development confirm they're done needing it.
5. This is where EVID-01's evidence viewer component and any future CON-01/FE-02 consumer work should eventually live — architect the React app's routing/component structure with room for that, not as a single monolithic component if avoidable.

**You must NOT:**
- Start building new Inspector features that don't exist in `dashboard.html` yet — parity first, expansion later (that's a separate, lower-priority task once this core migration is done).
- Delete `dashboard.html` unilaterally. That's ARCH-01's call once other agents confirm they no longer need it as reference.

## CONTEXT.md

- `frontend/dashboard.html` (16K) — no build step, opens directly in a browser, talks to the API over CORS. Functional today per the README, not "designed" (no bounding-box overlays, no mobile layout, no bulk actions).
- `frontend/react-app/` — Vite + React 18 + TypeScript + Tailwind, `lucide-react` for icons. Has a real `package.json` with working scripts (`dev`, `build`, `preview`). Two component files: `main.tsx`, `components/InspectionApp.tsx`. `lib/` has `api-client.ts`, `adapters.ts`, `data-url.ts`, `types.ts` — this suggests someone already started wiring API integration; read `api-client.ts` first rather than assuming a blank slate.
- `frontend/capture.html` (12K) is a third, separate frontend file — a calibrated capture tool (overlay guide + ID-1 reference card for real millimeter measurements). Confirm with ARCH-01 whether this stays separate (it's a different use case — capture-time calibration vs. review dashboard) or needs folding into the React app too; don't assume it's in scope without checking.

## CONTRACTS.md

**Contract you consume:** every backend endpoint under `/inspections*`, `/scan`, `/products/*/history`, `/auth/*` — these already exist and are stable; build against them as documented in Section E's Contract Map, not against assumptions.
**Contract you produce:** the React app's component structure becomes the base EVID-01 (evidence viewer) and eventually CON-01/FE-02 build into — keep this loosely coupled (clear component boundaries) so those additions don't require restructuring your work.
