# STATE — CV-01
Last updated: 2026-09-16

## Current phase
done (honest data-constrained outcome) — classical CV retained; YOLO not shipped

## What exists right now (verified by me, not assumed)
- Inventory (`dataset_paths.dataset_inventory()`, 2026-09-16):
  - synthetic_image_files: **50**
  - real_image_files: **30**
  - annotation_records: **50**, `annotations_marked_synthetic: true`
- `backend/layout_ensemble.py`: `yolo_readiness()` refuses to ship (`enough_for_honest_finetune` requires ≥200 real + ≥200 non-synthetic labels). `detect_layout()` calls classical `detect_regions`.
- No `backend/models/layout_yolov8n.pt`.
- Documented in `docs/cdd/00-REPOSITORY-BASELINE.md` and ARCH-01 D-08.
- Tests: `backend/tests/test_layout_ensemble.py`.

## What is NOT done yet
- A trained detector that beats classical CV on Traya Hair Actives / Hair Vitamin (data does not support an honest claim).

## Blocked on
- Data, not code: more real annotated photos, or a measured fine-tune that beats the baseline.

## Next action
Do not train on 50 synthetic boxes and call it YOLO. If more labels arrive, bake off against the two Traya photos and only then drop weights behind `LMPC_ENABLE_YOLO_LAYOUT`.
