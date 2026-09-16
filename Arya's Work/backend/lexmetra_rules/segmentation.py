"""
Rule segmentation: turn an accepted heading candidate into the complete text
span of that rule (including its sub-rules, provisos, explanations, etc.),
ending at the next accepted heading (or end of the supplied page range).

The original wording is preserved verbatim (lines are rejoined with "\\n",
not reworded or summarized) — segmentation only decides *where the rule
starts and ends*, never what it says.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .models import HeadingCandidate, PageText, SourceLocation


@dataclass
class RuleSpan:
    raw_number: str
    heading_line_text: str
    text: str
    page_start: int
    page_end: int
    # (page_no, line_text) for every line in the span, in document order.
    # Used by clause_segmentation.py to give each sub-rule/sub-clause its
    # own accurate page_start/page_end rather than inheriting the whole
    # rule's page range.
    lines: List[tuple[int, str]] = field(default_factory=list)


def _flatten_lines_with_pages(pages: List[PageText]) -> List[tuple[int, int, str]]:
    """Return [(page_no, line_index, raw_line_text), ...] in document order."""
    out: List[tuple[int, int, str]] = []
    for page in pages:
        for idx, raw in enumerate(page.text.splitlines()):
            out.append((page.page_no, idx, raw))
    return out


def segment_rules(pages: List[PageText], candidates: List[HeadingCandidate]) -> List[RuleSpan]:
    """
    Build one RuleSpan per *accepted* heading candidate, in document order.

    A rule's text runs from its own heading line up to (but not including)
    the next accepted heading's line, or to the end of the supplied pages
    if it is the last accepted heading.
    """
    accepted = [c for c in candidates if c.accepted]
    accepted_sorted = sorted(accepted, key=lambda c: (c.page_no, c.line_index))
    if not accepted_sorted:
        return []

    flat_lines = _flatten_lines_with_pages(pages)
    # Map (page_no, line_index) -> position in flat_lines for fast slicing.
    position_of = {(p, i): pos for pos, (p, i, _) in enumerate(flat_lines)}

    spans: List[RuleSpan] = []
    for i, cand in enumerate(accepted_sorted):
        start_pos = position_of.get((cand.page_no, cand.line_index))
        if start_pos is None:
            continue

        if i + 1 < len(accepted_sorted):
            nxt = accepted_sorted[i + 1]
            end_pos = position_of.get((nxt.page_no, nxt.line_index), len(flat_lines))
        else:
            end_pos = len(flat_lines)

        span_lines = flat_lines[start_pos:end_pos]
        if not span_lines:
            continue

        text = "\n".join(line for (_, _, line) in span_lines).strip("\n")
        page_start = span_lines[0][0]
        page_end = span_lines[-1][0]

        spans.append(
            RuleSpan(
                raw_number=cand.raw_number,
                heading_line_text=cand.line_text,
                text=text,
                page_start=page_start,
                page_end=page_end,
                lines=[(p, line) for (p, _, line) in span_lines],
            )
        )

    return spans


def to_source_location(document_id: str, span: RuleSpan) -> SourceLocation:
    return SourceLocation(
        document_id=document_id,
        page_start=span.page_start,
        page_end=span.page_end,
        clause=span.raw_number,
    )
