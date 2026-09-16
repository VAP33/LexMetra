# DECISIONS — RULE-03

## 2026-09-16 — Failed redeploy leaves SCHEDULED
- Context: Package: must not silently leave stale rules active.
- Decision: activation helper returns an error and does not set `ApprovalState.ACTIVE` when zip missing/deploy fails.
- Why: A green ACTIVE with yesterday's table is worse than a stuck SCHEDULED.
- Reversible? No.

## 2026-09-16 — Tesseract interim for gazette OCR
- Decision: call `ocr_extraction.run_ocr`, not a new gazette engine. Paddle fusion later if OCR-01 verifies it.
- Why: Package allows Tesseract interim.
- Reversible? Yes.
