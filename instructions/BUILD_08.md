# LexMetra Build 08 — RAG Historical Integrity

## Purpose

Extend the Build 07 approval gate with immutable knowledge identity and strict effective-date interval validation. This build does not replace the existing RAG retriever, ingestion pipeline, rule engine, PDF/reporting, audit, or UI.

## Files

- `backend/rag/publication.py` — additive safety helpers for immutable chunks and non-overlapping legal intervals.
- `backend/tests/test_build08_rag_immutability.py` — focused regression tests.

## Apply

Extract this ZIP into the repository root and replace/add the contained files.
Do not run any prior build apply script.

## Verify

```powershell
$env:PYTHONPATH="backend"
python -m pytest backend\tests\test_build07_rag_publication.py backend\tests\test_build08_rag_immutability.py -q

$env:PYTHONPATH="backend"
python -m pytest -q
```

## Safety contract

1. Existing chunk content/provenance cannot be silently rewritten under the same chunk id.
2. Invalid effective-date intervals are rejected.
3. Overlapping intervals for the same module/rule identity are rejected.
4. Adjacent historical intervals remain valid.
5. No existing production workflow is removed or bypassed.
