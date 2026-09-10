from datetime import date, datetime

import pytest

from backend.rag.amendment_pipeline import (
    activate_due_rule_versions,
    build_publication_plan,
    schedule_approved_amendment,
)
from backend.rag.publication import RAGPublicationError
from backend.rag.store import InMemoryKnowledgeStore
from backend.regulatory.models import AmendmentChange, AmendmentDraft, ApprovalState, KnowledgeChunk, RuleVersion


def version(rule_id, vid, start, end=None, state=ApprovalState.SCHEDULED):
    return RuleVersion(
        id=vid,
        module="lmpc",
        regulation="LMPC Rules",
        rule_id=rule_id,
        version=vid,
        effective_from=start,
        effective_to=end,
        approval_state=state,
        source_document_id="doc1",
        text=f"{rule_id} text {vid}",
    )


def draft(state=ApprovalState.APPROVED, versions=None, changes=None):
    return AmendmentDraft(
        id="a1",
        module="lmpc",
        source_document_id="doc1",
        approval_state=state,
        extracted_at=datetime(2026, 9, 10),
        changes=changes or [AmendmentChange(rule_id="R6", change_type="MODIFIED", effective_from=date(2026, 10, 1))],
        proposed_rule_versions=versions or [version("R6", "2026.2", date(2026, 10, 1))],
    )


def chunk(cid, rule_id="R6", text="Rule 6"):
    return KnowledgeChunk(
        id=cid,
        module="lmpc",
        department="DCA",
        regulation="LMPC Rules",
        document_id="doc1",
        document_version="2026.2",
        rule_version="2026.2",
        rule_id=rule_id,
        effective_from=date(2026, 10, 1),
        index_version="idx-2026.2",
        page=1,
        text=text,
        source_reference=f"doc1:{cid}",
    )


def test_publication_plan_requires_approved_lifecycle_state():
    with pytest.raises(RAGPublicationError, match="cannot produce a publication plan"):
        build_publication_plan(draft(ApprovalState.PENDING_REVIEW))


def test_publication_plan_is_deterministic_and_side_effect_free():
    before = draft()
    plan = build_publication_plan(before, rag_chunks=[chunk("c1")])
    assert plan.amendment_id == "a1"
    assert plan.affected_rules == ("R6",)
    assert plan.rule_versions[0].effective_from == date(2026, 10, 1)
    assert before.approval_state is ApprovalState.APPROVED


def test_rule_version_set_must_match_amendment_changes():
    bad = draft(
        changes=[AmendmentChange(rule_id="R6", change_type="MODIFIED")],
        versions=[version("R7", "2026.2", date(2026, 10, 1))],
    )
    with pytest.raises(RAGPublicationError, match="does not match amendment changes"):
        build_publication_plan(bad)


def test_overlapping_proposed_rule_versions_are_rejected():
    bad = draft(
        changes=[AmendmentChange(rule_id="R6", change_type="MODIFIED", effective_from=date(2026, 10, 1))],
        versions=[
            version("R6", "2026.2", date(2026, 10, 1), date(2027, 1, 1)),
            version("R6", "2026.3", date(2026, 12, 1)),
        ],
    )
    with pytest.raises(RAGPublicationError, match="Overlapping rule-version intervals"):
        build_publication_plan(bad)


def test_existing_rule_version_overlap_is_rejected():
    existing = version("R6", "2026.1", date(2026, 1, 1), None, ApprovalState.ACTIVE)
    with pytest.raises(RAGPublicationError, match="Overlapping rule-version intervals"):
        build_publication_plan(draft(), existing_rule_versions=[existing])


def test_schedule_requires_human_approved_state_and_schedules_versions():
    pending = draft(ApprovalState.PENDING_REVIEW)
    with pytest.raises(RAGPublicationError, match="Only APPROVED"):
        schedule_approved_amendment(pending)
    scheduled = schedule_approved_amendment(draft())
    assert scheduled.approval_state is ApprovalState.SCHEDULED
    assert scheduled.proposed_rule_versions[0].approval_state is ApprovalState.SCHEDULED


def test_due_activation_is_date_mechanics_not_future_learning():
    rows = [
        version("R6", "2026.1", date(2026, 1, 1), date(2026, 10, 1), ApprovalState.ACTIVE),
        version("R6", "2026.2", date(2026, 10, 1), None, ApprovalState.SCHEDULED),
    ]
    activated = activate_due_rule_versions(rows, as_of=date(2026, 10, 1))
    states = {v.id: v.approval_state for v in activated}
    assert states["2026.1"] is ApprovalState.SUPERSEDED
    assert states["2026.2"] is ApprovalState.ACTIVE


def test_future_scheduled_version_remains_scheduled():
    rows = [version("R6", "2026.2", date(2026, 10, 1), None, ApprovalState.SCHEDULED)]
    result = activate_due_rule_versions(rows, as_of=date(2026, 9, 30))
    assert result[0].approval_state is ApprovalState.SCHEDULED


def test_inmemory_store_never_rewrites_existing_legal_chunk():
    store = InMemoryKnowledgeStore()
    store.upsert_chunks([chunk("same", text="original")])
    with pytest.raises(RAGPublicationError, match="immutable"):
        store.upsert_chunks([chunk("same", text="changed")])
    store.upsert_chunks([chunk("same", text="original")])
    assert store.get("same").text == "original"
