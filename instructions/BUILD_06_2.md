# LexMetra Build 06.2 — Test Import Fix

Build 06 itself is already applied. The full-suite run exposed a Python import-mode
mismatch in two legacy regulatory tests.

The production module `backend/amendments.py` uses package-relative imports
(`from .models ...`), so tests must import it as `backend.amendments` rather than
as the top-level module `amendments`. The same package-qualified convention is used
by the Build 05 tests.

This patch changes only the two tests. No production code is changed.

## Apply

Extract into the LexMetra project root and replace the two files.

Run:

```powershell
$env:PYTHONPATH="backend"
python -m pytest backend\tests\regulatory\test_amendments.py backend\tests\regulatory\test_versioning.py -q
```

Then:

```powershell
$env:PYTHONPATH="backend"
python -m pytest -q
```

Do not rerun `apply_build06.py`.
