"""
Effective-date extraction.

Only extracts a date when it is textually associated with an
effective/commencement/supersession/expiry keyword. A date appearing
elsewhere in the rule text (e.g. inside an example, or an unrelated
reference) is NOT treated as an effective date — this module never
invents or infers a date the text does not actually attach to the
relevant keyword.

Parsed dates are normalized to ISO 8601 (YYYY-MM-DD) only when the parse
is unambiguous; the raw matched text is always preserved alongside so nothing
is lost if normalization is wrong or impossible. Uses the existing LexMetra
versioning concept (``effective_from`` / ``effective_to``) rather than
inventing new date-field names.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

from ..models import EffectiveDates

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

_DATE_TEXT_RE = re.compile(
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>" + "|".join(_MONTHS) + r")\s+(?P<year>\d{4})"
    r"|(?P<iso>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)

_FROM_KEYWORDS = (
    "with effect from", "w.e.f.", "shall come into force on",
    "shall come into force with effect from", "commencing from",
    "shall take effect from",
)
_TO_KEYWORDS = (
    "shall cease to have effect", "superseded with effect from",
    "shall stand superseded", "shall expire on", "up to and including",
)

# How far (chars) after a keyword we search for the associated date.
_SEARCH_WINDOW = 80


def _parse_date(day: str, month: str, year: str) -> Optional[str]:
    try:
        month_num = _MONTHS[month.lower()]
        dt = datetime(int(year), month_num, int(day))
        return dt.date().isoformat()
    except (KeyError, ValueError):
        return None


def _find_date_after(text: str, keyword_pos_end: int) -> Optional[Tuple[str, str]]:
    """Search a window after a keyword for a date. Returns (raw, iso_or_None)."""
    window = text[keyword_pos_end:keyword_pos_end + _SEARCH_WINDOW]
    match = _DATE_TEXT_RE.search(window)
    if not match:
        return None
    if match.group("iso"):
        raw = match.group("iso")
        try:
            iso = datetime.fromisoformat(raw).date().isoformat()
        except ValueError:
            iso = None
        return raw, iso
    raw = match.group(0)
    iso = _parse_date(match.group("day"), match.group("month"), match.group("year"))
    return raw, iso


def extract_effective_dates(rule_text: str) -> EffectiveDates:
    lowered = rule_text.lower()

    effective_from = effective_from_raw = effective_from_src = None
    effective_to = effective_to_raw = effective_to_src = None

    for kw in _FROM_KEYWORDS:
        pos = lowered.find(kw)
        if pos != -1:
            found = _find_date_after(rule_text, pos + len(kw))
            if found:
                effective_from_raw, effective_from = found
                start = pos
                end = min(len(rule_text), pos + len(kw) + _SEARCH_WINDOW)
                effective_from_src = rule_text[start:end].strip()
                break

    for kw in _TO_KEYWORDS:
        pos = lowered.find(kw)
        if pos != -1:
            found = _find_date_after(rule_text, pos + len(kw))
            if found:
                effective_to_raw, effective_to = found
                start = pos
                end = min(len(rule_text), pos + len(kw) + _SEARCH_WINDOW)
                effective_to_src = rule_text[start:end].strip()
                break

    return EffectiveDates(
        effective_from=effective_from,
        effective_to=effective_to,
        effective_from_raw=effective_from_raw,
        effective_to_raw=effective_to_raw,
        effective_from_source_text=effective_from_src,
        effective_to_source_text=effective_to_src,
    )
