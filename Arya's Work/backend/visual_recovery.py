"""Evidence-safe visual recovery merge for the /scan pipeline."""
from __future__ import annotations
from typing import Any,Dict,Iterable
RECOVERABLE_FIELDS={"common_name","net_quantity","mrp","mfg_date","expiry_date","manufacturer_name","packer_name","importer_name","consumer_care","country_of_origin"}
def merge_visual_candidates(classified:Dict[str,dict],candidates:Iterable[Dict[str,Any]])->Dict[str,dict]:
    out=dict(classified)
    for candidate in candidates:
        field,value=candidate.get("field"),candidate.get("value")
        if field not in RECOVERABLE_FIELDS or not value: continue
        existing=out.get(field)
        if existing and existing.get("value"):
            if str(existing["value"]).strip().lower()!=str(value).strip().lower():
                alternatives=list(existing.get("alternative_values") or [])
                if str(value) not in alternatives: alternatives.append(str(value))
                existing["alternative_values"]=alternatives
                existing["agreement"]="CONFLICTING"
                existing["agreement_note"]="OCR and visual VLM recovery disagree; human review required."
                existing["status"]="REVIEW_REQUIRED"; existing["review_required"]=True
            continue
        out[field]={**candidate,"source":"vlm_visual_recovery","confidence":min(.92,max(0.,float(candidate.get("confidence",0.) or 0.)))}
    return out
