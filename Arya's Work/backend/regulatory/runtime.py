"""Runtime selection of authoritative regulatory rule versions."""
from __future__ import annotations
from copy import deepcopy
from datetime import date, datetime
from typing import Dict, Iterable, Mapping, Optional, Tuple
from .models import ApprovalState, RuleVersion
from .versions import RuleVersionSelectionError, select_rule_version, validate_rule_version_intervals

DEFAULT_MODULE="lmpc"

def coerce_inspection_date(value: date | datetime | str) -> date:
    if isinstance(value,datetime): return value.date()
    if isinstance(value,date): return value
    if isinstance(value,str):
        try: return date.fromisoformat(value[:10])
        except ValueError as exc: raise ValueError(f"inspection_date must be an ISO date (YYYY-MM-DD); got {value!r}") from exc
    raise TypeError("inspection_date must be a date, datetime, or ISO date string")

def apply_rule_versions(rules: Mapping[str,dict], rule_versions: Iterable[RuleVersion], *, module: str=DEFAULT_MODULE, inspection_date: date|datetime|str) -> Tuple[Dict[str,dict],Dict[str,RuleVersion]]:
    target_date=coerce_inspection_date(inspection_date)
    versions=[v for v in rule_versions if v.module==module and v.approval_state is ApprovalState.ACTIVE]
    errors=validate_rule_version_intervals(versions)
    if errors: raise RuleVersionSelectionError("; ".join(errors))
    resolved={}; selected_versions={}
    for rule_id,rule in rules.items():
        selected=select_rule_version(versions,module=module,rule_id=rule_id,inspection_date=target_date)
        runtime_rule=deepcopy(rule)
        runtime_rule["version"]=selected.version
        runtime_rule["effective_from"]=selected.effective_from.isoformat()
        runtime_rule["effective_to"]=selected.effective_to.isoformat() if selected.effective_to else None
        runtime_rule["rule_version_id"]=selected.id
        runtime_rule["source_document_id"]=selected.source_document_id
        runtime_rule["source_url"]=selected.source_url
        resolved[rule_id]=runtime_rule; selected_versions[rule_id]=selected
    return resolved,selected_versions

def version_label(selected: Mapping[str,RuleVersion])->Optional[str]:
    versions=sorted({item.version for item in selected.values()})
    if not versions: return None
    return versions[0] if len(versions)==1 else "MULTIPLE:"+",".join(versions)

__all__=["DEFAULT_MODULE","RuleVersionSelectionError","apply_rule_versions","coerce_inspection_date","version_label"]
