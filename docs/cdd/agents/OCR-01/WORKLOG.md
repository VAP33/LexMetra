# WORKLOG — OCR-01

## 2026-09-16 — Additive language + provenance; Paddle left unverified
- What I did:
  - Kept Tesseract as the production path. Added `source_engine` on `OcrLine` for EVID-01.
  - Routed `LMPC_OCR_LANGUAGES` into Tesseract `-l` with `eng` fallback.
  - Did **not** uncomment paddleocr or claim fusion accuracy.
- What I verified:
  - `backend/.venv/bin/python -m pytest backend/tests/test_ocr_languages.py -q` → **3 passed**.
  - `rpm -q tesseract` → not installed. Pre-existing `test_ocr_engine.py` fails on this host for that reason.
- What I did NOT verify:
  - Hindi/Marathi tessdata on a real pack photo.
  - PaddleOCR vs Tesseract on Hair Actives degraded print.
- Files touched:
  - `backend/ocr_extraction.py`, `backend/ocr_engine.py`, `backend/config.py`, `backend/tests/test_ocr_languages.py`, `backend/Dockerfile`
