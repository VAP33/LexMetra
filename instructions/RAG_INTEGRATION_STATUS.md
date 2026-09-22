# RAG INTEGRATION STATUS: LEGAL KNOWLEDGE GROUNDING SUBSYSTEM

## 1. Subsystem Architecture

The repository's existing RAG components (`backend/rag/`) are now fully connected into the legal inspection pipeline via `backend/rag_grounding.py`:

- **Knowledge Store**: `InMemoryKnowledgeStore` loaded with authoritative statutory chunks from `rag.default_corpus.build_default_chunks()`.
- **Retriever**: `HybridRetriever` combining dense vector search and sparse keyword retrieval.
- **Grounding Service**: `GroundedRAGService` generating grounded statutory answers and citations.
- **Scope Engine**: `RegulatoryScopeEngine` partitioning legal framework boundaries (LMPC, FSSAI, CDSCO, Cosmetics).
- **HTTP Endpoints**: Mounted via `app.include_router(regulatory_router)`:
  - `GET /regulatory/modules`: Lists active and registered modules with metadata.
  - `POST /regulatory/rag/retrieve`: Fetches raw grounded chunks for a regulatory context.
  - `POST /regulatory/rag/query`: Generates grounded query answers with citations.
  - `POST /regulatory/knowledge/ingest`: Secure admin endpoint to ingest PDF gazettes into the knowledge store.

---

## 2. Grounded Provisions Retrieved at Runtime

During runtime inspection of the BRU coffee jar (food context), `ground_inspection_context()` retrieves 12 grounded statutory provisions:

1. `LMPC-2011-R6-DECLARATIONS` (Version: 2011 as amended, Effective: 2011-04-01)
   - Scope: Mandatory retail declarations (Name, Address, Net Quantity, MRP, Month/Year, Consumer Care).
   - Source: `rules.json:LMPC-2011-R6-DECLARATIONS`
2. `LMPC-2011-R6-11-UNIT-PRICE` (Version: 2011 as amended, Effective: 2023-02-01)
   - Scope: Unit sale price declaration requirements per gram/milliliter.
   - Source: `rules.json:LMPC-2011-R6-11-UNIT-PRICE`
3. `LMPC-2011-R3-SCOPE` (Version: 2011 as amended, Effective: 2011-04-01)
   - Scope: Scope and applicability to pre-packaged commodities sold in retail vs. wholesale.
   - Source: `rules.json:LMPC-2011-R3-SCOPE`
4. `LMPC-2011-R26-SMALL-PACKS` (Version: 2011 as amended, Effective: 2011-04-01)
   - Scope: Exemption for packages containing 10g/10ml or less.
   - Source: `rules.json:LMPC-2011-R26-SMALL-PACKS`
5. `LMPC-2011-R6-10-ECOMMERCE` (Version: 2011 as amended, Effective: 2018-01-01)
   - Scope: E-commerce marketplace declaration obligations.
   - Source: `rules.json:LMPC-2011-R6-10-ECOMMERCE`
6. `LMPC-2011-R24-WHOLESALE` (Version: 2011 as amended, Effective: 2011-04-01)
   - Scope: Declarations on wholesale packages.
   - Source: `rules.json:LMPC-2011-R24-WHOLESALE`
7. `LMPC-2011-R31-ADVERTISEMENT` (Version: 2011 as amended, Effective: 2011-04-01)
   - Scope: Advertisement requirements for pre-packaged commodities.
   - Source: `rules.json:LMPC-2011-R31-ADVERTISEMENT`
8. `LMPC-2011-R8-2-RETURNABLE-BOTTLE` (Version: 2011 as amended, Effective: 2011-04-01)
   - Scope: Returnable glass bottle exemptions.
   - Source: `rules.json:LMPC-2011-R8-2-RETURNABLE-BOTTLE`
9. `LMPC-2011-R4-MULTIPACK` (Version: 2011 as amended, Effective: 2011-04-01)
   - Scope: Group packages and retail bundles.
   - Source: `rules.json:LMPC-2011-R4-MULTIPACK`
10. `LMPC-2011-R25-EXPORT` (Version: 2011 as amended, Effective: 2011-04-01)
    - Scope: Export packages declaration exemptions.
    - Source: `rules.json:LMPC-2011-R25-EXPORT`
11. `LMPC-2011-R26-B-FAST-FOOD` (Version: 2011 as amended, Effective: 2011-04-01)
    - Scope: Fast food restaurant parcel exemption.
    - Source: `rules.json:LMPC-2011-R26-B-FAST-FOOD`
12. `LMPC-2011-R5-STANDARD-PACK` (Version: 2011 as amended, Effective: 2011-04-01)
    - Scope: Standard package size requirements under Second Schedule.
    - Source: `rules.json:LMPC-2011-R5-STANDARD-PACK`

---

## 3. Strict Decision Boundary & Effective Date Invariants

- **Zero LLM Verdicts**: The RAG subsystem does not determine `PASS` or `FAIL`. It constructs a `RuleVersion` registry and passes it to `run_inspection(..., rule_versions=...)`.
- **Effective Date Safety**: The RAG retriever filters provisions based on `inspection_date`:
  - Amendments with `effective_from > inspection_date` are rejected.
  - Expired provisions with `effective_to < inspection_date` are rejected.
  - Historical inspections evaluate against historical law, preventing legal anachronisms.
- **Failure-Safe Resilience**: If RAG is unreachable or retrieval fails, a fallback knowledge record is generated with status `REVIEW_REQUIRED`, and the deterministic Rule Engine evaluates default statutory rules without crashing.
