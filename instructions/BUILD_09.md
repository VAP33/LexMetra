# Build 09 — Regulatory Amendment Lifecycle Completion

Build 08 established historical RAG immutability checks. Build 09 completes the
regulatory lifecycle boundary while preserving the existing inspection/OCR/CV/
PDF/audit/frontend paths.

## What this build delivers

1. **Approval-gated amendment lifecycle**
   - AI/OCR can propose changes.
   - Only a human-reviewed `APPROVED` amendment may be scheduled.
   - No function in this build grants legal approval.

2. **Deterministic publication planning**
   - Every amended rule must map to a proposed `RuleVersion`.
   - Module and source-document identity must match the amendment.
   - Effective dates must match the amendment change when supplied.
   - Duplicate and overlapping version intervals are rejected.
   - Existing historical versions may be supplied to the planner and are checked
     for overlap before publication.
   - The plan is side-effect free and explicitly marks that RAG reindexing is
     required.

3. **Mechanical scheduling and effective-date activation**
   - `APPROVED -> SCHEDULED` is available only after validation.
   - Scheduled versions remain scheduled before their effective date.
   - On/after the approved effective date, the selected scheduled version becomes
     `ACTIVE`.
   - A previous active version is marked `SUPERSEDED` only when a newer approved
     version actually becomes active.
   - Future versions are never activated early.
   - Historical legal text is never rewritten.

4. **RAG persistence enforcement**
   - Existing chunk IDs are immutable.
   - Identical replay is idempotent.
   - Changed legal text/provenance/metadata under an existing chunk ID is rejected.
   - PostgreSQL no longer uses conflict-upsert to rewrite an existing legal chunk.
   - Multiple RAG chunks belonging to the same rule are allowed; the store does
     not incorrectly apply the Build 08 interval validator to ordinary chunk
     collections.

5. **Import/API hygiene**
   - New modules support both package-style imports and the project's existing
     `PYTHONPATH=backend` runtime convention.
   - RAG package exports the new lifecycle functions.

## Safety boundary

```text
AI/OCR extracts -> impact analysis -> HUMAN APPROVAL
                         |
                         v
                 deterministic scheduling
                         |
                         v
                   RAG publication
                         |
                         v
              effective-date activation
```

No model is permitted to decide that a Gazette amendment is legally valid.
No future rule may be used for a historical inspection.
No historical RAG chunk may be rewritten in place.

## Files

- `backend/rag/amendment_pipeline.py`
- `backend/rag/publication.py`
- `backend/rag/store.py`
- `backend/rag/__init__.py`
- `backend/tests/test_build09_amendment_publication.py`

## Verification

Run from the full LexMetra repository:

```powershell
$env:PYTHONPATH="backend"
python -m pytest backend\tests\test_build08_rag_immutability.py backend\tests\test_build09_amendment_publication.py backend\tests\regulatory\test_amendments.py -q
python -m py_compile backend\rag\amendment_pipeline.py backend\rag\publication.py backend\rag\store.py backend\rag\__init__.py
python -m pytest -q
```

The focused Build 09 tests pass in the isolated compatibility harness used while
building this package. The full LexMetra suite must still be run in your complete
local checkout before the ZIP is pushed to `main`.

Do not delete or modify `Chatgpt Patch/` in this build. Duplicate-tree comparison
and final cleanup belong to Build 11 after unique content has been proven absent.
