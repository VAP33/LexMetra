# DECISIONS — CV-01

## 2026-09-16 — Do not ship undertrained YOLO
- Context: Package default was YOLOv8n fine-tune unless data is too small. 30 real photos + synthetic labels is too small.
- Decision: `ship_trained_model=False`. Classical CV is production. Ensemble function is a no-op validator until weights exist.
- Why: "claim without a command" is the failure mode the CDD exists to prevent.
- Reversible? Yes, after a measured bake-off.
