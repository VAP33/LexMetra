"""LMPC module adapter.

The existing deterministic Python rule engine remains the compliance authority.
This module supplies the common regulatory-platform interface around it rather
than reimplementing the legal evaluators here.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
try:
    from .models import EvidenceRequirement, RegulatoryContext, RegulatoryFinding, RegulatoryModuleMetadata
    from .module import RegulatoryModule
except ImportError:
    from models import EvidenceRequirement, RegulatoryContext, RegulatoryFinding, RegulatoryModuleMetadata
    from module import RegulatoryModule

ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "rules" / "rules.json"

class LMPCModule(RegulatoryModule):
    MODULE_ID = "lmpc"
    def metadata(self) -> RegulatoryModuleMetadata:
        return RegulatoryModuleMetadata(
            id=self.MODULE_ID, name="Legal Metrology Packaged Commodities",
            department="Department of Consumer Affairs",
            regulation="Legal Metrology (Packaged Commodities) Rules, 2011",
            status="primary",
        )
    def supported_context(self) -> Dict[str, Any]:
        return {"product_category": True,"commodity_type": True,"package_type": True,
                "net_quantity": True,"unit": True,"sale_type": True,"consumer_type": True,
                "is_imported": True,"inspection_date": True}
    def applicability(self, context: RegulatoryContext) -> Dict[str, Any]:
        if context.sale_type in {"industrial","institutional"}:
            return {"status":"CONDITIONAL","reason":"Direct industrial/institutional treatment requires the exact package and sale conditions to be established.","rule_ids":["LMPC-2011-R3-SCOPE"]}
        return {"status":"APPLICABLE","reason":"LMPC is the configured primary packaged-commodity module for this inspection.","rule_ids":["LMPC-2011-R3-SCOPE"]}
    def required_evidence(self, context: RegulatoryContext) -> List[EvidenceRequirement]:
        if not RULES_PATH.exists(): return []
        data=json.loads(RULES_PATH.read_text(encoding="utf-8"))
        result=[]; seen=set()
        for rule in data.get("rules",[]):
            for item in rule.get("requirements",[]):
                rid=str(item.get("id") or f"{rule.get('rule_id')}:requirement")
                if rid in seen: continue
                seen.add(rid)
                result.append(EvidenceRequirement(id=rid,field=item.get("field"),description=str(item.get("description") or rid),condition=item.get("condition")))
        return result
    def evaluate(self, context: RegulatoryContext, evidence: Dict[str, Any]) -> List[RegulatoryFinding]:
        raise RuntimeError("LMPCModule.evaluate is intentionally delegated to the existing deterministic rule_engine. Use regulatory.lmpc_adapter.run_lmpc().")
    def explain(self, finding: RegulatoryFinding) -> Dict[str, Any]:
        return {"rule_id":finding.rule_id,"status":finding.status.value,"reason":finding.reason,"source":finding.source,"warning":"Explanation is subordinate to the deterministic finding and does not change it."}
    def sources(self) -> List[Dict[str, Any]]:
        if not RULES_PATH.exists(): return []
        data=json.loads(RULES_PATH.read_text(encoding="utf-8")); meta=data.get("_meta",{})
        return [{"authority":meta.get("authority"),"source_priority":meta.get("source_priority",[])}]
    def versions(self) -> List[Dict[str, Any]]:
        if not RULES_PATH.exists(): return []
        data=json.loads(RULES_PATH.read_text(encoding="utf-8"))
        return [{"rule_id":r.get("rule_id"),"version":r.get("version"),"effective_from":r.get("effective_from"),"effective_to":r.get("effective_to"),"verification_status":r.get("verification_status")} for r in data.get("rules",[])]
