"""
Rule heading detection.

This is the module specifically responsible for NOT repeating the earlier
prototype's mistake of turning every number in the OCR text into a "rule"
(R44, R46, R48, R900, R2011 in the brief's own example).

Approach (deliberately deterministic, no LLM):

  1. Regex finds *candidate* headings: a line that starts with a small
     integer (optionally with a letter suffix, e.g. "26A") followed by a
     period and a real title/sentence.
  2. Each candidate is scored down (not just accepted/rejected by one
     regex) using surrounding-context heuristics: is it at a paragraph
     start, is the number in a plausible range, does the line look like a
     table/date/money value instead of a heading, is it a continuation of a
     wrapped sentence.
  3. The single strongest signal is *sequence continuity*: genuine rule
     numbers in a regulation increase through the document. We compute the
     longest non-decreasing subsequence (LIS-by-value) of surviving
     candidates in document order and treat membership in that subsequence
     as strong positive evidence; a candidate whose number breaks the
     running sequence (an isolated "2011" between rules 24 and 25) is
     exactly the false-positive pattern in the brief and is scored down
     accordingly, not silently kept at full confidence.

Every candidate — accepted or not — is retained in the return value
(``HeadingCandidate.accepted``) so a reviewer can see why something was or
was not treated as a rule heading. Nothing is thrown away silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .models import HeadingCandidate, PageText

# A candidate heading: line-initial "NUMBER[LETTER]." followed by real text.
# Matches "3.", "26A.", "6.", but NOT "6(11)" (that's a sub-rule, handled
# separately) and not a bare "2011" with no trailing period+space+content.
HEADING_RE = re.compile(
    r"^\s*(?P<num>\d{1,3})(?P<suffix>[A-Za-z])?\.\s+(?P<rest>\S.*)$"
)

# Sub-rule / sub-clause markers, e.g. "(11)" or "(a)". Not top-level
# headings — segmentation.py keeps these as part of the parent rule's body.
SUBCLAUSE_RE = re.compile(r"^\s*\((?P<marker>[0-9]{1,3}|[a-zA-Z])\)\s+\S")

# Lines that look like a date, a Gazette/notification reference, or a money
# amount immediately after the number — these are the concrete
# false-positive shapes named in the brief (years, page numbers, amendment
# references).
_MONTHS = (
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
)
DATE_LIKE_RE = re.compile(
    r"^\d{1,4}(st|nd|rd|th)?\s+(" + "|".join(_MONTHS) + r")\b", re.IGNORECASE
)
GAZETTE_RE = re.compile(
    r"\b(g\.\s?s\.\s?r\.?|s\.\s?o\.(?!\w)|gazette\b|notification\s+no\b)", re.IGNORECASE
)
PAGE_FOOTER_RE = re.compile(r"^\s*(page\s*)?\d+\s*(of\s*\d+)?\s*$", re.IGNORECASE)
MONEY_RE = re.compile(r"^(rs\.?|₹|inr)\s*\d", re.IGNORECASE)

DEFAULT_MAX_RULE_NUMBER = 200
DEFAULT_MIN_REST_CHARS = 4
#: Minimum score to be emitted as a rule at all (vs. kept only as a
#: rejected debug candidate). Deliberately conservative per the brief's
#: success criterion "random numbers are not incorrectly treated as rules".
ACCEPT_THRESHOLD = 0.5


@dataclass
class _Line:
    page_no: int
    line_index: int
    text: str
    stripped: str


def _flatten_lines(pages: List[PageText]) -> List[_Line]:
    lines: List[_Line] = []
    for page in pages:
        for idx, raw in enumerate(page.text.splitlines()):
            lines.append(_Line(page.page_no, idx, raw, raw.strip()))
    return lines


def _looks_like_table_or_numeric_block(lines: List[_Line], index: int, window: int = 2) -> bool:
    """True if the lines immediately around `index` are digit-dense, which
    is characteristic of a table row rather than prose."""
    start = max(0, index - window)
    end = min(len(lines), index + window + 1)
    neighborhood = "".join(l.stripped for l in lines[start:end] if l is not lines[index])
    if not neighborhood:
        return False
    digit_chars = sum(ch.isdigit() for ch in neighborhood)
    return len(neighborhood) > 0 and (digit_chars / len(neighborhood)) > 0.5


def _starts_paragraph(lines: List[_Line], index: int) -> bool:
    """Heuristic: true if this line looks like the start of a new
    paragraph/heading rather than the continuation of a wrapped sentence."""
    if index == 0:
        return True
    prev = lines[index - 1].stripped
    if not prev:
        return True
    if prev.endswith((".", ":", ";")):
        return True
    if lines[index].page_no != lines[index - 1].page_no:
        # New page: treat cautiously as a possible new paragraph, since page
        # breaks in scanned PDFs frequently coincide with rule breaks too.
        return True
    return False


def _score_candidate(
    lines: List[_Line], index: int, max_rule_number: int
) -> Tuple[float, List[str]]:
    """
    Score one regex match without yet considering sequence continuity
    (that's a document-level pass done separately in detect_headings).

    Returns (score in [0,1], reasons).
    """
    line = lines[index]
    match = HEADING_RE.match(line.stripped)
    reasons: List[str] = []

    if not match:
        return 0.0, ["does not match heading pattern"]

    num_str = match.group("num")
    rest = match.group("rest").strip()
    num = int(num_str)

    score = 0.55
    reasons.append("matches NUMBER. TEXT heading pattern")

    if num > max_rule_number:
        return 0.0, [f"number {num} exceeds plausible rule-number range (> {max_rule_number})"]

    if len(rest) < DEFAULT_MIN_REST_CHARS:
        return 0.0, ["heading text too short to be a real title"]

    if DATE_LIKE_RE.match(line.stripped) or GAZETTE_RE.search(line.stripped):
        return 0.05, ["looks like a date or Gazette/notification reference, not a rule heading"]

    if PAGE_FOOTER_RE.match(line.stripped):
        return 0.0, ["looks like a page number/footer"]

    if MONEY_RE.match(rest):
        return 0.1, ["heading text starts with a currency amount"]

    if _starts_paragraph(lines, index):
        score += 0.2
        reasons.append("starts a new paragraph")
    else:
        score -= 0.3
        reasons.append("appears mid-paragraph (likely a wrapped sentence, not a heading)")

    if _looks_like_table_or_numeric_block(lines, index):
        score -= 0.3
        reasons.append("surrounded by a digit-dense block (likely a table)")

    # A real heading's "rest" usually has a reasonable ratio of letters.
    letters = sum(ch.isalpha() for ch in rest)
    if len(rest) > 0 and (letters / len(rest)) < 0.4:
        score -= 0.25
        reasons.append("heading text has too few letters to look like prose")
    else:
        score += 0.1
        reasons.append("heading text looks like prose")

    return max(0.0, min(1.0, score)), reasons


def _longest_nondecreasing_subsequence_indices(numbers: List[int]) -> set:
    """
    Standard O(n log n) patience-sorting LIS (non-decreasing variant),
    returning the *indices* (into `numbers`) that belong to one longest
    non-decreasing subsequence. Used to find the most plausible "real rule
    numbering sequence" among surviving candidates, in document order.
    """
    if not numbers:
        return set()

    import bisect

    n = len(numbers)
    tails_idx: List[int] = []       # indices into `numbers`, tails of piles
    predecessors = [-1] * n

    for i, value in enumerate(numbers):
        # Find first tail whose value > value (strict) — for a
        # NON-DECREASING subsequence we search with bisect_right.
        lo, hi = 0, len(tails_idx)
        while lo < hi:
            mid = (lo + hi) // 2
            if numbers[tails_idx[mid]] <= value:
                lo = mid + 1
            else:
                hi = mid
        pos = lo
        if pos > 0:
            predecessors[i] = tails_idx[pos - 1]
        if pos == len(tails_idx):
            tails_idx.append(i)
        else:
            tails_idx[pos] = i

    if not tails_idx:
        return set()

    result = set()
    k = tails_idx[-1]
    while k != -1:
        result.add(k)
        k = predecessors[k]
    return result


def detect_headings(
    pages: List[PageText],
    max_rule_number: int = DEFAULT_MAX_RULE_NUMBER,
    accept_threshold: float = ACCEPT_THRESHOLD,
) -> List[HeadingCandidate]:
    """
    Detect rule-heading candidates across the given pages.

    Returns every candidate considered, each flagged ``accepted`` or not.
    """
    lines = _flatten_lines(pages)

    raw_candidates: List[Tuple[int, int, str, List[str]]] = []  # (line_idx, num, reasons_prefix, )
    scored: List[Tuple[int, float, List[str], int]] = []  # (line_idx, score, reasons, num)

    for idx, line in enumerate(lines):
        if not line.stripped:
            continue
        if not HEADING_RE.match(line.stripped):
            continue
        score, reasons = _score_candidate(lines, idx, max_rule_number)
        match = HEADING_RE.match(line.stripped)
        num = int(match.group("num"))
        scored.append((idx, score, reasons, num))

    # Sequence-continuity pass: among candidates that already pass a basic
    # sanity floor, find the longest non-decreasing numeric subsequence in
    # document order. Membership is a strong positive signal; an isolated
    # break in the sequence is exactly the false-positive shape described
    # in the brief (a lone "2011" between rules 24 and 25).
    basic_pass_idxs = [i for i, (idx, score, reasons, num) in enumerate(scored) if score > 0.15]
    sections: List[List[int]] = []
    current_section: List[int] = []
    for i in basic_pass_idxs:
        num = scored[i][3]
        if current_section and num <= scored[current_section[-1]][3] and num == 1:
            sections.append(current_section)
            current_section = [i]
        else:
            current_section.append(i)
    if current_section:
        sections.append(current_section)

    lis_line_indices: set[int] = set()
    for sec in sections:
        sec_numbers = [scored[i][3] for i in sec]
        lis_local = _longest_nondecreasing_subsequence_indices(sec_numbers)
        for loc in lis_local:
            lis_line_indices.add(sec[loc])

    candidates: List[HeadingCandidate] = []
    for i, (idx, score, reasons, num) in enumerate(scored):
        final_score = score
        final_reasons = list(reasons)
        if score > 0.0:
            if i in lis_line_indices:
                final_score = min(1.0, score + 0.2)
                final_reasons.append(
                    "part of the longest non-decreasing rule-number sequence in the document "
                    "(strong positive signal)"
                )
            else:
                final_score = max(0.0, score - 0.5)
                final_reasons.append(
                    "breaks the document's running rule-number sequence "
                    "(classic false-positive shape: an isolated number, not a real heading)"
                )

        accepted = final_score >= accept_threshold
        line = lines[idx]
        candidates.append(
            HeadingCandidate(
                raw_number=str(num),
                page_no=line.page_no,
                line_index=line.line_index,
                line_text=line.stripped,
                accepted=accepted,
                confidence=round(final_score, 3),
                reasons=final_reasons,
            )
        )

    return candidates
