# LexMetra Build 06.1 — Regulatory Test Structure Fix

## Why this patch exists

Build 06 passed its focused tests, but the full suite exposed two stale tests under
`backend/tests/regulatory/`. They imported modules that do not exist in the canonical
runtime package:

- `regulatory.amendments`
- `regulatory.versioning`

The current architecture intentionally keeps the canonical amendment lifecycle in
`backend/amendments.py` and the canonical rule-version selector in
`backend/regulatory/versions.py`. The compatibility `backend/regulatory/models.py`
facade is not a reason to create another duplicate implementation tree.

This patch updates the two stale tests to use those canonical modules. No production
PDF/report/audit/auth/frontend code is changed.

## Files

- `backend/tests/regulatory/test_amendments.py`
- `backend/tests/regulatory/test_versioning.py`

## Apply

Extract this ZIP into the LexMetra project root and replace the two files.

Then run:

```powershell
$env:PYTHONPATH="backend"
python -m pytest backend\tests\regulatory\test_amendments.py backend\tests\regulatory\test_versioning.py -q
```

Then the complete suite:

```powershell
$env:PYTHONPATH="backend"
python -m pytest -q
```

The existing `pytest-asyncio` deprecation warning is not a test failure. It can be
cleaned separately after the functional suite is green.
