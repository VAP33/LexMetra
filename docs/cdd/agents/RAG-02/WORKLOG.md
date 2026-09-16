# WORKLOG — RAG-02

## 2026-09-16 — Additive hybrid, hash fallback labeled non-semantic
- What I did:
  - Left `retrieve()` alone. Added RRF path and embedding helper that refuses to call the hash vector "BGE-M3".
- What I verified:
  - `test_rag_wave2.py` in focused run.
- What I did NOT verify:
  - Retrieval quality vs a real gazette corpus.
  - `sentence_transformers` import (absent → hash fallback).
- Files touched:
  - `backend/rag/retriever.py`, `backend/rag/embeddings.py`, `backend/tests/test_rag_wave2.py`
