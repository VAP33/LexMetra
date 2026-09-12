# Build 03: /scan Visual Evidence Integration

The current GitHub main contains `backend/visual_recovery.py`, but `/scan` was
still not calling it before legal evaluation. This patch wires that seam.

Apply from the LexMetra repository root:

    python apply_build03.py

Then verify:

    python -m py_compile backend/main.py backend/visual_recovery.py
    PYTHONPATH=backend python -m pytest backend/tests/test_scan_visual_recovery_integration.py -q

Expected: 2 passed.

Do not replace the existing backend directory. Extract the contents of this
build folder into the repository root.
