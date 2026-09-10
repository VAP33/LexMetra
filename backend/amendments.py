"""Approval-gated amendment lifecycle.

AI/OCR may produce a draft. Only an authorized human approval transition can
move it toward activation. Historical versions remain immutable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List

from .models import AmendmentChange, AmendmentDraft, ApprovalState, RuleVersion


_ALLOWED_TRANSITIONS = {
    ApprovalState.DRAFT: {ApprovalState.EXTRACTED, ApprovalState.REJECTED},
    ApprovalState.EXTRACTED: {ApprovalState.AI_PARSED, ApprovalState.PENDING_REVIEW, ApprovalState.REJECTED},
    ApprovalState.AI_PARSED: {ApprovalState.PENDING_REVIEW, ApprovalState.REJECTED},
    ApprovalState.PENDING_REVIEW: {ApprovalState.APPROVED, ApprovalState.REJECTED},
    ApprovalState.APPROVED: {ApprovalState.SCHEDULED, ApprovalState.ACTIVE, ApprovalState.REJECTED},
    ApprovalState.SCHEDULED: {ApprovalState.ACTIVE, ApprovalState.REJECTED},
    ApprovalState.ACTIVE: {ApprovalState.SUPERSEDED},
    ApprovalState.SUPERSEDED: set(),
    ApprovalState.REJECTED: set(),
}


@dataclass(frozen=True)
class AmendmentImpact:
    affected_rules: tuple[str, ...]
    affected_fields: tuple[str, ...]
    affected_thresholds: tuple[str, ...]
    affected_modules: tuple[str, ...]
    affected_rag_chunks: tuple[str, ...]


def transition_amendment(draft: AmendmentDraft, target: ApprovalState) -> AmendmentDraft:
    if target not in _ALLOWED_TRANSITIONS[draft.approval_state]:
        raise ValueError(
            f"Illegal amendment transition {draft.approval_state.value} -> {target.value}."
        )
    if target in {ApprovalState.APPROVED, ApprovalState.SCHEDULED, ApprovalState.ACTIVE}:
        if draft.approval_state not in {ApprovalState.PENDING_REVIEW, ApprovalState.APPROVED, ApprovalState.SCHEDULED}:
            raise ValueError("Legal activation requires a human-review state first.")
    return draft.model_copy(update={"approval_state": target})


def calculate_impact(
    changes: Iterable[AmendmentChange],
    module: str,
    *,
    rag_chunks: Iterable = (),
) -> AmendmentImpact:
    changes = list(changes)
    rules = sorted({c.rule_id for c in changes})
    fields = sorted({field for c in changes for field in c.changed_fields})
    thresholds = sorted({k for c in changes for item in c.threshold_changes for k in item.keys()})
    rag_chunks = list(rag_chunks)
    affected_rag_chunks = sorted({
        chunk.id
        for change in changes
        for chunk in rag_chunks
        if chunk.module == module
        and chunk.rule_id == change.rule_id
        and (
            change.effective_from is None
            or (
                chunk.effective_from <= change.effective_from
                and (
                    chunk.effective_to is None
                    or change.effective_from < chunk.effective_to
                )
            )
        )
    })
    return AmendmentImpact(
        affected_rules=tuple(rules),
        affected_fields=tuple(fields),
        affected_thresholds=tuple(thresholds),
        affected_modules=(module,),
        affected_rag_chunks=tuple(affected_rag_chunks),
    )
