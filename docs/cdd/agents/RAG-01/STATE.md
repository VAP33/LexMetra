# STATE — RAG-01
Last updated: 2026-09-16

## Current phase
partial — provenance + unsourced marking; verbatim gazette not ingested

## What exists right now (verified by me, not assumed)
- `backend/rag/legal_sources.py`: intended India Code / eGazette / Consumer Affairs URLs per rule family.
- `backend/rag/default_corpus.py`: each bootstrap chunk from `rules.json` gets `sourced=False`, `placeholder=True`, `source_kind=rules.json_implementation_encoding`.
- Publication/immutability pipeline **not** rewritten (`ingest.py` / `publication.py` unchanged in intent).
- Tests: `backend/tests/test_rag_wave2.py`.

## What is NOT done yet
- Verbatim Legal Metrology Act 2009 + LMPC Rules 2011 gazette body in chunks.
- Human Legal Lead flipping `needs_official_verification`.

## Blocked on
- Authoritative text download/OCR that we will not fabricate. Package explicitly prefers marked placeholders over fake law.

## Next action
Ingest official HTML/PDF, chunk by legal section, publish new immutable versions. Leave bootstrap chunks as historical unsourced versions.
