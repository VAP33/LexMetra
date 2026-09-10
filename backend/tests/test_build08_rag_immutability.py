from datetime import date

import pytest

from backend.rag.publication import (
    RAGPublicationError,
    validate_chunk_interval,
    validate_immutable_version,
    validate_non_overlapping_chunks,
)
from backend.regulatory.models import KnowledgeChunk


def chunk(cid, start, end=None, text="Rule 6"):
    return KnowledgeChunk(
        id=cid,
        module="lmpc",
        department="DCA",
        regulation="LMPC Rules",
        document_id="doc-1",
        document_version="2026.1",
        rule_version="2026.1",
        rule_id="R6",
        effective_from=start,
        effective_to=end,
        index_version="idx-1",
        page=1,
        text=text,
        source_reference=f"doc-1:{cid}",
    )


def test_existing_chunk_identity_is_immutable():
    existing = chunk("same", date(2026, 1, 1), text="old")
    incoming = chunk("same", date(2026, 1, 1), text="new")
    with pytest.raises(RAGPublicationError, match="immutable"):
        validate_immutable_version(existing, incoming)


def test_identical_chunk_can_be_replayed_without_mutation():
    existing = chunk("same", date(2026, 1, 1), text="old")
    validate_immutable_version(existing, chunk("same", date(2026, 1, 1), text="old"))


def test_invalid_and_overlapping_intervals_are_rejected():
    with pytest.raises(RAGPublicationError, match="invalid effective interval"):
        validate_chunk_interval(chunk("bad", date(2026, 5, 1), date(2026, 5, 1)))
    rows = [
        chunk("a", date(2026, 1, 1), date(2026, 6, 1)),
        chunk("b", date(2026, 5, 1), None),
    ]
    with pytest.raises(RAGPublicationError, match="Overlapping knowledge intervals"):
        validate_non_overlapping_chunks(rows)


def test_adjacent_intervals_are_allowed():
    rows = [
        chunk("a", date(2026, 1, 1), date(2026, 6, 1)),
        chunk("b", date(2026, 6, 1), None),
    ]
    validate_non_overlapping_chunks(rows)
