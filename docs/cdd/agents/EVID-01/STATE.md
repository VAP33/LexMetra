# STATE — EVID-01
Last updated: 2026-09-16

## Current phase
partial — backend chain + React honesty UI landed; live authenticated round-trip not run

## What exists right now (verified by me, not assumed)
- `backend/evidence_view.py`: `GET /inspections/{id}/evidence` read-model with regions, findings, honesty banners, `verification_status`.
- `backend/main.py`: route registered; optional image URL.
- `frontend/react-app/src/lib/api-client.ts`: `getInspectionEvidence` + restored `getInspectionDetail`.
- `frontend/react-app/src/components/evidence/EvidenceView.tsx`: fetches the chain, shows honesty copy, overlays bboxes, surfaces verification_status. Falls back to scan-payload overlays if the endpoint 404s.
- Tests: `backend/tests/test_evidence_chain.py` passed in the Wave 1/2 focused run (24 passed / 3 skipped overall for that set).

## What is NOT done yet
- Browser-verified evidence page against a running FastAPI+Postgres instance.
- Image bytes for *stored* inspections when only a filesystem path exists (endpoint reports `image_path_present`).

## Blocked on
- Live backend (same as FE-01). Not a contract block.

## Next action
Start API, open an inspection in React, confirm honesty banners and `verification_status` render from `/evidence` (not only the scan payload).
