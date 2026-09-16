"""
lexmetra_rules — Module 1: Regulation PDF -> Structured Rules.

Standalone regulation-ingestion pipeline for LexMetra. This package is
deliberately independent of the existing LexMetra ``backend/`` package: it
does not import from it and does not modify it. Compatibility is achieved
through the adapters in ``lexmetra_rules.adapters``, which translate this
module's output into dict shapes that match the existing LexMetra
``rules/rules.json`` schema and the ``backend/models.py`` regulatory models,
without requiring the existing project as a runtime dependency.

Scope reminder (see README.md for the full rationale):
  - This module extracts structured rules from a regulation document.
  - It does NOT evaluate applicability against a product (Module 3).
  - It does NOT evaluate compliance against product evidence (Module 4).
  - It does NOT use an LLM to make legal/classification decisions.
  - It does NOT implement RAG, embeddings, or a vector database.
"""

__version__ = "0.1.0"
