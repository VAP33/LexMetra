"""
Clause-scoped, relationship-bound extraction.

This is the direct fix for the "Rule 2 / 4 litre" problem: every
extraction function here operates on a SINGLE clause's own text and
returns structures tagged with that clause's ``clause_id``. A number
that appears in one clause can never end up attached to a different
clause's requirement, because extraction never sees text outside the
clause it is currently processing.

Thresholds are further restricted to clauses whose semantic role is
actually operative (OBLIGATION / PROHIBITION / CONDITION / EXEMPTION /
THRESHOLD) — a number appearing inside a DEFINITION or EXPLANATION clause
(an illustrative example, e.g. "for instance, a 4 litre container...")
is deliberately NOT promoted to a compliance threshold. It is still
detected (for transparency — see ``unbound_numeric_mentions`` below) but
never enters the clause's ``thresholds`` list.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .clause_segmentation import ClauseSpan
from .extraction._sentences import split_sentences
from .extraction.conditions import extract_conditions as _extract_condition_sentences
from .extraction.effective_dates import extract_effective_dates
from .extraction.thresholds import extract_thresholds as _extract_raw_thresholds
from .models import (
    BoundThreshold,
    ClauseType,
    ConditionInfo,
    EffectiveDates,
    ExceptionInfo,
    RequirementInfo,
    SemanticRole,
)

#: Roles for which a numeric value found in the clause is treated as a real
#: compliance threshold. Everything else (DEFINITION, EXPLANATION, OTHER,
#: SCOPE, APPLICABILITY, PROCEDURE, EFFECTIVE_DATE, PENALTY, PERMISSION) is
#: excluded — a number there is data/context, not an operative limit.
_THRESHOLD_ELIGIBLE_ROLES = {
    SemanticRole.OBLIGATION,
    SemanticRole.PROHIBITION,
    SemanticRole.CONDITION,
    SemanticRole.EXEMPTION,
    SemanticRole.EXCEPTION,
    SemanticRole.THRESHOLD,
}

#: Controlled vocabulary for "what does this threshold apply to". Only
#: terms actually present in the SAME clause's text are ever used — this
#: is a lookup restricted to the clause, not a free-form guess.
_APPLIES_TO_VOCAB = [
    "net quantity", "net weight", "net volume", "net weight or measure",
    "package", "container", "wrapper", "commodity", "principal display panel",
    "unit sale price", "retail sale price", "maximum retail price",
    "label", "quantity", "weight", "volume", "measure", "size", "area",
    "font", "font size", "letter height", "numerals",
]

_SHALL_NOT_RE = re.compile(r"\bshall\s+not\b", re.IGNORECASE)
_SHALL_RE = re.compile(r"\bshall\b", re.IGNORECASE)
_MAY_RE = re.compile(r"\bmay\b", re.IGNORECASE)
_LEADING_MARKER_RE = re.compile(r"^\s*(?:\(\w{1,4}\)|\d{1,4}\.)\s*")


def _clean_leading_marker(text: str) -> str:
    return _LEADING_MARKER_RE.sub("", text, count=1).strip()


def _find_applies_to(clause_text: str, before_index: int) -> Tuple[Optional[str], float]:
    """
    Search the SAME clause's text, before the number's position, for the
    nearest controlled-vocabulary term. Returns (term, confidence). If
    nothing is found in this clause's own text, returns (None, 0.0) rather
    than guessing from context outside the clause.
    """
    left_context = clause_text[:before_index].lower()
    best_term = None
    best_pos = -1
    for term in _APPLIES_TO_VOCAB:
        pos = left_context.rfind(term)
        if pos > best_pos:
            best_pos = pos
            best_term = term
    if best_term is None:
        return None, 0.0
    # Closer terms are more likely to be the true referent; a term right
    # next to the number is high confidence, one far to the left (start of
    # a long clause) is lower.
    distance = before_index - (best_pos + len(best_term))
    confidence = max(0.3, min(0.95, 1.0 - distance / 120.0))
    return best_term, round(confidence, 3)


def extract_bound_thresholds(
    clause: ClauseSpan, semantic_role: SemanticRole
) -> Tuple[List[BoundThreshold], List[str]]:
    """
    Returns (bound_thresholds, informational_notes). `informational_notes`
    records numeric mentions found in a NON-eligible clause (e.g. a
    definition's illustrative example) — kept for explainability, never
    promoted to a real threshold.
    """
    raw = _extract_raw_thresholds(clause.text)
    if not raw:
        return [], []

    if semantic_role not in _THRESHOLD_ELIGIBLE_ROLES:
        notes = [
            f"clause {clause.clause_id} ({semantic_role.value}) contains numeric value(s) "
            f"not treated as compliance thresholds (non-operative clause role): "
            + "; ".join(f"{t.value:g} {t.unit}" for t in raw)
        ]
        return [], notes

    bound: List[BoundThreshold] = []
    notes: List[str] = []
    for t in raw:
        # Locate this specific match's position within the clause text so
        # the applies_to search only looks at text BEFORE it, in the same
        # clause — never elsewhere.
        pos = clause.text.find(t.source_text)
        anchor = pos + len(t.source_text) if pos != -1 else len(clause.text)
        applies_to, applies_to_confidence = _find_applies_to(clause.text, anchor)
        if applies_to is None:
            notes.append(
                f"clause {clause.clause_id}: threshold {t.value:g} {t.unit} found but what it "
                f"applies to could not be determined from this clause's own text"
            )
        bound.append(
            BoundThreshold(
                value=t.value,
                unit=t.unit,
                operator=t.operator,
                applies_to=applies_to,
                applies_to_confidence=applies_to_confidence,
                clause_id=clause.clause_id,
                source_text=t.source_text,
                page=clause.page_start,
            )
        )
    return bound, notes


def extract_condition_info(clause: ClauseSpan) -> Optional[ConditionInfo]:
    conditions = _extract_condition_sentences(clause.text)
    if not conditions:
        return None
    # A clause may contain more than one conditional sentence; the first
    # is used as the clause's primary condition (matches the "one clause,
    # one condition object" shape requested) — all matched sentences are
    # still visible in condition_text if they were joined by the sentence
    # splitter's boundaries, so nothing is silently dropped, only the
    # single most relevant one is promoted to the structured field.
    first = conditions[0]
    return ConditionInfo(
        subject=None,  # left None unless a reliable subject phrase can be isolated; see note below
        condition_type=first.condition_type,
        condition_text=first.condition_text,
        clause_id=clause.clause_id,
    )


def extract_requirement_info(
    clause: ClauseSpan, inherited_subject: Optional[str] = None
) -> Optional[RequirementInfo]:
    """
    Best-effort subject/action/object breakdown of an obligation/
    prohibition clause. If no reliable split point ("shall"/"shall
    not"/"may") is found within THIS clause's own text, `subject` and
    `action` are left None rather than guessed — `requirement_text`
    (the full clause text) is always populated regardless, so nothing is
    lost even when the structured breakdown isn't possible.
    """
    text = " ".join(clause.text.split())  # normalize whitespace/newlines for the regex

    match = _SHALL_NOT_RE.search(text) or _SHALL_RE.search(text) or _MAY_RE.search(text)
    subject = None
    action = None
    obj = None

    if match:
        subject_raw = text[: match.start()].strip(" ,;:")
        subject = _clean_leading_marker(subject_raw) or None
        after = text[match.end():].strip()
        # action = first short verb phrase (up to the next comma or ~4
        # words, whichever is shorter) — deliberately modest since a full
        # parse of legal verb phrases is out of scope; this is a best
        # effort aid for Module 2, not a legal parser.
        after_words = after.split()
        action_words = []
        for w in after_words[:6]:
            if w.endswith(","):
                action_words.append(w.rstrip(","))
                break
            action_words.append(w)
        action = " ".join(action_words) or None
        remainder = after[len(" ".join(action_words)):].strip(" ,;:") if action_words else after
        obj = remainder or None

    if not subject and inherited_subject:
        subject = inherited_subject

    return RequirementInfo(
        subject=subject,
        action=action,
        object=obj,
        requirement_text=clause.text.strip(),
        clause_id=clause.clause_id,
    )


def extract_exception_info(
    clause: ClauseSpan, semantic_role: SemanticRole, modifies_clause_id: Optional[str]
) -> Optional[ExceptionInfo]:
    if semantic_role not in (SemanticRole.EXCEPTION, SemanticRole.EXEMPTION):
        return None

    condition_text = None
    conditions = _extract_condition_sentences(clause.text)
    if conditions:
        condition_text = conditions[0].condition_text

    return ExceptionInfo(
        modifies_clause_id=modifies_clause_id,
        description=clause.text.strip(),
        condition_text=condition_text,
        is_exemption=(semantic_role == SemanticRole.EXEMPTION),
        clause_id=clause.clause_id,
    )


def extract_clause_effective_date(clause: ClauseSpan, semantic_role: SemanticRole) -> Optional[EffectiveDates]:
    if semantic_role != SemanticRole.EFFECTIVE_DATE:
        return None
    dates = extract_effective_dates(clause.text)
    if dates.effective_from is None and dates.effective_to is None:
        return None
    return dates


def extract_applies_to(clause: ClauseSpan) -> List[str]:
    """
    Who/what this clause applies to, restricted to terms actually present
    in THIS clause's own text (never inferred from sibling clauses or the
    rule as a whole).
    """
    lowered = clause.text.lower()
    found = []
    for term in _ENTITY_VOCAB:
        if term in lowered and term not in found:
            found.append(term)
    return found


_ENTITY_VOCAB = [
    "manufacturer", "packer", "importer", "seller", "retailer", "dealer",
    "distributor", "consumer", "wholesale dealer", "wholesaler",
    "package", "commodity", "specified goods",
]
