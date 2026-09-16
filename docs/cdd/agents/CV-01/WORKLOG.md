# WORKLOG — CV-01

## 2026-09-16 — Evaluated YOLO, retained classical CV
- What I did:
  - Counted on-disk data. Built an ensemble seam that does not replace `region_detection.py`.
  - Recorded numbers in the repository baseline (package-required honesty path).
- What I verified:
  - `PYTHONPATH=backend backend/.venv/bin/python -c "from dataset_paths import dataset_inventory; …"` → 50 / 30 / 50 synthetic annotations.
  - `test_layout_ensemble.py` in focused run (24 passed / 3 skipped set).
- What I did NOT verify:
  - ultralytics/YOLOv8n training (intentionally not started).
- Files touched:
  - `backend/layout_ensemble.py`, `backend/dataset_paths.py`, `backend/tests/test_layout_ensemble.py`, `docs/cdd/00-REPOSITORY-BASELINE.md`
