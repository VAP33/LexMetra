from datetime import date
from regulatory.models import KnowledgeChunk,RegulatoryContext
from rag import GroundedRAGService,HybridRetriever
def _chunk(chunk_id,*,module="LMPC",jurisdiction="IN",effective_from=date(2020,1,1),effective_to=None):
    return KnowledgeChunk(id=chunk_id,module=module,department="DCA",regulation="LMPC",document_id=f"doc-{chunk_id}",document_version="v1",rule_version="v1",rule_id="R6",effective_from=effective_from,effective_to=effective_to,index_version="idx-1",page=1,language="en",jurisdiction=jurisdiction,text="Every package shall bear the required declaration.",source_reference=f"doc-{chunk_id}:page:1:chunk:0")
def test_regulatory_models_are_canonical_models():
    import models,regulatory.models as regulatory_models
    assert regulatory_models.KnowledgeChunk is models.KnowledgeChunk
    assert regulatory_models.RegulatoryContext is models.RegulatoryContext
def test_rag_public_api_imports():
    assert GroundedRAGService is not None; assert HybridRetriever is not None
def test_retriever_enforces_scope_and_effective_date():
    chunks=[_chunk("eligible"),_chunk("future",effective_from=date(2030,1,1)),_chunk("expired",effective_to=date(2022,1,1)),_chunk("wrong-module",module="FSSAI"),_chunk("wrong-jurisdiction",jurisdiction="US")]
    context=RegulatoryContext(inspection_date=date(2025,1,1),regulatory_modules=["LMPC"],jurisdiction="IN")
    assert [h.chunk.id for h in HybridRetriever(chunks).retrieve("required declaration Rule 6",context)]==["eligible"]
def test_no_eligible_source_returns_no_hits():
    context=RegulatoryContext(inspection_date=date(2025,1,1),regulatory_modules=["LMPC"],jurisdiction="IN")
    assert HybridRetriever([_chunk("future",effective_from=date(2030,1,1))]).retrieve("required declaration",context)==[]
