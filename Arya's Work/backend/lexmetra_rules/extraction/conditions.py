"""
Condition extraction.

Extracts sentences that express a condition under which a provision
applies, WITHOUT evaluating that condition against any product. This
module only records what the regulation says; whether a given product
satisfies the condition is Module 3's job (out of scope here).
"""

from __future__ import annotations

import re
from typing import List, Optional

from ..models import ExtractionCondition
from ._sentences import split_sentences

_CONDITION_MARKERS = (
    "if ", "where ", "in case of", "in the case of", "provided that",
    "unless", "subject to", "when ", "for the purposes of",
    "in respect of", "applicable to",
)

# condition_type best-guess keyword -> tag. Order matters: first match wins.
_CONDITION_TYPE_KEYWORDS = (
    (("imported", "import", "country of origin"), "import_status"),
    (("net quantity", "weight", "volume", "gram", "kilogram", "millilitre", "litre", "ml", " g ", " kg "), "package_size"),
    (("wholesale", "retail", "institutional", "industrial", "export"), "sale_type"),
    (("food", "cosmetic", "drug", "commodity"), "commodity_type"),
)


def _guess_condition_type(sentence: str) -> Optional[str]:
    lowered = sentence.lower()
    for keywords, tag in _CONDITION_TYPE_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            return tag
    return None


def extract_conditions(rule_text: str) -> List[ExtractionCondition]:
    results: List[ExtractionCondition] = []
    for sentence in split_sentences(rule_text):
        lowered = sentence.lower()
        if any(marker in lowered for marker in _CONDITION_MARKERS):
            results.append(
                ExtractionCondition(
                    condition_text=sentence,
                    condition_type=_guess_condition_type(sentence),
                    source_text=sentence,
                )
            )
    return results
