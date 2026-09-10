"""Approval-gated publication helpers for regulatory RAG chunks."""
from __future__ import annotations

from typing import Iterable, List

from regulatory.models import ApprovalState, AmendmentDraft, KnowledgeChunk


class RAGPublicationError(ValueError):
    """Raised when regulatory knowledge is not safe to publish."""


def publishable_chunks(draft: AmendmentDraft, chunks: Iterable[KnowledgeChunk]) -> List[KnowledgeChunk]:
    """Return chunks that may enter the searchable knowledge base.

    Publication is blocked until the amendment has reached APPROVED, SCHEDULED,
    or ACTIVE. Draft/extracted/AI-parsed/review states remain non-searchable.
    """
    if draft.approval_state not in {
        ApprovalState.APPROVED,
        ApprovalState.SCHEDULED,
        ApprovalState.ACTIVE,
    }:
        raise RAGPublicationError(
            f"Amendment {draft.id} is not approved for RAG publication: "
            f"{draft.approval_state.value}."
        )
    rows = list(chunks)
    for chunk in rows:
        if chunk.module != draft.module:
            raise RAGPublicationError(
                f"Chunk {chunk.id} belongs to module {chunk.module!r}, "
                f"not amendment module {draft.module!r}."
            )
        if chunk.document_id != draft.source_document_id:
            raise RAGPublicationError(
                f"Chunk {chunk.id} references document {chunk.document_id!r}, "
                f"not amendment source {draft.source_document_id!r}."
            )
    return rows
