"""
Clause-level segmentation.

A ``RuleSpan`` from ``segmentation.py`` is one whole rule's text. That is
too coarse a unit for semantic extraction: a single rule routinely mixes
several sub-rules, a proviso, and an explanation, each of which needs its
OWN semantic role, its OWN condition/requirement/threshold binding, and
its OWN source location. Treating the whole rule as one undifferentiated
block is exactly what let an unrelated number from one clause attach
itself to a requirement in a different clause of the same rule (the
"Rule 2 / 4 litre" problem).

This module purely does STRUCTURAL segmentation (numbering/marker-based).
It assigns no semantic meaning — that is `semantic_roles.py`'s job, run
afterwards on each ``ClauseSpan`` this module produces.

Structure recognized (in the order provisions typically nest):

    <rule body / chapeau text, before any numbering>
    (1) <sub-rule text>
        (a) <sub-clause text>
        (b) <sub-clause text>
    (2) <sub-rule text>
    Provided that <proviso text>
    Provided further that <proviso text>
    Explanation.\u2014<explanation text>

Tables are detected heuristically (a run of lines that are mostly numeric)
and kept as their own clause type rather than being merged into
surrounding prose or silently mined for thresholds — a table row is very
often NOT the same thing as an operative numeric requirement (this is one
of the concrete threshold false-binding risks named in the brief).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .models import ClauseType
from .segmentation import RuleSpan

# (n) sub-rule marker — must be the very first thing on the line (supports Western and Devanagari digits).
_SUBRULE_RE = re.compile(r"^\((?P<marker>\d{1,3}|[०-९]{1,3})\)\s*(?P<rest>.*)$")
# (i), (ii), (iii) roman numeral sub-subclause marker.
_ROMAN_RE = re.compile(r"^\((?P<marker>i{1,3}|iv|v|vi{1,3}|ix|x|xi{1,3}|xiv|xv)\)\s*(?P<rest>.*)$", re.IGNORECASE)
# (a) sub-clause marker (single/short lowercase-letter label or Devanagari letter).
_SUBCLAUSE_RE = re.compile(r"^\((?P<marker>[a-z]{1,3}|[क-ह])\)\s*(?P<rest>.*)$")
_PROVISO_RE = re.compile(r"^(Provided(?:\s+(?:that|further|also))?\b.*)$", re.IGNORECASE)
_EXPLANATION_RE = re.compile(r"^(Explanation|Note|Illustration)\s*[\.:\u2014-]\s*(?P<rest>.*)$", re.IGNORECASE)

_DEVANAGARI_DIGITS = {
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}

_HINDI_LETTER_MAP = {
    "क": "a", "ख": "b", "ग": "c", "घ": "d", "ङ": "e",
    "च": "f", "छ": "g", "ज": "h", "झ": "i", "ञ": "j",
    "ट": "k", "ठ": "l", "ड": "m", "ढ": "n", "ण": "o",
    "त": "p", "थ": "q", "द": "r", "ध": "s", "न": "t",
    "प": "u", "फ": "v", "ब": "w", "भ": "x", "म": "y", "य": "z",
}


#: A line is treated as (part of) a table if this fraction or more of its
#: non-space characters are digits/punctuation typical of tabular data.
_TABLE_DIGIT_RATIO = 0.5
#: Consecutive table-like lines required before we call it a table block
#: (a single stray digit-heavy line is more likely OCR noise/a citation).
_TABLE_MIN_LINES = 2


@dataclass
class ClauseSpan:
    clause_id: str
    parent_clause_id: Optional[str]
    clause_type: ClauseType
    text: str
    page_start: int
    page_end: int


def _looks_tabular(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    digit_punct = sum(ch.isdigit() or ch in ".,-%" for ch in stripped)
    non_space = sum(not ch.isspace() for ch in stripped)
    if non_space == 0:
        return False
    return (digit_punct / non_space) >= _TABLE_DIGIT_RATIO and len(stripped) < 60


def segment_clauses(span: RuleSpan) -> List[ClauseSpan]:
    """
    Break one rule's text into structural clauses.

    The first line (the heading line itself, e.g. "6. Declarations on
    every package.\u2014") is treated as the start of the BODY clause; the
    heading's leading "NUMBER. " is left in place here (callers that want
    it stripped, e.g. for title-guessing, already do that elsewhere) since
    this module's job is structural boundaries, not text cleanup.
    """
    lines: List[Tuple[int, str]] = span.lines or [
        (span.page_start, l) for l in span.text.splitlines()
    ]
    if not lines:
        return []

    ordered: List[Tuple[int, ClauseSpan]] = []

    current_type = ClauseType.BODY
    current_marker: Optional[str] = None
    current_parent: Optional[str] = None
    current_lines: List[Tuple[int, str]] = []
    current_start_index = 0
    subrule_counter = 0
    proviso_counter = 0
    explanation_counter = 0
    table_counter = 0
    last_subrule_id: Optional[str] = None
    last_subrule_marker: Optional[str] = None
    last_subclause_id: Optional[str] = None
    last_subclause_marker: Optional[str] = None

    def clause_id_for(ctype: ClauseType, marker: Optional[str]) -> str:
        rule_no = span.raw_number
        if ctype == ClauseType.BODY:
            return rule_no
        if ctype == ClauseType.SUBRULE:
            return f"{rule_no}({marker})"
        if ctype == ClauseType.SUBCLAUSE:
            if last_subrule_marker:
                return f"{rule_no}({last_subrule_marker})({marker})"
            return f"{rule_no}({marker})"
        if ctype == ClauseType.SUBSUBCLAUSE:
            if last_subclause_marker:
                if last_subrule_marker:
                    return f"{rule_no}({last_subrule_marker})({last_subclause_marker})({marker})"
                return f"{rule_no}({last_subclause_marker})({marker})"
            if last_subrule_marker:
                return f"{rule_no}({last_subrule_marker})({marker})"
            return f"{rule_no}({marker})"
        if ctype == ClauseType.PROVISO:
            return f"{rule_no}.proviso{marker}"
        if ctype == ClauseType.EXPLANATION:
            return f"{rule_no}.explanation{marker}"
        if ctype == ClauseType.TABLE:
            return f"{rule_no}.table{marker}"
        return f"{rule_no}.{marker}"

    def flush():
        nonlocal current_lines
        if not current_lines:
            return
        text = "\n".join(l for (_, l) in current_lines).strip("\n")
        if not text.strip():
            current_lines = []
            return
        page_start = current_lines[0][0]
        page_end = current_lines[-1][0]
        ordered.append((
            current_start_index,
            ClauseSpan(
                clause_id=clause_id_for(current_type, current_marker),
                parent_clause_id=current_parent,
                clause_type=current_type,
                text=text,
                page_start=page_start,
                page_end=page_end,
            ),
        ))
        current_lines = []

    table_run: List[Tuple[int, str]] = []
    table_start_index = 0

    def flush_table_run():
        nonlocal table_run, table_counter, current_lines
        if len(table_run) >= _TABLE_MIN_LINES:
            table_counter += 1
            text = "\n".join(l for (_, l) in table_run).strip("\n")
            ordered.append((
                table_start_index,
                ClauseSpan(
                    clause_id=clause_id_for(ClauseType.TABLE, str(table_counter)),
                    parent_clause_id=last_subrule_id,
                    clause_type=ClauseType.TABLE,
                    text=text,
                    page_start=table_run[0][0],
                    page_end=table_run[-1][0],
                ),
            ))
        else:
            # Not enough consecutive digit-heavy lines to call it a real
            # table — fold them back into the current clause as ordinary
            # text rather than discarding them.
            current_lines.extend(table_run)
        table_run = []

    i = 0
    n = len(lines)
    while i < n:
        page_no, raw_line = lines[i]
        stripped = raw_line.strip()

        if _looks_tabular(stripped):
            if not table_run:
                table_start_index = i
            table_run.append((page_no, raw_line))
            i += 1
            continue
        elif table_run:
            flush_table_run()

        subrule_match = _SUBRULE_RE.match(stripped)
        roman_match = _ROMAN_RE.match(stripped) if not subrule_match else None
        subclause_match = _SUBCLAUSE_RE.match(stripped) if not (subrule_match or roman_match) else None
        proviso_match = _PROVISO_RE.match(stripped)
        explanation_match = _EXPLANATION_RE.match(stripped)

        if subrule_match:
            flush()
            subrule_counter += 1
            current_type = ClauseType.SUBRULE
            raw_marker = subrule_match.group("marker")
            current_marker = "".join(_DEVANAGARI_DIGITS.get(ch, ch) for ch in raw_marker)
            current_parent = span.raw_number
            current_start_index = i
            last_subrule_marker = current_marker
            last_subrule_id = clause_id_for(ClauseType.SUBRULE, current_marker)
            last_subclause_id = None
            last_subclause_marker = None
            current_lines = [(page_no, raw_line)]
        elif roman_match and (last_subclause_id or last_subrule_id or current_type in (ClauseType.SUBCLAUSE, ClauseType.SUBSUBCLAUSE)):
            flush()
            current_type = ClauseType.SUBSUBCLAUSE
            current_marker = roman_match.group("marker").lower()
            current_parent = last_subclause_id or last_subrule_id or span.raw_number
            current_start_index = i
            current_lines = [(page_no, raw_line)]
        elif subclause_match:
            flush()
            current_type = ClauseType.SUBCLAUSE
            raw_marker = subclause_match.group("marker")
            current_marker = _HINDI_LETTER_MAP.get(raw_marker, raw_marker.lower())
            current_parent = last_subrule_id or span.raw_number
            current_start_index = i
            last_subclause_marker = current_marker
            last_subclause_id = clause_id_for(ClauseType.SUBCLAUSE, current_marker)
            current_lines = [(page_no, raw_line)]
        elif proviso_match:
            flush()
            proviso_counter += 1
            current_type = ClauseType.PROVISO
            current_marker = str(proviso_counter)
            current_parent = last_subclause_id or last_subrule_id or span.raw_number
            current_start_index = i
            current_lines = [(page_no, raw_line)]
        elif explanation_match:
            flush()
            explanation_counter += 1
            current_type = ClauseType.EXPLANATION
            current_marker = str(explanation_counter)
            current_parent = last_subclause_id or last_subrule_id or span.raw_number
            current_start_index = i
            current_lines = [(page_no, raw_line)]
        else:
            current_lines.append((page_no, raw_line))

        i += 1


    if table_run:
        flush_table_run()
    flush()

    ordered.sort(key=lambda pair: pair[0])
    return [clause for _, clause in ordered]
