"""
Requirement (obligation) extraction.

Extracts sentences that state an obligation ("shall...", "is required
to...") and, only when a confident match exists, suggests a canonical
declaration field name mirroring the existing LexMetra
``schema.CANONICAL_FIELD_ALIASES`` vocabulary (mirrored here as a small,
static, local table so this package has no runtime import on the existing
``backend`` package — see README "Compatibility" for why it is a mirror,
not an import).

``suggested_field`` is exactly that: a suggestion. It is never asserted as
the final ``requirements[].field`` value the existing rule engine expects;
integration/review confirms it.
"""

from __future__ import annotations

from typing import List, Optional

from ..models import ExtractionRequirement
from ._sentences import split_sentences

_REQUIREMENT_MARKERS = (
    "shall ", "shall be", "shall contain", "shall bear", "shall declare",
    "must ", "is required", "required to", "shall not be sold",
    "shall be declared", "shall specify",
)

# Mirrors backend/schema.py:CANONICAL_FIELD_ALIASES (subset, deliberately
# not imported — see module docstring).
_CANONICAL_FIELD_TERMS = {
    "mrp": "mrp",
    "maximum retail price": "mrp",
    "retail sale price": "mrp",
    "net quantity": "net_quantity",
    "net weight": "net_quantity",
    "net volume": "net_quantity",
    "manufacturer": "manufacturer_name_address",
    "packer": "manufacturer_name_address",
    "importer": "manufacturer_name_address",
    "marketed by": "manufacturer_name_address",
    "common name": "common_name",
    "generic name": "common_name",
    "date of manufacture": "mfg_date",
    "date of packing": "mfg_date",
    "best before": "best_before_use_by",
    "use by": "best_before_use_by",
    "consumer care": "consumer_care",
    "customer care": "consumer_care",
    "unit sale price": "unit_sale_price",
    "standard pack size": "standard_pack_size",
    "country of origin": "country_of_origin",
}


def _guess_field(sentence: str) -> Optional[str]:
    lowered = sentence.lower()
    for term, field in _CANONICAL_FIELD_TERMS.items():
        if term in lowered:
            return field
    return None


def extract_requirements(rule_text: str, rule_number: str) -> List[ExtractionRequirement]:
    results: List[ExtractionRequirement] = []
    idx = 0
    for sentence in split_sentences(rule_text):
        lowered = sentence.lower()
        if any(marker in lowered for marker in _REQUIREMENT_MARKERS):
            idx += 1
            results.append(
                ExtractionRequirement(
                    id=f"{rule_number}.req{idx}",
                    description=sentence,
                    suggested_field=_guess_field(sentence),
                    source_text=sentence,
                )
            )
    return results
