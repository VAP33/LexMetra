# CDD Package — CV-01 (Layout Detection Upgrade)

(Verbatim from `CDD/Wave 2/CV-01.md`, copied here for persistent context.)

**Agent ID:** CV-01
**Depends on:** nothing blocking — start immediately.

**Purpose:** Improve on `region_detection.py`'s classical-CV layout detection where a real, time-boxed effort can honestly move the needle — without pretending a full YOLO retrain is free.

**You must:**
1. Read `region_detection.py`'s module docstring in full first — it's explicit about what current detections do and don't mean (text regions ≠ mandatory-declaration regions, package boundary ≠ legal Principal Display Panel). Any upgrade must preserve this honesty, not quietly imply more certainty than the detector has.
2. Check what's actually available to train on: `dataset/annotations/annotations.json` (synthetic) plus whatever real photos exist under `dataset/real images/`. Be realistic about sample size before committing to a training approach — a handful of real images is not enough to train a robust YOLO model from scratch, but may be enough to fine-tune a pretrained small model (e.g. YOLOv8n) as a genuine improvement over pure heuristics, especially combined with synthetic augmentation.
3. **Default plan (do this unless you find a clearly better option):** fine-tune a small pretrained YOLO model on the available annotated + synthetic data, and run it as an **ensemble validator alongside** the existing classical-CV detector (not a wholesale replacement) — use classical CV's heuristic regions as a fallback/sanity-check when the trained model's confidence is low, rather than trusting either blindly.
4. If, after a genuine attempt, the available data proves too small to produce a trained model that beats the classical baseline on the two real product photos (Traya Hair Actives, Traya Hair Vitamin) — **that's an acceptable outcome.** Document it plainly in `00-REPOSITORY-BASELINE.md` (via ARCH-01) as "YOLO evaluated, data-constrained, classical CV retained as production path" with your actual numbers, rather than shipping an undertrained model that quietly performs worse. This is the safest-minimal-default the CDD process calls for when a full solution isn't achievable in scope — a documented, honest limitation, not a silent gap.
5. Whatever you ship, it must plug into the exact same `ExtractedFact`/bbox output shape EVID-01 and OCR-01 already consume — no contract change without ARCH-01 sign-off.

**You must NOT:**
- Ship a trained model as "done" without reporting real accuracy numbers against the same test cases the classical detector was validated on — that would be exactly the "claim without a command" violation the whole CDD process exists to prevent.
- Remove the classical-CV path. It's the fallback either way.

## CONTEXT.md

- `region_detection.py` (~60K) is the current, honestly-documented classical-CV detector.
- Dataset reality: `dataset/annotations/annotations.json` (synthetic, per `02-DEPENDENCIES-CLASSIFICATION.md`'s findings on dataset paths), `dataset/real images/` (a handful of real product photos), `dataset/images dataset/` (the real path — not the dead `DEPENDENCIES/` fallback some older tools still reference).
- Runtime: podman is available for any containerized training/inference tooling; no GPU availability confirmed — check what's actually on the host before assuming GPU-accelerated training is feasible, and plan for CPU-only fine-tuning if not.

## CONTRACTS.md

**Contract you consume:** `ExtractedFact`/bbox output shape (from ARCH-01/`schema.py`) — whatever detector you ship must populate the same structure.
**Contract you produce:** updated (or unchanged, if you land on "classical CV retained") region-detection output for OCR-01 and EVID-01 to consume — coordinate any shape change with both directly.
