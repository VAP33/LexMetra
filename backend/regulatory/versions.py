from __future__ import annotations
from datetime import date
from typing import Iterable,List
from .models import ApprovalState,RuleVersion

class RuleVersionSelectionError(ValueError): pass
_APPLICABLE_STATES={ApprovalState.ACTIVE}

def select_rule_version(versions:Iterable[RuleVersion],*,module:str,rule_id:str,inspection_date:date)->RuleVersion:
    candidates=[v for v in versions if v.module==module and v.rule_id==rule_id and v.approval_state in _APPLICABLE_STATES and v.effective_from<=inspection_date and (v.effective_to is None or inspection_date<v.effective_to)]
    if not candidates: raise RuleVersionSelectionError(f"No applicable rule version for {module}/{rule_id} on {inspection_date}.")
    candidates.sort(key=lambda x:(x.effective_from,x.version,x.id),reverse=True)
    latest=candidates[0].effective_from
    same=[x for x in candidates if x.effective_from==latest]
    if len(same)>1: raise RuleVersionSelectionError(f"Multiple rule versions start on {latest} for {module}/{rule_id}; deterministic selection is unsafe.")
    return candidates[0]

def validate_rule_version_intervals(versions:Iterable[RuleVersion])->List[str]:
    errors=[]; groups={}
    for v in versions: groups.setdefault((v.module,v.rule_id),[]).append(v)
    for (module,rule_id),items in groups.items():
        ordered=sorted(items,key=lambda x:(x.effective_from,x.version,x.id))
        for previous,current in zip(ordered,ordered[1:]):
            if previous.effective_to is None or current.effective_from<previous.effective_to:
                errors.append(f"Overlapping rule-version intervals for {module}/{rule_id}: {previous.id} and {current.id}.")
    return errors
