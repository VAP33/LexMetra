# Claude 1 — everything from this conversation, at real project paths

This folder mirrors the actual project's structure exactly
(`backend/`, `frontend/`, `rules/`, `dataset/`, `handoff/` sit at the same
relative positions they would in the real repo root) so you can diff or
merge selectively. Nothing outside this folder was touched — your existing
`SIH 2026` and `SIH 2026 vision upgrade` project files are untouched and
not duplicated in here.

## Read this before merging anything

Your project has moved substantially since most of this was written —
"Kiro" sessions added auth/RBAC, audit logging, PDF reports, multi-surface
capture sessions, and (in the vision branch) a real multi-engine vision
pipeline. **Do not blindly overwrite your current `backend/` with this
folder's `backend/`** — most of it is now behind what you have. Specifics:

| This folder | Status relative to your current project |
|---|---|
| `backend/main.py`, `rule_engine.py`, `exemption.py`, `unit_price.py`, `schema.py`, `ocr_extraction.py`, `sticker_detection.py`, `product_similarity.py`, `vlm_verifier.py`, `db/` | **Superseded.** Your current backend has all of this plus auth, RBAC, audit trail, evidence retention, session-based multi-surface capture, and PDF reports that this folder doesn't. Keep for reference only. |
| `rules/rules.json` | **Check before replacing.** This may be an earlier version than what's in your current project — compare `rule_id` coverage before overwriting; don't lose any Rule 4/25/26(b)/26(c)/27 entries your current file may have added. |
| `dataset/` (50 synthetic images + generator) | **Still additive** — synthetic pipeline-testing fixtures, doesn't conflict with anything. Safe to keep alongside your `real_photos/` set. |
| `frontend/capture.html`, `frontend/dashboard.html` | **Present in your current project already**, effectively unchanged from this version. `dashboard.html` is flagged in your own `PROJECT_STATE.md` as broken against the now-secured backend (no auth header) — needs that fix regardless of which version you keep. |
| `frontend/react-app/` | **New — not in your current project.** Full React/TypeScript integration (type-checked, zero errors, against real `lucide-react`/React types). **Updated** to match the current backend: real auth (login screen, Bearer token, 401 handling) and real multi-surface capture via `/sessions/*` (previously only the first photo was ever analyzed — now every captured photo is uploaded as its own surface and the legal engine runs against all of them). See `frontend/react-app/INTEGRATION_README.md`'s "Update" section for exactly what changed and what's still unverified (no live end-to-end test yet — no `package.json`/Vite scaffold was provided to actually run it in a browser). |
| `handoff/` (5 workstream briefs + prompts) | Reference for what was originally scoped out for 4 parallel Claude sessions. Cross-check against `PROJECT_STATE.md`'s P0-P3 tables in your current project — some of this is now done, some (tampering/FSSAI/consumer-reporting) explicitly is not, per your own project's Session 2 log. |
| `ENGINE_UPGRADE_NOTES.md`, `README.md`, `SETUP.md` | Historical record of earlier bug fixes and setup steps from this conversation. Superseded by your current project's own `IMPLEMENTATION_STATUS.md`/`PROJECT_STATE.md`, kept here for the record. |
