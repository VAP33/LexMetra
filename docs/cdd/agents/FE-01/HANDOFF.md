# HANDOFF — FE-01
Prepared: 2026-09-16

## Summary for the next agent (or my future self)
The Inspector surface is `frontend/react-app/`. The three `dashboard.html` tabs (Scan, Inspections/history, Review Queue with a typed reviewer note) are implemented there against the existing FastAPI contracts. `dashboard.html` is frozen, not deleted. The React tree is split so EVID-01 can extend `EvidenceView` without restructuring the app. `npm run build` is green. A live authenticated scan has **not** been run this session because the backend was down.

## What I own that is now stable (safe for others to depend on)
- `frontend/react-app/src/lib/api-client.ts` — auth, scan/sessions, inspections list/detail/review, product history, health, report HEAD.
- `frontend/react-app/src/lib/{types,adapters}.ts` — UI shapes mapped from `ProductInspection` / list rows. Do not fork these; additive fields only, ARCH-01 owns the backend contract.
- `frontend/react-app/src/lib/views.ts` — view registry. Add new screens here.
- `frontend/react-app/src/components/evidence/EvidenceView.tsx` — EVID-01's mount point.
- `docs/cdd/00-REPOSITORY-BASELINE.md` amendment: dashboard FROZEN, React is the Inspector surface.

## What I own that is still in flux (do NOT depend on this yet)
- Authenticated end-to-end of Scan → History → Review Queue → Mark reviewed (needs a running API).
- Evidence overlays on *stored* inspections when the evidence HTTP call fails (scan-payload fallback). Live authenticated round-trip still outstanding.
- `capture.html` integration (explicitly not done).

## Contracts I changed
- None of the frozen backend contracts (`ExtractedFact` / `ProductInspection`). Frontend-only.
- `markReviewed()` now returns `{ status, inspection_id, review_note, reviewed_by }` instead of `void` — matches `POST /inspections/{id}/review`.

## Open questions I could not resolve myself
- ARCH-01: please fold the 2026-09-16 baseline amendment into the frozen voice of `00-REPOSITORY-BASELINE.md` when you next revise it.
- When may `dashboard.html` be deleted? FE-01 must not. Wait until EVID-01 / OCR-01 / RULE-01 say they no longer need it as a live reference.
- Should Review Queue hide already-reviewed rows? Dashboard does not. I matched dashboard.
- POST `/inspections/{id}/review` requires `reviewer` or `admin` (`auth.require_reviewer`). An inspector Quick Login will 403 on Mark reviewed — same as the dashboard would against this backend. Not a frontend bug.
