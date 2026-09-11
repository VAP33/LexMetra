from datetime import date

import pytest

from regulatory.models import KnowledgeChunk, RAGGroundingStatus, RegulatoryContext
from backend.rag.query import GroundedRAGService
from backend.rag.retriever import HybridRetriever


def chunk(cid, text, *, start, end=None, rule="R6", module="LMPC", commodity="food"):
    return KnowledgeChunk(
        id=cid,
        module=module,
        department="Consumer Affairs",
        regulation="LMPC",
        document_id=f"doc-{cid}",
        document_version="v1",
        rule_version="v1",
        rule_id=rule,
        effective_from=start,
        effective_to=end,
        index_version="idx-1",
        page=1,
        language="en",
        commodity=commodity,
        jurisdiction="IN",
        text=text,
        source_reference=f"doc-{cid}:page:1:chunk:0",
    )


def context(when):
    return RegulatoryContext(
        inspection_date=when,
        regulatory_modules=["LMPC"],
        department="Consumer Affairs",
        jurisdiction="IN",
        commodity_type="food",
    )


def test_historical_date_filter_excludes_future_rule():
    chunks = [
        chunk("old", "Rule 6 requires declaration of net quantity.", start=date(2024, 1, 1), end=date(2026, 1, 1)),
        chunk("future", "Rule 6 requires declaration of revised net quantity.", start=date(2026, 1, 1)),
    ]
    hits = HybridRetriever(chunks).retrieve("Rule 6 net quantity", context(date(2025, 12, 31)))
    assert [h.chunk.id for h in hits] == ["old"]


def test_effective_to_is_exclusive_boundary():
    chunks = [
        chunk("old", "Rule 6 old requirement.", start=date(2024, 1, 1), end=date(2026, 1, 1)),
        chunk("new", "Rule 6 new requirement.", start=date(2026, 1, 1)),
    ]
    hits = HybridRetriever(chunks).retrieve("Rule 6 requirement", context(date(2026, 1, 1)))
    assert [h.chunk.id for h in hits] == ["new"]


def test_no_grounding_never_becomes_legal_answer():
    service = GroundedRAGService(HybridRetriever([]))
    response = service.answer("What does Rule 99 require?", context(date(2026, 1, 1)))
    assert response.grounding_status is RAGGroundingStatus.NOT_FOUND
    assert response.sources == []
    assert response.confidence == 0


def test_rag_response_carries_citation_and_date():
    chunks = [chunk("r1", "Rule 6 requires net quantity.", start=date(2025, 1, 1))]
    response = GroundedRAGService(HybridRetriever(chunks)).answer(
        "Rule 6 net quantity", context(date(2025, 6, 1))
    )
    assert response.grounding_status is RAGGroundingStatus.GROUNDED
    assert response.effective_date == date(2025, 6, 1)
    assert response.citation
    assert response.sources[0].rule_id == "R6"


def test_ineligible_commodity_does_not_cross_apply():
    chunks = [
        chunk("food", "Rule 6 food quantity.", start=date(2024, 1, 1), commodity="food"),
        chunk("cosmetic", "Rule 6 cosmetic quantity.", start=date(2024, 1, 1), commodity="cosmetic"),
    ]
    hits = HybridRetriever(chunks).retrieve("Rule 6 quantity", context(date(2025, 6, 1)))
    assert [h.chunk.id for h in hits] == ["food"]


def test_retriever_rejects_scheduled_publication_state():
    from datetime import date
    from rag.retriever import HybridRetriever
    from regulatory.models import KnowledgeChunk, RegulatoryContext

    base = dict(
        module="lmpc", department="Department of Consumer Affairs",
        regulation="Rules", document_id="doc", document_version="1",
        rule_version="1", rule_id="R25", effective_from=date(2020,1,1),
        effective_to=None, index_version="idx", page=1, section="25", clause="25",
        language="en", commodity=None, jurisdiction="IN", text="maximum retail price",
        source_url=None, source_reference="doc:p1",
    )
    scheduled = KnowledgeChunk(id="scheduled", metadata={"publication_state":"SCHEDULED"}, **base)
    active = KnowledgeChunk(id="active", metadata={"publication_state":"ACTIVE"}, **base)
    context = RegulatoryContext(inspection_date=date(2026,1,1), regulatory_modules=["lmpc"], department="Department of Consumer Affairs", jurisdiction="IN")
    hits = HybridRetriever([scheduled, active]).retrieve("rule R25", context)
    assert [h.chunk.id for h in hits] == ["active"]
