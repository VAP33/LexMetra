"""FastAPI routes for regulatory knowledge and grounded retrieval.

Retrieval can explain rules, but it cannot change inspection status.
"""
from __future__ import annotations
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional
from fastapi import APIRouter,Depends,File,Form,HTTPException,UploadFile
import auth
from db import persistence as db
from api_models import RAGQueryRequest
from lmpc import LMPCModule
from registry import RegulatoryModuleRegistry
from rag.default_corpus import build_default_chunks
from rag.ingest import ingest_pdf
from rag.query import GroundedRAGService
from rag.retriever import HybridRetriever
from rag.store import InMemoryKnowledgeStore,PostgresKnowledgeStore
from regulatory.models import RegulatoryContext

router=APIRouter(prefix="/regulatory",tags=["regulatory"])

def _registry():
    return RegulatoryModuleRegistry([LMPCModule()])

_store=InMemoryKnowledgeStore()
_store.upsert_chunks(build_default_chunks())
_service=GroundedRAGService(HybridRetriever(_store.list_chunks()))

@router.get("/modules")
def list_modules(current_user:auth.CurrentUser=Depends(auth.require_inspector)):
    return {"modules":_registry().metadata()}

@router.post("/rag/retrieve")
def retrieve(req:RAGQueryRequest,current_user:auth.CurrentUser=Depends(auth.require_inspector)):
    context=RegulatoryContext(inspection_date=req.inspection_date,department=req.department,
        regulatory_modules=[req.module],jurisdiction=req.jurisdiction,
        product_category=req.product_category,commodity_type=req.commodity_type)
    hits=_service.retrieve(req.query,context,top_k=req.top_k)
    return {"query":req.query,"effective_date":req.inspection_date,"module":req.module,
            "hits":[{"chunk_id":h.chunk.id,"rule_id":h.chunk.rule_id,"score":h.score,
                     "retrieval_method":h.method,"page":h.chunk.page,
                     "source_reference":h.chunk.source_reference,
                     "effective_from":h.chunk.effective_from,"effective_to":h.chunk.effective_to,
                     "text":h.chunk.text} for h in hits]}

@router.post("/rag/query")
def query(req:RAGQueryRequest,current_user:auth.CurrentUser=Depends(auth.require_inspector)):
    context=RegulatoryContext(inspection_date=req.inspection_date,department=req.department,
        regulatory_modules=[req.module],jurisdiction=req.jurisdiction,
        product_category=req.product_category,commodity_type=req.commodity_type)
    return _service.answer(req.query,context,top_k=req.top_k).model_dump(mode="json")

@router.post("/knowledge/ingest")
async def ingest_knowledge(file:UploadFile=File(...),module:str=Form("lmpc"),
    document_id:str=Form(...),document_version:str=Form(...),effective_from:date=Form(...),
    source_url:Optional[str]=Form(None),
    current_user:auth.CurrentUser=Depends(auth.require_reviewer)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400,detail="Only PDF regulatory source documents are accepted.")
    payload=await file.read()
    if not payload: raise HTTPException(status_code=400,detail="The uploaded regulatory document is empty.")
    with tempfile.NamedTemporaryFile(suffix=".pdf",delete=False) as tmp:
        tmp.write(payload); tmp_path=Path(tmp.name)
    try:
        chunks=ingest_pdf(tmp_path,module=module,
            department="Department of Consumer Affairs" if module=="lmpc" else "Unspecified",
            regulation="Regulatory source document",document_id=document_id,
            document_version=document_version,effective_from=effective_from,
            index_version=f"{document_id}:{document_version}",source_url=source_url)
    finally: tmp_path.unlink(missing_ok=True)
    if not chunks: raise HTTPException(status_code=422,detail="No extractable text was found in the PDF.")
    PostgresKnowledgeStore(db.get_conn).upsert_chunks(chunks)
    db.record_audit_event(action="regulatory_document_ingested",actor_username=current_user.username,
        resource_type="regulatory_document",resource_id=document_id,
        detail=f"module={module}, version={document_version}, chunks={len(chunks)}")
    return {"status":"INGESTED_PENDING_ACTIVATION","document_id":document_id,
            "document_version":document_version,"chunks":len(chunks),
            "activation":"human approval required"}
