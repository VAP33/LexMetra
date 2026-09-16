# HANDOFF — OCR-01
Prepared: 2026-09-16

## Summary for the next agent (or my future self)
Tesseract remains the working path. Language packs are an env flag (`LMPC_OCR_LANGUAGES`) and Docker packages. Each OCR line can name its engine for the evidence viewer. PaddleOCR is still the unused flag it was; do not treat it as verified.

## What I own that is now stable (safe for others to depend on)
- `OcrLine.source_engine`
- `LMPC_OCR_LANGUAGES` / `config.OCR_LANGUAGES`

## What I own that is still in flux (do NOT depend on this yet)
- Paddle fusion quality
- Hindi/Marathi classification (out of scope) and even extraction accuracy on real photos

## Contracts I changed
- None of `ExtractedFact` / `ProductInspection`. Additive provenance only.

## Open questions I could not resolve myself
- Does Paddle recover Hair Actives `800.00` better than `_reocr_digits`? Unmeasured.
