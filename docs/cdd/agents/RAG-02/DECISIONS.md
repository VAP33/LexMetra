# DECISIONS — RAG-02

## 2026-09-16 — Do not change retrieve()
- Context: TEST-BASELINE covers BM25/TF-IDF behavior.
- Decision: new method `retrieve_with_vectors` rather than changing `retrieve` signature/scores.
- Why: additive, no silent retrieval drift.
- Reversible? Callers can switch later.

## 2026-09-16 — Hash vectors are test-only
- Decision: 64-d SHA256 hash embed when sentence-transformers is missing. Backend string is `hash_fallback_not_semantic`.
- Why: unit tests for RRF must run on CI without downloading BGE-M3.
- Reversible? Replace `embed_text` implementation when the extra is installed.
