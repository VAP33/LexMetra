# DECISIONS — OCR-01

## 2026-09-16 — Do not enable PaddleOCR in this pass
- Context: Package allows Paddle as additive behind `LMPC_ENABLE_PADDLEOCR`. This host cannot even run Tesseract.
- Options considered: uncomment paddleocr anyway; leave flag off until measured.
- Decision: leave Paddle disabled. Ship language flag + `source_engine` provenance only.
- Why: Honesty over fake completeness. Unverified fusion would look like a quality upgrade without numbers.
- Reversible? Yes — enable the existing flag once a bake-off is recorded.

## 2026-09-16 — Provenance field stays off the frozen ExtractedFact model
- Context: EVID-01 needs engine identity. `ExtractedFact` is `extra="forbid"`.
- Decision: put `source_engine` on `OcrLine` / evidence read-model (`validation` JSON already on facts), not a new required schema.py field.
- Why: Avoid an ARCH-01 SCR for a viewer-only attribute.
- Reversible? Yes.
