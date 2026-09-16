"""Safe placeholder modules for future regulatory domains."""
from __future__ import annotations
from typing import Any,Dict,List
from .models import EvidenceRequirement,RegulatoryContext,RegulatoryFinding,RegulatoryModuleMetadata
from .module import RegulatoryModule
class UnsupportedRegulatoryModule(RegulatoryModule):
    def __init__(self,module_id:str,name:str,department:str,regulation:str)->None:
        self._meta=RegulatoryModuleMetadata(id=module_id,name=name,department=department,regulation=regulation,status="interface_only")
    def metadata(self): return self._meta
    def supported_context(self)->Dict[str,Any]: return {"common_regulatory_context":True}
    def applicability(self,context:RegulatoryContext)->Dict[str,Any]: return {"status":"UNKNOWN","reason":"No approved implementation is active for this module."}
    def required_evidence(self,context:RegulatoryContext)->List[EvidenceRequirement]: return []
    def evaluate(self,context:RegulatoryContext,evidence:Dict[str,Any])->List[RegulatoryFinding]: return []
    def explain(self,finding:RegulatoryFinding)->Dict[str,Any]: return {"status":"UNKNOWN","reason":"Module interface only; no compliance verdict is generated."}
    def sources(self)->List[Dict[str,Any]]: return []
    def versions(self)->List[Dict[str,Any]]: return []
def default_future_modules()->list[RegulatoryModule]:
    return [
        UnsupportedRegulatoryModule("fssai","Food Safety","FSSAI","Food Safety and Standards framework"),
        UnsupportedRegulatoryModule("cdsco","Drugs and Medical Products","CDSCO","Drugs and Cosmetics framework"),
        UnsupportedRegulatoryModule("cosmetics","Cosmetics","CDSCO","Cosmetics regulatory framework"),
        UnsupportedRegulatoryModule("medical_devices","Medical Devices","CDSCO","Medical Devices Rules"),
    ]
