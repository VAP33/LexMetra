# LexMetra Build 04 — RAG Runtime Integrity

## Objective
Make the existing regulatory/RAG architecture import-safe without moving or rewriting
the existing canonical `backend/models.py`, and declare the RAG runtime dependencies
already used by the implementation.

## Changes
1. Add `backend/regulatory/` as a compatibility package.
   - `regulatory.models` re-exports the canonical models from `backend/models.py`.
   - This preserves the existing RAG imports while keeping one canonical model source.
2. Add `scikit-learn` because `backend/rag/retriever.py` already imports TF-IDF/cosine APIs.
3. Add `pypdf` because `backend/rag/ingest.py` already imports `PdfReader`.
4. Add focused tests for the compatibility import and RAG filtering.

## Safety
No legal rule content is changed.
No inspection engine behavior is changed.
No PDF/reporting or audit code is changed.
No amendment activation behavior is changed.
No automatic legal activation is introduced.

## Apply
Run from the repository root:

    python apply_build04.py

Then:

    $env:PYTHONPATH="backend"
    python -m pytest backend/tests/test_build04_rag_runtime_integrity.py -q

Then:

    python -m py_compile backend/regulatory/__init__.py backend/regulatory/models.py backend/rag/*.py

Inspect the diff before committing.
