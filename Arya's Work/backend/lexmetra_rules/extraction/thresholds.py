"""
Numeric threshold extraction.

Finds NUMBER + UNIT patterns and, where a comparison phrase sits nearby,
attaches an operator. Values and units are captured exactly as written;
this module never converts units (e.g. it will not turn "1 kg" into
"1000 g") or reinterprets a legal threshold — that is exactly the kind of
silent reinterpretation the existing LexMetra ``exemption.py`` is careful
to avoid, and this module preserves the same discipline.
"""

from __future__ import annotations

import re
from typing import List, Optional

from ..models import ExtractionThreshold

_UNIT_ALTERNATION = r"(?:g|kg|gram|grams|kilogram|kilograms|ml|millilitre|millilitres|l|litre|litres|cm|mm|cm2|sq\.?\s?cm|%|percent|rs\.?|rupees|₹)"

_THRESHOLD_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>" + _UNIT_ALTERNATION + r")\b",
    re.IGNORECASE,
)

# Legal drafting frequently spells small numbers out ("ten grams", "twenty
# millilitres") rather than using numerals. This is a deliberately small,
# exact word list (one..ninety, hundred) — no attempt is made at compound
# forms like "twenty-five" or "one hundred and fifty"; those are left
# unextracted and the rule is still emitted (with its numeral-based
# thresholds, if any) rather than the module guessing a compound value.
# See README "Known limitations".
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}
_WORD_THRESHOLD_RE = re.compile(
    r"\b(?P<word>" + "|".join(_WORD_NUMBERS.keys()) + r")\s+(?P<unit>" + _UNIT_ALTERNATION + r")\b",
    re.IGNORECASE,
)

# phrase -> operator. Checked longest-phrase-first via dict iteration order
# (Python dicts preserve insertion order), so "not exceeding" is matched
# before a hypothetical shorter overlapping phrase.
_OPERATOR_PHRASES = {
    "not exceeding": "lte",
    "does not exceed": "lte",
    "or less": "lte",
    "up to": "lte",
    "below": "lt",
    "less than": "lt",
    "in excess of": "gt",
    "more than": "gt",
    "greater than": "gt",
    "exceeding": "gt",
    "above": "gt",
    "or more": "gte",
}


def _nearby_operator(text: str, match_start: int, window: int = 40) -> Optional[str]:
    left_context = text[max(0, match_start - window):match_start].lower()
    for phrase, operator in _OPERATOR_PHRASES.items():
        if phrase in left_context:
            return operator
    return None


def _matches_to_thresholds(rule_text: str, matches, value_from_match) -> List[ExtractionThreshold]:
    results: List[ExtractionThreshold] = []
    for match in matches:
        value = value_from_match(match)
        if value is None:
            continue
        unit = match.group("unit").lower()

        snippet_start = max(0, match.start() - 60)
        snippet_end = min(len(rule_text), match.end() + 20)
        source_text = rule_text[snippet_start:snippet_end].strip()

        operator = _nearby_operator(rule_text, match.start())

        results.append(
            ExtractionThreshold(
                value=value,
                unit=unit,
                operator=operator,
                label=None,
                source_text=source_text,
            )
        )
    return results


def extract_thresholds(rule_text: str) -> List[ExtractionThreshold]:
    """
    Extract numeral thresholds ("20 g") and small spelled-out thresholds
    ("twenty grams"). Both are merged and de-duplicated by (value, unit,
    approximate position) so a phrase that happens to be matched by both
    patterns isn't double-counted.
    """
    def numeral_value(match):
        try:
            return float(match.group("num"))
        except ValueError:
            return None

    def word_value(match):
        return float(_WORD_NUMBERS.get(match.group("word").lower(), 0)) or None

    numeral_results = _matches_to_thresholds(rule_text, _THRESHOLD_RE.finditer(rule_text), numeral_value)
    word_results = _matches_to_thresholds(rule_text, _WORD_THRESHOLD_RE.finditer(rule_text), word_value)

    combined: List[ExtractionThreshold] = []
    seen = set()
    for t in numeral_results + word_results:
        key = (t.value, t.unit, t.source_text)
        if key not in seen:
            seen.add(key)
            combined.append(t)
    return combined
