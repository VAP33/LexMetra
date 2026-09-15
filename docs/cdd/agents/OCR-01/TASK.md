# CDD Package — OCR-01 (OCR Upgrade)

(Verbatim from `CDD/Wave 1/2 OCR-01.md`, copied here for persistent context.)

**Agent ID:** OCR-01
**Role:** Bring OCR closer to the vision's PaddleOCR+Tesseract fusion and Hindi/Marathi multilingual target, without breaking the existing (working, tested-against-real-photos) Tesseract pipeline.

**Purpose:** Add PaddleOCR as a second OCR engine alongside Tesseract, fuse their outputs, and extend language support beyond English — incrementally, behind flags, never replacing the working path outright.

**You must:**
1. Read `backend/ocr_extraction.py` and `backend/ocr_engine.py` fully before changing anything — they already contain three layered fixes for real bugs (line-splitting at horizontal gaps, digit-fragment merging, rank-based label/value pairing) that are load-bearing. Don't refactor these away while adding PaddleOCR.
2. Uncomment and properly integrate `paddleocr` (currently commented out in `requirements.txt` as a deliberate "lightweight MVP" choice) behind a feature flag (`LMPC_ENABLE_PADDLEOCR`, which already exists in `docker-compose.yml` — it's just unused right now).
3. Build the fusion layer the README calls "Existing LexMetra fusion" plus PaddleOCR — when both engines run, combine results rather than picking one blindly; the existing digit-fragment-merging logic is a good model for how confidence-aware merging should work here.
4. Add Hindi and Marathi language support — Tesseract has language packs (`tesseract-ocr-hin`, `tesseract-ocr-mar`) that are a lower-risk first step than retraining anything; PaddleOCR also has multilingual models. Do the language work as an additive path (a `language` parameter routed to the right model/pack), not a rewrite of the field-classification regex logic, which is currently English-pattern-specific and will need separate work per language, not a one-shot generalization.
5. Test against the two real product photos already in the repo (Traya Hair Actives, Traya Hair Vitamin) plus the specific known-hard case (Hair Actives' degraded print causing `800.00` → `goo.o00`-style misreads) — this is the concrete bar to clear, not a vague "improve accuracy" goal.
6. Hand your evidence/confidence output format to EVID-01 unchanged unless you coordinate a schema change through ARCH-01 first.

**You must NOT:**
- Remove the Tesseract path. PaddleOCR is additive.
- Attempt full multilingual field-classification (the regex-based label detection) in this pass — that's a larger scope than "OCR." Get multilingual *text extraction* working first; classification generalization can be a follow-up task.

## CONTEXT.md

- `ocr_extraction.py` (64K) and `ocr_engine.py` (88K) are the two files in scope. `paddle_worker.py` (8K) already exists as a stub/scaffold for PaddleOCR — check whether it's usable before writing a new one from scratch.
- Known specific failure mode (from README): the Hair Actives box's lower print/scan quality causes Tesseract's dictionary bias to misread digits as letters badly enough that even the existing targeted digit-whitelist re-OCR pass (`_reocr_digits`) doesn't fully recover it. This is your clearest concrete success/failure signal for whether PaddleOCR fusion actually helps.
- `LMPC_ENABLE_PADDLEOCR` env var already exists in `docker-compose.yml`, defaulted to `false` — it's wired for exactly this feature, just not implemented behind it yet.

## CONTRACTS.md

**Contract you consume:** `ExtractedFact` shape (from ARCH-01/`schema.py`) — your fused OCR output must populate this same structure.
**Contract you produce:** OCR confidence/provenance data for EVID-01's evidence viewer — bbox, source engine (tesseract/paddle/fused), confidence per field. Coordinate the exact shape with EVID-01 directly since you're both Wave 1 and can run in parallel.
