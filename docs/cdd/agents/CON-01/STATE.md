# STATE — CON-01
Last updated: 2026-09-16

## Current phase
partial — contract + flagged endpoint + limiter; no public UI (FE-02 is Wave 3)

## What exists right now (verified by me, not assumed)
- `backend/consumer_scan.py`: `ConsumerScanResponse` (`extra="forbid"`). UNCERTAIN has dedicated consumer copy. No bboxes, no rule IDs, no per-engine confidence.
- `POST /consumer/scan` in `main.py`, gated by `LMPC_ENABLE_CONSUMER_SCAN` (default false). IP sliding-window `LMPC_CONSUMER_SCAN_RPM`.
- Persistence: `consumer_scans` (not `inspections`).
- Draft published in `docs/cdd/01-CONTRACTS.md`. ARCH-01 D-06: no consumer RBAC role.
- Tests: `backend/tests/test_consumer_scan.py` in the 24-passed focused set.

## What is NOT done yet
- CAPTCHA
- Device-id / optional phone identity
- FE-02 consumer frontend (out of scope)
- Live HTTP with flag on against a running API

## Blocked on
- Nothing for the published draft. Shipping the flag in production wants DEVOPS-01 cost review.

## Next action
CON-02 / FE-02 / AUTH-01 should build against `ConsumerScanResponse` in `01-CONTRACTS.md`. Do not call Inspector `/evidence`.
