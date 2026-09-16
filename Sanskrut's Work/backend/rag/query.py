"""Grounded RAG query service."""
from __future__ import annotations

from regulatory.models import RAGGroundingStatus, RAGResponse, RegulatoryContext
from .retriever import HybridRetriever

def classify_query(query: str) -> str:
    q = query.casefold()
    if any(x in q for x in ("amendment", "changed", "change", "revision")):
        return "AMENDMENT_LOOKUP"
    if "threshold" in q or "how many" in q or "how much" in q:
        return "THRESHOLD_LOOKUP"
    if "why" in q or "applicable" in q or "exempt" in q:
        return "APPLICABILITY_LOOKUP"
    if "compare" in q or "difference" in q:
        return "REGULATORY_COMPARISON"
    return "LEGAL_EXPLANATION"

class GroundedRAGService:
    def __init__(self, retriever: HybridRetriever) -> None:
        self.retriever = retriever

    def retrieve(self, query: str, context: RegulatoryContext, top_k: int = 8):
        return self.retriever.retrieve(query, context, top_k=top_k)

    def answer(self, query: str, context: RegulatoryContext, top_k: int = 6) -> RAGResponse:
        query_type = classify_query(query)
        hits = self.retrieve(query, context, top_k=top_k)
        if not hits:
            return RAGResponse(
                answer="The approved regulatory knowledge base does not contain enough information to answer this question.",
                query_type=query_type,
                effective_date=context.inspection_date,
                grounding_status=RAGGroundingStatus.NOT_FOUND,
                warning="No grounded source matched the regulatory context and effective date. Do not use model memory as a legal substitute.",
            )
        lines = []
        for hit in hits[:top_k]:
            label = hit.chunk.source_reference or hit.chunk.document_id
            lines.append(f"[{label}] {hit.chunk.text.strip()}")
        rule_ids = sorted({h.chunk.rule_id for h in hits if h.chunk.rule_id})
        citations = sorted({h.chunk.source_reference for h in hits if h.chunk.source_reference})
        confidence = max(0.0, min(1.0, hits[0].score))
        return RAGResponse(
            answer="\n\n".join(lines),
            query_type=query_type,
            sources=self.retriever.to_sources(hits),
            rule_ids=rule_ids,
            module=(context.regulatory_modules[0] if context.regulatory_modules else None),
            effective_date=context.inspection_date,
            retrieval_hits=len(hits),
            confidence=confidence,
            grounding_status=RAGGroundingStatus.GROUNDED,
            citation=citations,
            warning="Retrieved knowledge explains the law; it does not determine the inspection verdict.",
        )
