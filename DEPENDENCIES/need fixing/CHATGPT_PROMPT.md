# ChatGPT Diagnostic Prompt: LMPC Inspection & OCR Pipeline

Copy and paste the prompt below into ChatGPT along with the files in this folder:

---

```markdown
I am developing an automated Legal Metrology (LMPC) Packaged Commodity Inspection Platform. The stack is FastAPI (Python 3.12) on the backend and React (Vite/TypeScript) on the frontend.

I have uploaded the core pipeline files:
1. `ocr_extraction.py` - Regex-based field extraction and classification
2. `ocr_engine.py` - Tesseract OCR pipeline with variant filtering
3. `preprocess.py` - Image enhancements (CLAHE, glare removal, thresholding)
4. `vlm_verifier.py` - Semantic VLM ambiguity verification
5. `rule_engine.py` - Deterministic legal rule engine (Rules 6, 7, 8, 9, etc.)
6. `main.py` - FastAPI orchestration (/extract-preview, /scan, /sessions, /finalize)
7. `geometry.py` - Package & Principal Display Panel (PDP) bounding box detection
8. `adapters.ts` - Frontend adapter translating backend facts & findings into UI models

### The Problem:
When testing real product photos (e.g., curved coffee jars, snack bags with glare):
1. **OCR Detection & Extraction Fails / Partial:**
   - Essential fields like Net Quantity, Manufacturer Name/Address, and Consumer Care are either not recognized at all or come out as partial fragments (e.g., missing numbers due to glare or curvature).
2. **VLM (Vision-Language Model) appears inactive:**
   - `vlm_verifier.py` seems disconnected from the actual OCR image reading. Is it only doing post-hoc text ambiguity checks rather than helping read difficult, glared, or curved text? How do we make multimodal vision assist OCR extraction when Tesseract confidence is low?
3. **Computer Vision (CV) Status is opaque:**
   - Sticker detection, geometry detection, and PDP area calibration don't seem to pass real measurements down to the rules, causing font-height rules to always return UNCERTAIN.
4. **Inspection Results Show "Not Detected" Everywhere:**
   - In the frontend inspection view, almost every mandatory declaration displays:
     - Value: `Not detected`
     - Reason: `No further detail available for this field.`
   - This leaves the inspector with zero diagnostic information as to why a field failed (e.g., whether OCR saw nothing, whether regex pattern matched nothing, or whether evidence was missing).

### What I Need You To Do:
1. **Trace the Pipeline End-to-End:**
   - Trace how an image moves from `main.py` -> `ocr_engine.py` -> `preprocess.py` -> `ocr_extraction.py` -> `rule_engine.py` -> `adapters.ts`.
   - Identify where the breakdown occurs that causes fields to be dropped or marked "Not detected".
2. **Fix OCR & Extraction Brittleness:**
   - Show how to tune `preprocess.py` and `ocr_extraction.py` so real-world curved/glared text isn't lost by rigid regexes.
   - Propose an active fallback to Gemini / Multimodal VLM specifically for reading high-uncertainty cropped regions.
3. **Fix the "No further detail available" Issue:**
   - Modify `rule_engine.py` and `main.py` so every unobserved or failing declaration provides a concrete diagnostic reason (e.g., `"No text matching net weight patterns (e.g. 'Net Wt: 150g') found across 2 captured surfaces"` instead of returning `null` reason).
   - Ensure `adapters.ts` surfaces these reasons properly.
4. **Provide Concrete Code Fixes:**
   - Give me the exact code diffs/replacements for the attached files to make this pipeline reliable on real phone photos.
```
