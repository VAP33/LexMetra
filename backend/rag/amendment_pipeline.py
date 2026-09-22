"""Approval-gated amendment lifecycle for the regulatory knowledge plane.

AI/OCR may propose an amendment. A human reviewer must approve it. After that
approval, deterministic machinery may schedule the already-approved legal
version, publish its RAG material, and activate it on its effective date.
Nothing in this module interprets legal text or grants legal approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Tuple

try:
    from ..amendments import transition_amendment, calculate_impact
    from ..regulatory.models import AmendmentDraft, ApprovalState, KnowledgeChunk, RuleVersion
except ImportError:  # backend/ on PYTHONPATH
    from amendments import transition_amendment, calculate_impact
    from regulatory.models import AmendmentDraft, ApprovalState, KnowledgeChunk, RuleVersion

from .publication import (
    RAGPublicationError,
    publishable_chunks,
    validate_chunk_interval,
)
try:
    from ..regulatory.versions import validate_rule_version_intervals
except ImportError:
    from regulatory.versions import validate_rule_version_intervals


@dataclass(frozen=True)
class AmendmentPublicationPlan:
    amendment_id: str
    module: str
    rule_versions: Tuple[RuleVersion, ...]
    affected_rules: Tuple[str, ...]
    affected_rag_chunks: Tuple[str, ...]
    effective_from: Tuple[date, ...]
    requires_reindex: bool = True


def _validate_proposed_versions(
    draft: AmendmentDraft,
    *,
    existing_rule_versions: Iterable[RuleVersion] = (),
) -> List[RuleVersion]:
    versions = list(draft.proposed_rule_versions)
    if not versions:
        raise RAGPublicationError(f"Amendment {draft.id} has no proposed RuleVersion records.")

    changed_rules = {change.rule_id for change in draft.changes}
    proposed_rules = {version.rule_id for version in versions}
    if proposed_rules != changed_rules:
        raise RAGPublicationError(
            "Proposed RuleVersion set does not match amendment changes; "
            f"missing={sorted(changed_rules - proposed_rules)}, "
            f"extra={sorted(proposed_rules - changed_rules)}."
        )

    seen_ids = set()
    for version in versions:
        if version.id in seen_ids:
            raise RAGPublicationError(f"Duplicate RuleVersion id {version.id!r} in amendment {draft.id}.")
        seen_ids.add(version.id)
        if version.module != draft.module:
            raise RAGPublicationError(
                f"RuleVersion {version.id} belongs to module {version.module!r}, not {draft.module!r}."
            )
        if version.source_document_id != draft.source_document_id:
            raise RAGPublicationError(
                f"RuleVersion {version.id} must reference amendment source document {draft.source_document_id!r}."
            )
        validate_chunk_interval(_version_as_chunk(version))

    existing = list(existing_rule_versions)
    interval_errors = validate_rule_version_intervals([*existing, *versions])
    if interval_errors:
        raise RAGPublicationError("; ".join(interval_errors))
    if len(versions) != len(proposed_rules):
        raise RAGPublicationError("Each amended rule must have exactly one proposed RuleVersion.")

    for change in draft.changes:
        matching = next(v for v in versions if v.rule_id == change.rule_id)
        if change.effective_from is not None and matching.effective_from != change.effective_from:
            raise RAGPublicationError(
                f"RuleVersion {matching.id} effective date does not match amendment change {change.rule_id}."
            )

    return versions


def _version_as_chunk(version: RuleVersion) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=f"rule-version:{version.id}",
        module=version.module,
        department="__rule_version__",
        regulation=version.regulation,
        document_id=version.source_document_id or "",
        document_version=version.version,
        rule_version=version.version,
        rule_id=version.rule_id,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        index_version="__validation__",
        text=version.text or "",
        source_url=version.source_url,
    )


def build_publication_plan(
    draft: AmendmentDraft,
    *,
    rag_chunks: Iterable[KnowledgeChunk] = (),
    existing_rule_versions: Iterable[RuleVersion] = (),
) -> AmendmentPublicationPlan:
    """Validate an approved amendment and return a side-effect-free plan."""
    if draft.approval_state not in {
        ApprovalState.APPROVED,
        ApprovalState.SCHEDULED,
        ApprovalState.ACTIVE,
    }:
        raise RAGPublicationError(
            f"Amendment {draft.id} cannot produce a publication plan from state {draft.approval_state.value}."
        )

    versions = _validate_proposed_versions(draft, existing_rule_versions=existing_rule_versions)
    chunks = publishable_chunks(draft, rag_chunks)
    impact = calculate_impact(draft.changes, draft.module, rag_chunks=chunks)

    return AmendmentPublicationPlan(
        amendment_id=draft.id,
        module=draft.module,
        rule_versions=tuple(sorted(versions, key=lambda v: (v.rule_id, v.effective_from, v.version, v.id))),
        affected_rules=impact.affected_rules,
        affected_rag_chunks=impact.affected_rag_chunks,
        effective_from=tuple(sorted({v.effective_from for v in versions})),
    )


def schedule_approved_amendment(draft: AmendmentDraft) -> AmendmentDraft:
    """Move an approved amendment to SCHEDULED after validating its versions."""
    if draft.approval_state is not ApprovalState.APPROVED:
        raise RAGPublicationError(
            f"Only APPROVED amendments may be scheduled; got {draft.approval_state.value}."
        )
    _validate_proposed_versions(draft)
    scheduled = transition_amendment(draft, ApprovalState.SCHEDULED)
    versions = [
        v.model_copy(update={"approval_state": ApprovalState.SCHEDULED})
        for v in draft.proposed_rule_versions
    ]
    return scheduled.model_copy(update={"proposed_rule_versions": versions})


def activation_eligibility(
    versions: Iterable[RuleVersion],
    *,
    as_of: date,
) -> Tuple[RuleVersion, ...]:
    """Return versions eligible for explicit human-authorized activation.

    Effective dates may establish eligibility, but they MUST NOT mutate legal
    state automatically. This function is intentionally side-effect free.
    """
    rows = list(versions)
    validate_rule_version_intervals(rows)

    eligible = [
        v for v in rows
        if v.approval_state is ApprovalState.SCHEDULED
        and v.effective_from <= as_of
    ]
    return tuple(sorted(
        eligible,
        key=lambda v: (v.module, v.rule_id, v.effective_from, v.version, v.id),
    ))


def activate_due_rule_versions(
    versions: Iterable[RuleVersion],
    *,
    as_of: date,
) -> Tuple[RuleVersion, ...]:
    """Fail safely: automatic legal activation is prohibited."""
    raise RAGPublicationError(
        "Automatic rule activation is prohibited. Use activation_eligibility() "
        "and an explicit human-authorized activation workflow."
    )


__all__ = [
    "AmendmentPublicationPlan",
    "build_publication_plan",
    "schedule_approved_amendment",
    "activation_eligibility",
    "activate_due_rule_versions",
]
