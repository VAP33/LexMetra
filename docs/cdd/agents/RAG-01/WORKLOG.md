# WORKLOG — RAG-01

## 2026-09-16 — Mark bootstrap corpus as unsourced
- What I did:
  - Catalogued intended official URLs. Tagged `rules.json` bootstrap chunks so RAG-02 cannot present them as gazette.
- What I verified:
  - `test_rag_wave2.py` in focused pytest set.
- What I did NOT verify:
  - Any downloaded gazette file (none added to the repo).
- Files touched:
  - `backend/rag/legal_sources.py`, `backend/rag/default_corpus.py`, `backend/tests/test_rag_wave2.py`
