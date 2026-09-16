from datetime import date
from rag.query import GroundedRAGService
from rag.retriever import HybridRetriever
from rag.store import InMemoryKnowledgeStore
from regulatory.models import KnowledgeChunk,RegulatoryContext,RAGGroundingStatus
def chunk(cid,text,rule="R6",start="2023-01-01",module="lmpc"):
    return KnowledgeChunk(id=cid,module=module,department="Department of Consumer Affairs",regulation="LMPC",document_id="doc-1",document_version="2023",rule_version="2023",rule_id=rule,effective_from=date.fromisoformat(start),index_version="idx-1",page=1,text=text,source_reference=f"doc-1:p1:{cid}")
def context():
    return RegulatoryContext(inspection_date=date(2026,9,9),department="Department of Consumer Affairs",regulatory_modules=["lmpc"],jurisdiction="IN")
def test_rag_returns_grounded_citations():
    store=InMemoryKnowledgeStore(); store.upsert_chunks([chunk("a","Rule 6 requires the common or generic name of the commodity."),chunk("b","Rule 24 concerns wholesale package declarations.",rule="R24")])
    result=GroundedRAGService(HybridRetriever(store.list_chunks())).answer("What does Rule 6 require?",context())
    assert result.grounding_status is RAGGroundingStatus.GROUNDED; assert result.rule_ids==["R6"]; assert result.citation
def test_rag_does_not_use_future_document():
    store=InMemoryKnowledgeStore(); store.upsert_chunks([chunk("future","Future amendment text",start="2027-01-01")])
    result=GroundedRAGService(HybridRetriever(store.list_chunks())).answer("What does Rule 6 require?",context())
    assert result.grounding_status is RAGGroundingStatus.NOT_FOUND
def test_rag_does_not_cross_regulatory_module():
    store=InMemoryKnowledgeStore(); store.upsert_chunks([chunk("cdsco","A drug rule",module="cdsco")])
    result=GroundedRAGService(HybridRetriever(store.list_chunks())).answer("drug rule",context())
    assert result.grounding_status is RAGGroundingStatus.NOT_FOUND
