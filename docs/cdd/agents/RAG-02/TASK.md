# CDD Package — RAG-02 (Vector Retrieval)

(Verbatim from `CDD/Wave 2/RAG-02.md`, copied here for persistent context.)

**Agent ID:** RAG-02
**Depends on:** RAG-01's real corpus for meaningful index population — but you can build the pgvector schema and embedding pipeline in parallel against whatever placeholder content exists today, and re-embed once RAG-01's real corpus lands.

**Purpose:** Add pgvector-backed semantic retrieval alongside (not replacing) the existing, working BM25/TF-IDF `HybridRetriever`, closing the "no semantic/vector retrieval" gap flagged as the RAG system's biggest limitation.

**You must:**
1. Read `backend/rag/retriever.py` fully — understand the existing `HybridRetriever`'s interface before adding a parallel path. The goal is hybrid lexical+semantic, matching the original vision, not a wholesale replacement of working retrieval.
2. Add the `pgvector` Postgres extension (coordinate with DB-01 for the migration — this is a schema change) and an embedding column/table for `KnowledgeChunk`s.
3. Choose a real embedding approach: BGE-M3 is the vision's named target. It's runnable CPU-only via `sentence-transformers` or `FlagEmbedding` for a corpus this size (Legal Metrology gazette text is not large-scale), so a locally-run open model is realistic — don't reach for a paid hosted embedding API unless CPU inference proves too slow in practice; confirm the actual latency before deciding.
4. Combine semantic (vector similarity) and lexical (existing BM25) results — a genuine hybrid, not one gated behind a feature flag that silently disables the other. Score fusion (e.g. reciprocal rank fusion) is a reasonable default; document whatever you choose.
5. Validate retrieval quality qualitatively against a handful of realistic queries (e.g. "what's the minimum numeral height for a package under 200g") — compare BM25-only vs. hybrid results side by side and report which surfaces the correct chunk more reliably, rather than assuming semantic search is automatically better.

**You must NOT:**
- Remove or disable the BM25 path. It stays as one half of the hybrid.
- Block your whole task on RAG-01 finishing — build and test the pipeline against whatever corpus exists now; re-run embedding once real content lands.

## CONTEXT.md

- Current retrieval is TF-IDF/BM25 via `sklearn`, real and working, just not semantic. This is the gap the vision names most explicitly (BGE-M3 + pgvector + hybrid + rerank).
- No GPU confirmed available on the host (verify — don't assume) — CPU-only embedding inference is the default planning assumption; BGE-M3 CPU inference on a modest corpus (dozens to low hundreds of chunks) should be practical within a hackathon time budget.
- `KnowledgeChunk` model (`backend/regulatory/models.py`) is the object you're embedding — don't fork a second representation of chunk content.

## CONTRACTS.md

**Contract you consume:** RAG-01's corpus (`KnowledgeChunk` records); existing `HybridRetriever` interface (`retriever.py`).
**Contract you produce:** the hybrid (lexical+semantic) retrieval interface — document its response shape for whatever consumes retrieval results (rule engine context, amendment diff support, any future explainability UI).
