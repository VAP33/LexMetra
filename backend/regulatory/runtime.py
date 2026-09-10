"""Runtime selection of authoritative regulatory rule versions.

This module is deliberately small: it selects the legal version to use for an
inspection date, but does not invent or rewrite the substantive rule logic.
The existing rules.json remains the implementation catalogue; RuleVersion
records decide which dated version is authoritative for a dated inspection.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from typing import Dict, Iterable, Mapping, Optional, Tuple

from .models import ApprovalState, RuleVersion
from .versions import (
    RuleVersionSelectionError,
    select_rule_version,
    validate_rule_version_intervals,
)


DEFAULT_MODULE = "lmpc"


def coerce_inspection_date(value: date | datetime | str) -> date:
    """Convert supported API/date representations to a calendar date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise ValueError(
                f"inspection_date must be an ISO date (YYYY-MM-DD); got {value!r}"
            ) from exc
    raise TypeError("inspection_date must be a date, datetime, or ISO date string")


def apply_rule_versions(
    rules: Mapping[str, dict],
    rule_versions: Iterable[RuleVersion],
    *,
    module: str = DEFAULT_MODULE,
    inspection_date: date | datetime | str,
) -> Tuple[Dict[str, dict], Dict[str, RuleVersion]]:
    """Resolve every implementation rule against the dated version registry.

    A dated inspection is never allowed to fall back to the undated rules.json
    catalogue. Every rule in the implementation catalogue must have exactly one
    applicable, scheduled/active RuleVersion. The returned rule dictionaries are
    copies, so the source catalogue is not mutated.
    """
    target_date = coerce_inspection_date(inspection_date)
    versions = list(rule_versions)
    applicable_versions = [
        item
        for item in versions
        if item.module == module
        and item.approval_state in {ApprovalState.SCHEDULED, ApprovalState.ACTIVE}
    ]
    interval_errors = validate_rule_version_intervals(applicable_versions)
    if interval_errors:
        raise RuleVersionSelectionError("; ".join(interval_errors))

    resolved: Dict[str, dict] = {}
    selected_versions: Dict[str, RuleVersion] = {}

    for rule_id, rule in rules.items():
        selected = select_rule_version(
            versions,
            module=module,
            rule_id=rule_id,
            inspection_date=target_date,
        )
        runtime_rule = deepcopy(rule)
        # The legal implementation remains in rules.json. These fields are the
        # authoritative dated identity and provenance selected by RuleVersion.
        runtime_rule["version"] = selected.version
        runtime_rule["effective_from"] = selected.effective_from.isoformat()
        runtime_rule["effective_to"] = (
            selected.effective_to.isoformat() if selected.effective_to else None
        )
        runtime_rule["rule_version_id"] = selected.id
        runtime_rule["source_document_id"] = selected.source_document_id
        runtime_rule["source_url"] = selected.source_url
        resolved[rule_id] = runtime_rule
        selected_versions[rule_id] = selected

    return resolved, selected_versions


def version_label(selected: Mapping[str, RuleVersion]) -> Optional[str]:
    """Return a deterministic inspection-level version label."""
    versions = sorted({item.version for item in selected.values()})
    if not versions:
        return None
    if len(versions) == 1:
        return versions[0]
    return "MULTIPLE:" + ",".join(versions)


__all__ = [
    "DEFAULT_MODULE",
    "RuleVersionSelectionError",
    "apply_rule_versions",
    "coerce_inspection_date",
    "version_label",
]
