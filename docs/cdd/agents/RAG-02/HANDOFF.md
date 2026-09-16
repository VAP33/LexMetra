# HANDOFF — RAG-02
Prepared: 2026-09-16

## Summary for the next agent (or my future self)
Lexical retrieval still works. Semantic fusion is an opt-in method plus a JSONB table. Do not advertise BGE-M3 until `embedding_backend()` returns a real model name after a successful encode.

## What I own that is now stable
- RRF helper
- Unchanged `retrieve()`

## What I own that is still in flux
- Vector quality
- pgvector extension

## Contracts I changed
- Additive retrieval method. Draft note in `01-CONTRACTS.md`.

## Open questions
- Should rule-engine explainability call `retrieve_with_vectors` yet? Not wired; keep BM25 until gazette lands.
