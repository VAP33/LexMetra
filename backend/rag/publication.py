"""Approval-gated publication and immutable regulatory RAG helpers."""
from __future__ import annotations

from datetime import date
from typing import Iterable, List, Optional

try:
    from ..regulatory.models import ApprovalState, AmendmentDraft, KnowledgeChunk
except ImportError:
    from regulatory.models import ApprovalState, AmendmentDraft, KnowledgeChunk


class RAGPublicationError(ValueError):
    """Raised when regulatory knowledge is unsafe to publish."""


_PUBLISHABLE_STATES = {
    ApprovalState.APPROVED,
    ApprovalState.SCHEDULED,
    ApprovalState.ACTIVE,
}

_IMMUTABLE_CHUNK_FIELDS = (
    "module", "department", "regulation", "document_id", "document_version",
    "rule_version", "rule_id", "effective_from", "effective_to", "index_version",
    "page", "section", "clause", "language", "commodity", "jurisdiction", "text",
    "source_url", "source_reference", "metadata",
)


def publishable_chunks(draft: AmendmentDraft, chunks: Iterable[KnowledgeChunk]) -> List[KnowledgeChunk]:
    """Validate chunks for an approved/scheduled amendment without mutating them."""
    if draft.approval_state not in _PUBLISHABLE_STATES:
        raise RAGPublicationError(
            f"Amendment {draft.id} is not approved for RAG publication: {draft.approval_state.value}."
        )
    rows = list(chunks)
    for chunk in rows:
        validate_chunk_interval(chunk)
        if chunk.module != draft.module:
            raise RAGPublicationError(
                f"Chunk {chunk.id} belongs to module {chunk.module!r}, not amendment module {draft.module!r}."
            )
        if chunk.document_id != draft.source_document_id:
            raise RAGPublicationError(
                f"Chunk {chunk.id} references document {chunk.document_id!r}, not amendment source {draft.source_document_id!r}."
            )
    return rows


def validate_chunk_interval(chunk: KnowledgeChunk) -> None:
    if chunk.effective_to is not None and chunk.effective_to <= chunk.effective_from:
        raise RAGPublicationError(
            f"Chunk {chunk.id} has invalid effective interval {chunk.effective_from}..{chunk.effective_to}."
        )


def validate_immutable_version(existing: Optional[KnowledgeChunk], incoming: KnowledgeChunk) -> None:
    """Reject any rewrite of an existing chunk identity; identical replay is safe."""
    validate_chunk_interval(incoming)
    if existing is None:
        return
    changed = [
        field for field in _IMMUTABLE_CHUNK_FIELDS
        if getattr(existing, field) != getattr(incoming, field)
    ]
    if changed:
        raise RAGPublicationError(
            f"Knowledge chunk {incoming.id} is immutable; changed fields: {', '.join(changed)}."
        )


def validate_unique_chunk_batch(chunks: Iterable[KnowledgeChunk]) -> None:
    """Reject duplicate IDs carrying different content in one publication batch."""
    seen: dict[str, KnowledgeChunk] = {}
    for chunk in chunks:
        previous = seen.get(chunk.id)
        if previous is not None:
            validate_immutable_version(previous, chunk)
        else:
            seen[chunk.id] = chunk


def validate_non_overlapping_chunks(chunks: Iterable[KnowledgeChunk]) -> None:
    """Legacy Build 08 interval check retained for explicit version-like chunk sets."""
    grouped: dict[tuple[str, Optional[str]], list[KnowledgeChunk]] = {}
    for chunk in chunks:
        validate_chunk_interval(chunk)
        grouped.setdefault((chunk.module, chunk.rule_id), []).append(chunk)
    for key, rows in grouped.items():
        rows.sort(key=lambda c: (c.effective_from, c.effective_to or date.max, c.id))
        for previous, current in zip(rows, rows[1:]):
            if previous.effective_to is None or current.effective_from < previous.effective_to:
                raise RAGPublicationError(
                    f"Overlapping knowledge intervals for {key[0]}/{key[1]}: {previous.id} and {current.id}."
                )
