# Build 03 Fixed: Actual /scan Integration

The previous Build 03 commit added the regression test but did not modify
`backend/main.py`. This fixed patch targets the `/scan` endpoint boundaries
explicitly, so the change cannot accidentally land in `/extract-preview`.

Apply from repository root:

    python apply_build03_fixed.py

Verify:

    python -m py_compile backend/main.py backend/visual_recovery.py
    PYTHONPATH=backend python -m pytest backend/tests/test_scan_visual_recovery_integration.py -q

Expected: 2 passed.
