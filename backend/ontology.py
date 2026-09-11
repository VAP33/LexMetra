"""Cross-department terminology and common regulatory concepts."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class CanonicalConcept:
    id:str
    legal_terms:tuple[str,...]
    module:str
CONCEPTS={
"RETAIL_PRICE":CanonicalConcept("RETAIL_PRICE",("MRP","Maximum Retail Price","Retail Sale Price"),"common"),
"NET_QUANTITY":CanonicalConcept("NET_QUANTITY",("Net Quantity","Net Weight","Net Volume"),"common"),
}
def canonical_concept(term:str)->CanonicalConcept|None:
    needle=term.strip().casefold()
    for concept in CONCEPTS.values():
        if any(needle==item.casefold() for item in concept.legal_terms): return concept
    return None
