"""Approval-gated publication and immutable-version helpers for regulatory RAG."""
from __future__ import annotations

from datetime import date
from typing import Iterable, List, Optional

from regulatory.models import ApprovalState, AmendmentDraft, KnowledgeChunk


class RAGPublicationError(ValueError):
    """Raised when regulatory knowledge is not safe to publish."""


_PUBLISHABLE_STATES = {
    ApprovalState.APPROVED,
    ApprovalState.SCHEDULED,
    ApprovalState.ACTIVE,
}


def publishable_chunks(draft: AmendmentDraft, chunks: Iterable[KnowledgeChunk]) -> List[KnowledgeChunk]:
    """Return chunks that may enter the searchable knowledge base."""
    if draft.approval_state not in _PUBLISHABLE_STATES:
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


def validate_chunk_interval(chunk: KnowledgeChunk) -> None:
    """Reject impossible effective-date intervals."""
    if chunk.effective_to is not None and chunk.effective_to <= chunk.effective_from:
        raise RAGPublicationError(
            f"Chunk {chunk.id} has invalid effective interval "
            f"{chunk.effective_from}..{chunk.effective_to}."
        )


def validate_immutable_version(existing: Optional[KnowledgeChunk], incoming: KnowledgeChunk) -> None:
    """Prevent an existing chunk identity from being silently rewritten.

    The same chunk id must represent the same legal text/provenance forever.
    A changed legal version must receive a new content-derived chunk id.
    """
    validate_chunk_interval(incoming)
    if existing is None:
        return
    immutable_fields = (
        "module", "department", "regulation", "document_id", "document_version",
        "rule_version", "rule_id", "effective_from", "effective_to", "index_version",
        "page", "section", "clause", "language", "commodity", "jurisdiction", "text",
        "source_url", "source_reference",
    )
    changes = [field for field in immutable_fields if getattr(existing, field) != getattr(incoming, field)]
    if changes:
        raise RAGPublicationError(
            f"Knowledge chunk {incoming.id} is immutable; changed fields: {', '.join(changes)}."
        )


def validate_non_overlapping_chunks(chunks: Iterable[KnowledgeChunk]) -> None:
    """Reject overlapping legal intervals for the same module/rule identity."""
    grouped: dict[tuple[str, Optional[str]], list[KnowledgeChunk]] = {}
    for chunk in chunks:
        validate_chunk_interval(chunk)
        grouped.setdefault((chunk.module, chunk.rule_id), []).append(chunk)
    for key, rows in grouped.items():
        rows.sort(key=lambda c: (c.effective_from, c.effective_to or date.max, c.id))
        for previous, current in zip(rows, rows[1:]):
            if previous.effective_to is None or current.effective_from < previous.effective_to:
                raise RAGPublicationError(
                    f"Overlapping knowledge intervals for {key[0]}/{key[1]}: "
                    f"{previous.id} and {current.id}."
                )
