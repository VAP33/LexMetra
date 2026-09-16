# STATE — OCR-01
Last updated: 2026-09-16

## Current phase
partial — language flag + provenance landed; Paddle fusion not verified on this host

## What exists right now (verified by me, not assumed)
- `backend/ocr_extraction.py`: `OcrLine.source_engine`; `_tesseract_lang_flag()` from `LMPC_OCR_LANGUAGES` (default `eng`).
- `backend/ocr_engine.py`: Tesseract `-l` uses that flag with English fallback; `ImageReading.lines` copies `source_engine` from the observation engine; Paddle still behind `LMPC_ENABLE_PADDLEOCR` (commented optional extra in requirements).
- `backend/config.py`: `OCR_LANGUAGES`, existing `ENABLE_PADDLEOCR`.
- `backend/Dockerfile`: `tesseract-ocr-hin`, `tesseract-ocr-mar` (image not rebuilt this session).
- Tests: `backend/tests/test_ocr_languages.py` — 3 passed (2026-09-16).

## What is NOT done yet
- Uncommenting and verifying `paddleocr` against Traya Hair Actives / Hair Vitamin (including the `800.00` → `goo.o00` case). Host has **no Tesseract binary** (`rpm -q tesseract` not installed), so even the Tesseract path cannot be accuracy-checked here.
- Multilingual *field classification* (explicitly out of this package pass).
- Production fusion bake-off numbers.

## Blocked on
- Host/container with Tesseract 5.x + optional PaddleOCR extra, and the two real Traya photos, to measure whether fusion actually helps.

## Next action
In a Tesseract-equipped environment: run `test_ocr_engine.py` + the two real photos with `LMPC_OCR_LANGUAGES=eng` then `eng+hin+mar`. Only then consider enabling Paddle behind the existing flag and recording Hair Actives digit recovery.
