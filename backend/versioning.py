"""Deterministic, approval-aware legal version selection."""
from __future__ import annotations
from datetime import date
from typing import Iterable,Optional
from .models import ApprovalState,RuleVersion
ACTIVE_STATES={ApprovalState.ACTIVE}
def select_rule_version(versions:Iterable[RuleVersion],inspection_date:date,*,require_approved:bool=True)->Optional[RuleVersion]:
    candidates=[]
    for version in versions:
        if require_approved and version.approval_state not in ACTIVE_STATES: continue
        if version.effective_from>inspection_date: continue
        if version.effective_to is not None and inspection_date>=version.effective_to: continue
        candidates.append(version)
    if not candidates:return None
    candidates.sort(key=lambda x:(x.effective_from,x.version,x.id),reverse=True)
    return candidates[0]
def assert_historical_reproducibility(version:RuleVersion,inspection_date:date)->None:
    if select_rule_version([version],inspection_date) is None:
        raise ValueError(f"Rule version {version.id} is not valid for inspection date {inspection_date.isoformat()}.")
