# STATE — RAG-02
Last updated: 2026-09-16

## Current phase
partial — additive RRF + JSONB table; BGE-M3 not shipped; BM25 retrieve() unchanged

## What exists right now (verified by me, not assumed)
- `HybridRetriever.retrieve()` still lexical hybrid (TEST-BASELINE path).
- Additive `retrieve_with_vectors()` + `reciprocal_rank_fusion`.
- `backend/rag/embeddings.py`: `embedding_backend()` is `sentence-transformers` if installed, else `hash_fallback_not_semantic` (must not be reported as BGE-M3).
- `knowledge_chunk_embeddings` JSONB table (DB-01).
- Tests: `backend/tests/test_rag_wave2.py`.

## What is NOT done yet
- BGE-M3 / FlagEmbedding in requirements as a required dep.
- Qualitative BM25 vs hybrid bake-off on "minimum numeral height under 200g" with gazette chunks (chunks are unsourced bootstrap).
- Native pgvector type.

## Blocked on
- RAG-01 real corpus for a meaningful quality claim.
- Optional: sentence-transformers extra + time for CPU embed.

## Next action
When gazette chunks exist, embed with a real model, compare BM25-only vs RRF, write the query table in WORKLOG. Do not delete BM25.
