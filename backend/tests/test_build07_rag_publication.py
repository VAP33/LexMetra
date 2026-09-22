from datetime import date, datetime

import pytest

from backend.models import ApprovalState, AmendmentDraft, KnowledgeChunk
from backend.rag.publication import RAGPublicationError, publishable_chunks


def draft(state=ApprovalState.DRAFT):
    return AmendmentDraft(
        id="amd-1",
        module="lmpc",
        source_document_id="gazette-2026-01",
        approval_state=state,
        extracted_at=datetime(2026, 9, 10),
    )


def chunk(**overrides):
    data = dict(
        id="chunk-1",
        module="lmpc",
        department="DCA",
        regulation="LMPC Rules",
        document_id="gazette-2026-01",
        document_version="v2",
        rule_version="v2",
        rule_id="R6",
        effective_from=date(2026, 1, 1),
        index_version="idx-1",
        text="Declarations shall be made in the prescribed form.",
        source_reference="gazette-2026-01:p1:c1",
    )
    data.update(overrides)
    return KnowledgeChunk(**data)


def test_unapproved_amendment_cannot_publish_to_rag():
    with pytest.raises(RAGPublicationError, match="not approved"):
        publishable_chunks(draft(ApprovalState.PENDING_REVIEW), [chunk()])


def test_approved_amendment_can_publish_matching_chunks():
    result = publishable_chunks(draft(ApprovalState.APPROVED), [chunk()])
    assert [item.id for item in result] == ["chunk-1"]


def test_wrong_module_is_rejected():
    with pytest.raises(RAGPublicationError, match="belongs to module"):
        publishable_chunks(draft(ApprovalState.ACTIVE), [chunk(module="fssai")])


def test_wrong_source_document_is_rejected():
    with pytest.raises(RAGPublicationError, match="references document"):
        publishable_chunks(draft(ApprovalState.SCHEDULED), [chunk(document_id="other.pdf")])
