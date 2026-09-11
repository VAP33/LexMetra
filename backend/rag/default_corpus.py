"""Build a traceable retrieval corpus from the checked-in regulatory dataset."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from regulatory.models import KnowledgeChunk
RULES_PATH=Path(__file__).resolve().parents[2]/"rules"/"rules.json"
def build_default_chunks()->list[KnowledgeChunk]:
    if not RULES_PATH.exists(): return []
    data=json.loads(RULES_PATH.read_text(encoding="utf-8")); chunks=[]
    for rule in data.get("rules",[]):
        rid=str(rule.get("rule_id") or "")
        if not rid: continue
        start=date.fromisoformat(rule.get("effective_from") or "2011-04-01")
        parts=[str(rule.get(k) or "") for k in ("source","clause","rule_type","legal_note")]
        parts += [str(req.get("description") or req.get("id") or "") for req in rule.get("requirements",[])]
        text=" ".join(x for x in parts if x).strip()
        chunks.append(KnowledgeChunk(
            id=f"rules-json:{rid}",module="lmpc",department="Department of Consumer Affairs",
            regulation="Legal Metrology (Packaged Commodities) Rules, 2011",
            document_id="rules.json",document_version=str(rule.get("version") or "implementation-dataset"),
            rule_version=str(rule.get("version") or "implementation-dataset"),
            rule_id=rid,effective_from=start,
            effective_to=date.fromisoformat(rule["effective_to"]) if rule.get("effective_to") else None,
            index_version="rules-json-bootstrap-v1",section=str(rule.get("clause") or ""),
            language="en",jurisdiction="IN",text=text,source_reference=f"rules.json:{rid}",
            metadata={"authority":data.get("_meta",{}).get("authority"),
                      "verification_status":rule.get("verification_status"),
                      "legal_boundary":data.get("_meta",{}).get("legal_boundary"),
                      "bootstrap_corpus":True}))
    return chunks
