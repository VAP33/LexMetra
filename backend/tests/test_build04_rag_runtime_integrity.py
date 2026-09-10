from datetime import date

from regulatory.models import KnowledgeChunk, RegulatoryContext
from rag import GroundedRAGService, HybridRetriever


def _chunk(chunk_id, *, module="LMPC", jurisdiction="IN",
           effective_from=date(2020, 1, 1), effective_to=None):
    return KnowledgeChunk(
        id=chunk_id,
        module=module,
        department="DCA",
        regulation="LMPC",
        document_id=f"doc-{chunk_id}",
        document_version="v1",
        rule_version="v1",
        rule_id="R6",
        effective_from=effective_from,
        effective_to=effective_to,
        index_version="idx-1",
        page=1,
        language="en",
        jurisdiction=jurisdiction,
        text="Every package shall bear the required declaration.",
        source_reference=f"doc-{chunk_id}:page:1:chunk:0",
    )


def test_regulatory_models_are_canonical_models():
    import models
    import regulatory.models as regulatory_models

    assert regulatory_models.KnowledgeChunk is models.KnowledgeChunk
    assert regulatory_models.RegulatoryContext is models.RegulatoryContext


def test_rag_public_api_imports():
    assert GroundedRAGService is not None
    assert HybridRetriever is not None


def test_retriever_enforces_scope_and_effective_date():
    chunks = [
        _chunk("eligible"),
        _chunk("future", effective_from=date(2030, 1, 1)),
        _chunk("expired", effective_to=date(2022, 1, 1)),
        _chunk("wrong-module", module="FSSAI"),
        _chunk("wrong-jurisdiction", jurisdiction="US"),
    ]
    retriever = HybridRetriever(chunks)
    context = RegulatoryContext(
        inspection_date=date(2025, 1, 1),
        regulatory_modules=["LMPC"],
        jurisdiction="IN",
    )

    hits = retriever.retrieve("required declaration Rule 6", context)

    assert [hit.chunk.id for hit in hits] == ["eligible"]


def test_no_eligible_source_returns_no_hits():
    retriever = HybridRetriever(
        [_chunk("future", effective_from=date(2030, 1, 1))]
    )
    context = RegulatoryContext(
        inspection_date=date(2025, 1, 1),
        regulatory_modules=["LMPC"],
        jurisdiction="IN",
    )

    assert retriever.retrieve("required declaration", context) == []
