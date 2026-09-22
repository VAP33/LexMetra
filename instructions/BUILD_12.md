# Build 12: Production Safety + Demo Convenience Completion

Build 12 is an additive hardening pass. It preserves the working SIH demo flow while tightening deployment defaults and RAG safety.

## Completed
- Production default is `LMPC_DEV_MODE=false`; local/test/demo explicitly opt in.
- Added `LMPC_DEMO_MODE` for demo UX without conflating it with production mode.
- Preserved backend demo bootstrap accounts behind explicit `LMPC_DEMO_MODE`/dev gating and preserved frontend Quick Admin / Quick Inspector login convenience.
- Added environment-driven `LMPC_MAX_UPLOAD_BYTES` with the existing 12 MB default.
- Added `/ready` dependency-aware readiness probe. `/health` remains a cheap liveness probe.
- Redis readiness is operational-only and can never determine a legal verdict.
- RAG retrieval rejects chunks explicitly marked `publication_state != ACTIVE` while preserving legacy bootstrap chunks that do not carry publication state.
- Historical rule immutability and explicit human activation remain intact from Builds 08-11.

## Safety boundary
AI/OCR extracts evidence. RAG retrieves knowledge. Applicability scopes it. The deterministic rule engine decides compliance. Material uncertainty remains reviewable. Scheduled or draft regulatory knowledge cannot become runtime legal authority merely because a date has arrived.

## Validation
Focused Build 09-12 regression set: 27 passed.

Remaining environment-dependent gates are intentionally not claimed green here: PostgreSQL integration, Docker Compose startup, optional PaddleOCR/Gemini/Anthropic live credentials, and frontend package build require the user's network/runtime environment.
