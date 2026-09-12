# LexMetra Build 01

This bundle is designed to be applied to the **current GitHub `main` source tree**.
It deliberately does **not** contain a replacement `backend/main.py`, `orientation.py`, or `vlm_verifier.py`, because the current GitHub versions are newer than the older local snapshot available for offline execution. Replacing those files wholesale would risk regressing working functionality.

## Included

- `backend/regulatory/`
  - common regulatory models
  - module contract and registry
  - LMPC adapter
  - future FSSAI/CDSCO/cosmetics/medical-device interfaces
  - approval-gated amendment lifecycle
  - historical rule-version selection
- `backend/rag/`
  - PDF ingestion
  - evidence-safe legal chunking
  - hybrid BM25 + TF-IDF retrieval
  - strict effective-date/module/jurisdiction filtering
  - grounded extractive RAG responses and citations
  - bootstrap corpus from `rules/rules.json`, explicitly labelled as an implementation dataset
  - PostgreSQL knowledge-store adapter
- `backend/db/schema.sql` addon via `backend/tools/regulatory_schema_addon.sql`
- `backend/regulatory/router.py` API routes for modules, RAG retrieval/query, and reviewer-gated PDF ingestion
- `backend/tools/apply_current_build01.py`
  - marker-driven patcher for the current GitHub `backend/main.py`
  - wires `/regulatory/*` routes
  - inserts actual image-based VLM recovery into `/scan`
  - removes dead/unsafe calibration inference from the current `/scan` path
  - adds RAG document dependencies
  - adds regulatory DB tables
- regression tests for RAG, amendment lifecycle, version selection, and visual recovery

## Safety properties

1. RAG retrieves knowledge but never determines PASS/FAIL.
2. Future rules are filtered out for historical inspections.
3. Draft/rejected amendments cannot become active through ingestion.
4. Regulatory PDF ingestion does not activate law.
5. OCR/VLM conflicts remain explicit and require review.
6. Ordinary photographs do not receive fabricated physical scale.
7. Existing PDF/report/audit code is not replaced by this build.

## Validation

On the offline compatibility worktree used during development:

- 354 backend regression tests passed
- 2 tests skipped
- Python compilation passed

Those numbers are **not claimed as a fresh test run against the current GitHub tree**. The bundle intentionally avoids replacing newer current-GitHub files.
