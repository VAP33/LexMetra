# HANDOFF — CV-01
Prepared: 2026-09-16

## Summary for the next agent (or my future self)
Layout detection is still `region_detection.py`. `detect_layout()` is the future YOLO hook. EVID-01/OCR-01 keep consuming the same bbox shape.

## What I own that is now stable
- Honesty notes on DetectionResult when YOLO is absent.
- Inventory helper `dataset_paths.dataset_inventory()`.

## What I own that is still in flux
- Any future weights file (must not appear without numbers).

## Contracts I changed
- None. Same `ExtractedFact`/bbox shape.

## Open questions
- GPU/CPU training budget when more labels exist. Host GPU was not assumed.
