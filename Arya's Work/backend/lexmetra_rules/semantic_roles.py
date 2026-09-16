"""
Semantic role classification for one clause.

Deterministic and rule-based (no LLM required — see ``llm_assist.py`` for
the optional advisory layer). This module deliberately does NOT rely on
keyword-matching alone: the same trigger word means different things in
different structural positions, so ``clause_type`` (from
``clause_segmentation.py``) is treated as a strong prior, and trigger
phrases are checked in an order that reflects legal drafting convention
(a PROVISO clause containing "shall not apply" is an EXEMPTION even
though it also contains "shall"; a definitional "means" pattern beats a
generic "includes" scope signal, etc.).
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .clause_segmentation import ClauseSpan
from .models import ClauseType, SemanticRole

# ---------------------------------------------------------------------------
# Trigger vocabulary (see brief section 2)
# ---------------------------------------------------------------------------

_DEFINITION_RE = re.compile(
    r'"[^"]{2,60}"\s+(means|includes)\b|^\s*\'[^\']{2,60}\'\s+(means|includes)\b',
    re.IGNORECASE,
)
_PROHIBITION_RE = re.compile(r"\bshall\s+not\b", re.IGNORECASE)
_OBLIGATION_RE = re.compile(r"\bshall\b", re.IGNORECASE)
_PERMISSION_RE = re.compile(r"\bmay\b", re.IGNORECASE)
_EXEMPTION_STRONG_RE = re.compile(
    r"\b(nothing contained|nothing in this (rule|sub-rule|clause|regulation)|"
    r"shall not apply|shall not extend|does not apply|exempt(ed|ion)?)\b",
    re.IGNORECASE,
)
_EXCEPTION_RE = re.compile(r"\b(except|excluding|other than)\b", re.IGNORECASE)
_CONDITION_RE = re.compile(r"\b(unless|where|if\b|subject to|provided that|in case of|in the case of)\b", re.IGNORECASE)
_EFFECTIVE_DATE_RE = re.compile(
    r"\b(come into force|comes into force|with effect from|w\.e\.f\.?|shall commence|commencement)\b",
    re.IGNORECASE,
)
_PENALTY_RE = re.compile(r"\b(penalty|punishable|fine of|imprisonment|contravention)\b", re.IGNORECASE)
_PROCEDURE_RE = re.compile(r"\b(shall apply to the .*(registrar|authority|director)|application shall be made|shall be filed|shall register)\b", re.IGNORECASE)
_SCOPE_APPLICABILITY_RE = re.compile(
    r"\b(shall apply to|applies to|these rules apply|applicable to|extends to)\b", re.IGNORECASE
)

# Comparator language (brief section 2's "not less than" / "not more than" /
# "more than" / "less than" / "within") — used by threshold extraction for
# operator inference, but also nudges CONDITION/THRESHOLD role detection.
_COMPARATOR_RE = re.compile(
    r"\b(not less than|not more than|more than|less than|within|at least|at most)\b",
    re.IGNORECASE,
)
_HAS_NUMBER_UNIT_RE = re.compile(
    r"\b\d+(\.\d+)?\s*(g|kg|gram|grams|kilogram|kilograms|ml|millilitre|millilitres|"
    r"l|litre|litres|cm|mm|cm2|%|percent|rs\.?|rupees)\b",
    re.IGNORECASE,
)


def classify_clause(clause: ClauseSpan) -> Tuple[SemanticRole, float, List[str]]:
    """
    Return (semantic_role, confidence, signals). Confidence reflects how
    unambiguous the trigger language was — a clause matching exactly one
    strong pattern is high confidence; a clause matching several
    conflicting patterns (e.g. both "shall" and "may" in different
    sentences) is scored lower and left for review rather than guessed.
    """
    text = clause.text
    signals: List[str] = []

    # --- Structural priors first: some clause_types almost always carry
    # one semantic role regardless of wording. ---
    if clause.clause_type == ClauseType.EXPLANATION:
        signals.append("clause_type=explanation")
        return SemanticRole.EXPLANATION, 0.85, signals

    if clause.clause_type == ClauseType.TABLE:
        signals.append("clause_type=table")
        # A table is data, not itself an obligation/threshold statement —
        # it becomes THRESHOLD material only if a sibling clause
        # explicitly refers to it; we do not assume that here.
        return SemanticRole.OTHER, 0.4, signals

    if clause.clause_type == ClauseType.PROVISO:
        if _EXEMPTION_STRONG_RE.search(text):
            signals.append("proviso + exemption language")
            return SemanticRole.EXEMPTION, 0.9, signals
        if _EXCEPTION_RE.search(text) or _CONDITION_RE.search(text):
            signals.append("proviso + exception/condition language")
            return SemanticRole.EXCEPTION, 0.8, signals
        signals.append("proviso (no specific exemption/exception language found)")
        return SemanticRole.CONDITION, 0.55, signals

    # --- Definitions: only from an explicit quoted-term "means"/"includes"
    # pattern — NOT from any occurrence of the word "includes" elsewhere,
    # which is a common false-positive source. ---
    if _DEFINITION_RE.search(text):
        signals.append('quoted-term "means"/"includes" pattern')
        return SemanticRole.DEFINITION, 0.9, signals

    # --- Effective date: checked early since "shall" often co-occurs
    # ("These rules shall come into force...") and would otherwise be
    # mis-classified as a plain obligation. ---
    if _EFFECTIVE_DATE_RE.search(text):
        signals.append("commencement/effective-date language")
        return SemanticRole.EFFECTIVE_DATE, 0.9, signals

    # --- Penalty ---
    if _PENALTY_RE.search(text):
        signals.append("penalty language")
        return SemanticRole.PENALTY, 0.8, signals

    # --- Strong exemption language anywhere (even outside a PROVISO
    # clause_type — e.g. Rule 3-style "Nothing contained... shall apply
    # to..." bodies are exemptions by their very content). ---
    if _EXEMPTION_STRONG_RE.search(text):
        signals.append("exemption language")
        confidence = 0.85
        return SemanticRole.EXEMPTION, confidence, signals

    # --- Scope/applicability (checked before generic obligation, since
    # "these rules shall apply to..." is applicability, not an obligation
    # on a product). ---
    if _SCOPE_APPLICABILITY_RE.search(text):
        signals.append("scope/applicability language")
        return SemanticRole.APPLICABILITY, 0.75, signals

    # --- Prohibition beats obligation ("shall not" contains "shall"). ---
    if _PROHIBITION_RE.search(text):
        signals.append('"shall not"')
        return SemanticRole.PROHIBITION, 0.85, signals

    if _OBLIGATION_RE.search(text):
        signals.append('"shall"')
        confidence = 0.85
        # Mixed obligation + conditional language: still an obligation,
        # but lower confidence since a CONDITION sub-object needs to be
        # extracted alongside it (handled by clause_extraction.py) and the
        # boundary between the two is less clean.
        if _CONDITION_RE.search(text):
            signals.append("also contains conditional language (mixed)")
            confidence = 0.7
        return SemanticRole.OBLIGATION, confidence, signals

    if _PERMISSION_RE.search(text):
        signals.append('"may"')
        return SemanticRole.PERMISSION, 0.75, signals

    if _EXCEPTION_RE.search(text):
        signals.append("exception language")
        return SemanticRole.EXCEPTION, 0.6, signals

    if _CONDITION_RE.search(text):
        signals.append("conditional language")
        return SemanticRole.CONDITION, 0.6, signals

    if clause.clause_type == ClauseType.SUBCLAUSE and _HAS_NUMBER_UNIT_RE.search(text) and len(text) < 80:
        # A short lettered sub-clause that is mostly just "25 kg" with no
        # obligation/condition verb of its own — likely a threshold-only
        # list item under a parent obligation (e.g. "(a) 25 kg (b) 25
        # litre"). Bound to its parent by clause_extraction.py.
        signals.append("short numeric-only sub-clause")
        return SemanticRole.THRESHOLD, 0.6, signals

    signals.append("no strong trigger language matched")
    return SemanticRole.OTHER, 0.3, signals


# ---------------------------------------------------------------------------
# Parent-context refinement (relationship binding at the role level)
# ---------------------------------------------------------------------------

#: Roles a child clause can independently hold even under an OBLIGATION/
#: PROHIBITION parent — these are strong enough signals of their own that
#: they should never be silently overridden by inheritance.
_STRONG_INDEPENDENT_ROLES = {
    SemanticRole.EXEMPTION,
    SemanticRole.EFFECTIVE_DATE,
    SemanticRole.PENALTY,
    SemanticRole.DEFINITION,
}
_INDEPENDENT_CONFIDENCE_FLOOR = 0.75
_INHERITABLE_PARENT_ROLES = {SemanticRole.OBLIGATION, SemanticRole.PROHIBITION}


def refine_roles_with_parent_context(
    entries: List[Tuple[ClauseSpan, SemanticRole, float, List[str]]],
) -> List[Tuple[ClauseSpan, SemanticRole, float, List[str]]]:
    """
    Numbered sub-items enumerated under an obligation ("...shall bear the
    following declarations, namely:— (1) ... (2) ... (11) ...") ARE
    requirements of that obligation even when their own local wording (or
    the absence of any local "shall") would classify them, in isolation,
    as OTHER or as a bare CONDITION. This is exactly the "do not extract
    fields independently" relationship-binding principle applied to role
    classification itself — a clause's role is partly a function of its
    parent, not just its own text.

    A child is only overridden when its own independently-detected role is
    NOT one of the strong, self-sufficient roles (exemption, effective
    date, penalty, definition) at reasonable confidence — those always win.
    """
    by_id = {clause.clause_id: (clause, role, conf, sig) for clause, role, conf, sig in entries}
    refined: List[Tuple[ClauseSpan, SemanticRole, float, List[str]]] = []

    for clause, role, confidence, signals in entries:
        if (
            clause.clause_type in (ClauseType.SUBRULE, ClauseType.SUBCLAUSE)
            and clause.parent_clause_id
            and clause.parent_clause_id in by_id
        ):
            parent_clause, parent_role, parent_confidence, _ = by_id[clause.parent_clause_id]
            already_strong = (
                role in _STRONG_INDEPENDENT_ROLES and confidence >= _INDEPENDENT_CONFIDENCE_FLOOR
            )
            if parent_role in _INHERITABLE_PARENT_ROLES and not already_strong and role != parent_role:
                new_confidence = round(min(parent_confidence, max(confidence, 0.5)), 3)
                new_signals = list(signals) + [
                    f"reclassified {role.value} -> {parent_role.value}: enumerated item under "
                    f"parent clause {clause.parent_clause_id} ({parent_role.value})"
                ]
                refined.append((clause, parent_role, new_confidence, new_signals))
                continue
        refined.append((clause, role, confidence, signals))

    return refined
