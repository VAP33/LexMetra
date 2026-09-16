"""
Reviewer-correction tracking.

Per the brief: "Do not silently overwrite the original extracted
information." A correction always produces a *new* ``corrected_rule``
object; ``system_extraction`` retains exactly what the pipeline produced,
untouched, forever.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .models import ExtractedRule, ReviewRecord, ReviewStatus


def apply_reviewer_correction(
    rule: ExtractedRule,
    corrections: Dict[str, Any],
    *,
    reviewer: str,
    rule_key: str,
    corrected_at: str | None = None,
) -> ReviewRecord:
    """
    Build a ReviewRecord: the original ``rule`` is kept verbatim as
    ``system_extraction``; ``corrected_rule`` is a new object with the
    supplied field-level corrections applied on top, and its
    ``review_status`` is forced to AUTO_ACCEPTED (a human reviewed it).

    ``corrections`` must be a mapping of top-level ExtractedRule field
    names to their corrected values (e.g. {"rule_id": "26A", "title": "..."}).
    """
    if not reviewer or not reviewer.strip():
        raise ValueError("apply_reviewer_correction requires a non-empty reviewer identity")
    if not corrections:
        raise ValueError("apply_reviewer_correction requires at least one correction")

    unknown_fields = set(corrections) - set(ExtractedRule.model_fields)
    if unknown_fields:
        raise ValueError(f"Unknown ExtractedRule field(s) in corrections: {sorted(unknown_fields)}")

    updated_data = rule.model_dump()
    updated_data.update(corrections)
    updated_data["review_status"] = ReviewStatus.AUTO_ACCEPTED
    updated_data["review_reasons"] = [f"reviewer-confirmed by {reviewer}"]
    corrected_rule = ExtractedRule(**updated_data)

    timestamp = corrected_at or datetime.now(timezone.utc).isoformat()

    return ReviewRecord(
        rule_key=rule_key,
        system_extraction=rule,
        reviewer_correction=corrections,
        corrected_fields=sorted(corrections.keys()),
        corrected_rule=corrected_rule,
        corrected_by=reviewer,
        corrected_at=timestamp,
    )
