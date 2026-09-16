"""
Deterministic validation layer, run AFTER semantic extraction.

Produces (errors, warnings) for one clause. Errors indicate the clause's
extraction should not be trusted as-is (drives review_status down hard);
warnings indicate something worth a human's attention but not necessarily
wrong. Nothing here invents a fix — validation only flags problems, it
never silently repairs data.
"""

from __future__ import annotations

import re
from datetime import date
from typing import List, Tuple

from .models import Clause, SemanticRole

_GAZETTE_RE = re.compile(r"\b(g\.?s\.?r\.?|s\.?o\.?|gazette|notification\s+no)\b", re.IGNORECASE)
_PAGE_FOOTER_RE = re.compile(r"^\s*(page\s*)?\d+\s*(of\s*\d+)?\s*$", re.IGNORECASE)
_DATE_NEAR_RE = re.compile(
    r"\b\d{1,2}(st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+\d{4}\b",
    re.IGNORECASE,
)


def validate_clause(clause: Clause) -> Tuple[List[str], List[str]]:
    """Returns (errors, warnings) for one fully-built Clause."""
    errors: List[str] = []
    warnings: List[str] = []

    # 1 & 3: every threshold/requirement must have supporting source text.
    for t in clause.thresholds:
        if not t.source_text or not t.source_text.strip():
            errors.append(f"threshold on clause {clause.clause_id} has no supporting source text")
        # 2: every threshold belongs to the correct clause (clause_id match).
        if t.clause_id != clause.clause_id:
            errors.append(
                f"threshold clause_id mismatch: threshold tagged {t.clause_id} "
                f"but attached to clause {clause.clause_id}"
            )
    if clause.requirement and not clause.requirement.requirement_text.strip():
        errors.append(f"requirement on clause {clause.clause_id} has no supporting source text")

    # 4: every exception is connected to something it modifies.
    if clause.exception and clause.exception.modifies_clause_id is None:
        warnings.append(
            f"exception/exemption on clause {clause.clause_id} could not be linked to "
            f"the requirement it modifies (no preceding operative clause found in this rule)"
        )

    # 5 & 6: effective dates must be valid dates, and dates must not be
    # mistaken for thresholds.
    if clause.effective_date:
        for field_name, value in (
            ("effective_from", clause.effective_date.effective_from),
            ("effective_to", clause.effective_date.effective_to),
        ):
            if value is not None:
                try:
                    date.fromisoformat(value)
                except ValueError:
                    errors.append(f"clause {clause.clause_id}: {field_name}='{value}' is not a valid ISO date")
    for t in clause.thresholds:
        if _DATE_NEAR_RE.search(t.source_text):
            errors.append(
                f"clause {clause.clause_id}: threshold {t.value:g} {t.unit} source text looks like "
                f"it contains a date, not a compliance threshold — possible date/threshold confusion"
            )

    # 7 & 8: Gazette/notification numbers and page numbers must not be
    # interpreted as thresholds.
    for t in clause.thresholds:
        if _GAZETTE_RE.search(t.source_text):
            errors.append(
                f"clause {clause.clause_id}: threshold {t.value:g} {t.unit} source text contains a "
                f"Gazette/notification reference — likely not a real compliance threshold"
            )
        if _PAGE_FOOTER_RE.match(t.source_text.strip()):
            errors.append(f"clause {clause.clause_id}: threshold source text looks like a page number")

    # 9: OCR garbage is not treated as reliable legal language.
    if clause.ocr_quality_flag and clause.semantic_role not in (SemanticRole.OTHER,):
        warnings.append(
            f"clause {clause.clause_id}: classified as {clause.semantic_role.value} but OCR quality "
            f"is low (score={clause.ocr_quality_score:.2f}) — semantic role should be treated as "
            f"tentative"
        )

    # 10: a definition should not carry unrelated compliance thresholds
    # (this is the structural side of the Rule 2 / 4 litre fix — enforced
    # here as a hard invariant, not just a pipeline convention).
    if clause.semantic_role == SemanticRole.DEFINITION and clause.thresholds:
        errors.append(
            f"clause {clause.clause_id}: DEFINITION clause must not carry bound compliance "
            f"thresholds, but {len(clause.thresholds)} were attached"
        )

    # 11: a clause should not inherit semantic information from an
    # unrelated clause — checked via clause_id consistency on every
    # attached sub-structure.
    if clause.condition and clause.condition.clause_id != clause.clause_id:
        errors.append(f"condition.clause_id ({clause.condition.clause_id}) does not match clause {clause.clause_id}")
    if clause.requirement and clause.requirement.clause_id != clause.clause_id:
        errors.append(f"requirement.clause_id ({clause.requirement.clause_id}) does not match clause {clause.clause_id}")
    if clause.exception and clause.exception.clause_id != clause.clause_id:
        errors.append(f"exception.clause_id ({clause.exception.clause_id}) does not match clause {clause.clause_id}")

    # 12: empty/uncertain fields remain null rather than being guessed —
    # checked as a low role_confidence combined with a populated
    # structured field, which would indicate a guess was made despite
    # uncertainty.
    if clause.role_confidence < 0.4 and (clause.requirement or clause.condition or clause.thresholds):
        warnings.append(
            f"clause {clause.clause_id}: semantic role confidence is low ({clause.role_confidence:.2f}) "
            f"but structured fields were still populated — treat with caution"
        )

    return errors, warnings
