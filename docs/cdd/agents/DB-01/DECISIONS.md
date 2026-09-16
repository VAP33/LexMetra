# DECISIONS — DB-01

## 2026-09-16 — Wave 2 tables now, Wave 3 later
- Context: Package said don't create unused Wave 2/3 tables. Wave 2 agents are now active.
- Decision: create CON-01 / FSSAI-01 / RULE-02 / RAG-02 tables. Leave CON-02 / AUTH-01 as SQL comments in `WAVE23_STUBS.md`.
- Why: Dead Wave 3 tables are still merge risk; live Wave 2 owners need persistence.
- Reversible? Dropping unused tables is easy; adding them later is the documented stub.

## 2026-09-16 — JSONB embeddings instead of vector type
- Context: CI/compose uses `postgres:16-alpine` without pgvector.
- Decision: `embedding_json JSONB` + best-effort `CREATE EXTENSION vector`.
- Why: Don't break TEST-BASELINE hosts for an optional RAG-02 path.
- Reversible? Yes — migrate to `vector` when the image includes pgvector.
