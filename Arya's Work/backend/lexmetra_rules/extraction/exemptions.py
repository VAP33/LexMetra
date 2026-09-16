"""
Exemption / exception / proviso extraction.

Extracts sentences describing an exemption from a provision, WITHOUT
evaluating whether any particular product qualifies for it — that
evaluation belongs to Module 3, exactly as it does in the existing
LexMetra ``exemption.py`` (which evaluates against a product, but only
after the exemption's *existence* has been established as data).
"""

from __future__ import annotations

import re
from typing import List, Optional

from ..models import ExtractionExemption
from ._sentences import split_sentences

_EXEMPTION_MARKERS = (
    "exempt", "shall not apply", "nothing in this rule", "nothing contained",
    "shall not be applicable", "does not apply", "shall not extend to",
    "excluding", "except", "provided that nothing",
)

_DATE_RE = re.compile(
    r"\b(?:with effect from|w\.e\.f\.?)\s+"
    r"(?P<date>\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


def _nearby_effective_from(sentence: str) -> Optional[str]:
    match = _DATE_RE.search(sentence)
    if match:
        return match.group("date")
    return None


def extract_exemptions(rule_text: str) -> List[ExtractionExemption]:
    results: List[ExtractionExemption] = []
    for sentence in split_sentences(rule_text):
        lowered = sentence.lower()
        if any(marker in lowered for marker in _EXEMPTION_MARKERS):
            results.append(
                ExtractionExemption(
                    description=sentence,
                    condition_text=sentence,
                    effective_from=_nearby_effective_from(sentence),
                    source_text=sentence,
                )
            )
    return results
