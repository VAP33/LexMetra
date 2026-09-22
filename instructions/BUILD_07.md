# LexMetra Build 07 - Approval-Gated RAG Publication

## Purpose
Prevent unapproved amendment material from becoming searchable legal knowledge.

## Changes
- Add `backend/rag/publication.py`.
- Publication is allowed only for `APPROVED`, `SCHEDULED`, or `ACTIVE` amendment drafts.
- Every published chunk must match the amendment module and source document.
- Add focused tests covering blocked drafts and provenance mismatch.

## Apply
Copy the files from this ZIP into the repository root. No existing production file is replaced.

## Verify
```powershell
$env:PYTHONPATH="backend"
python -m pytest backend\tests\test_build07_rag_publication.py -q
$env:PYTHONPATH="backend"
python -m pytest -q
```

Do not push until the full suite is green.
