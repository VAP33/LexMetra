from __future__ import annotations

from datetime import date
from typing import Iterable, List

from .models import ApprovalState, RuleVersion


class RuleVersionSelectionError(ValueError):
    """Raised when no unique approved/scheduled/active rule version applies."""


_APPLICABLE_STATES = {
    ApprovalState.SCHEDULED,
    ApprovalState.ACTIVE,
}


def select_rule_version(
    versions: Iterable[RuleVersion],
    *,
    module: str,
    rule_id: str,
    inspection_date: date,
) -> RuleVersion:
    candidates = [
        version
        for version in versions
        if version.module == module
        and version.rule_id == rule_id
        and version.approval_state in _APPLICABLE_STATES
        and version.effective_from <= inspection_date
        and (
            version.effective_to is None
            or inspection_date < version.effective_to
        )
    ]

    if not candidates:
        raise RuleVersionSelectionError(
            f"No applicable rule version for {module}/{rule_id} on {inspection_date}."
        )

    candidates.sort(
        key=lambda item: (item.effective_from, item.version, item.id),
        reverse=True,
    )

    latest_start = candidates[0].effective_from
    same_start = [
        item for item in candidates
        if item.effective_from == latest_start
    ]
    if len(same_start) > 1:
        raise RuleVersionSelectionError(
            f"Multiple rule versions start on {latest_start} for "
            f"{module}/{rule_id}; deterministic selection is unsafe."
        )

    return candidates[0]


def validate_rule_version_intervals(
    versions: Iterable[RuleVersion],
) -> List[str]:
    errors: List[str] = []
    groups = {}

    for version in versions:
        key = (version.module, version.rule_id)
        groups.setdefault(key, []).append(version)

    for (module, rule_id), items in groups.items():
        ordered = sorted(
            items,
            key=lambda item: (item.effective_from, item.version, item.id),
        )
        for previous, current in zip(ordered, ordered[1:]):
            if (
                previous.effective_to is None
                or current.effective_from < previous.effective_to
            ):
                errors.append(
                    f"Overlapping rule-version intervals for "
                    f"{module}/{rule_id}: {previous.id} and {current.id}."
                )

    return errors
