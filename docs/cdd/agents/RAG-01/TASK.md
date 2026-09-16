# CDD Package — RAG-01 (Legal Knowledge Ingestion)

(Verbatim from `CDD/Wave 2/RAG-01.md`, copied here for persistent context.)

**Agent ID:** RAG-01
**Depends on:** nothing blocking — start immediately. RAG-02 needs your real corpus before their vector index is meaningful, so prioritize getting real content in over building elaborate ingestion tooling.

**Purpose:** Replace/extend whatever placeholder or minimal corpus exists in `rag/ingest.py`/`default_corpus.py` with real Legal Metrology Act 2009 + LMPC Rules 2011 gazette text, chunked and versioned through the existing (working, tested) immutability/publication governance.

**You must:**
1. Read `backend/rag/ingest.py`, `default_corpus.py`, and `publication.py` fully — the chunking, immutability, and effective-dating governance is already `VERIFIED_WORKING` and tested (`test_build07_rag_publication.py`, `test_build08_rag_immutability.py`). You're feeding real content through an existing, correct pipeline, not building new governance.
2. Source real gazette/Act text for at least the rules already encoded in `rules/rules.json` (Rules 3, 6, 7, 8, 12, 26, 27, 32, Second Schedule) — official government sources where possible (India Code, Legal Metrology division publications). Document your sources per chunk so provenance is traceable, matching the existing "every legal finding must be traceable to its evidence" discipline (`01-CONTRACTS.md` §1.3.5) extended to knowledge chunks.
3. Chunk at a granularity that supports the retrieval use case: a rule engine or human reviewer citing "why does this requirement exist" needs chunk boundaries that correspond to actual legal sections, not arbitrary character windows.
4. Version and publish through the existing immutable pipeline — once published, a chunk doesn't change; a correction is a new version, exactly like the existing rule-versioning pattern.
5. This corpus becomes RAG-02's embedding target — coordinate timing so you're not still actively re-chunking while they're indexing (a stable-but-partial corpus is fine to hand off; a moving target isn't).

**You must NOT:**
- Fabricate or paraphrase legal text as if verbatim — if you can't source the authoritative text, mark that chunk clearly as unsourced/placeholder rather than presenting synthesized text as gazette content.
- Change the chunking/immutability governance code itself — that's tested and working; you're a content producer feeding it, not its maintainer.

## CONTEXT.md

- `backend/rag/` module: `ingest.py`, `default_corpus.py`, `publication.py`, `retriever.py` (BM25/TF-IDF hybrid — RAG-02's territory, not yours). Your scope is `ingest.py`/`default_corpus.py` content quality and coverage.
- `KnowledgeChunk`/`RegulatoryContext` models live in `backend/regulatory/models.py` — reuse these, don't invent new ones.
- Every rule in `rules/rules.json` carries `verification_status: needs_official_verification` — your sourcing work here is directly useful evidence for whoever (the human Legal Lead) eventually resolves that status, even though resolving it isn't your job.

## CONTRACTS.md

**Contract you consume:** existing `KnowledgeChunk`/publication pipeline (`backend/rag/publication.py`, `backend/regulatory/models.py`) — unchanged.
**Contract you produce:** the real corpus RAG-02 indexes. Confirm with them when a stable snapshot is ready for embedding.
