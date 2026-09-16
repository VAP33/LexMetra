"""Parallel FSSAI evaluator.

Produces RuleFinding rows with the four FactStatus members. Absence of a
mark on the provided images is UNCERTAIN, never FAIL. Does not write into
rules.json or rule_engine.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from schema import FactStatus, ProductInspection, RuleFinding

RULES_PATH = Path(__file__).resolve().parents[2] / "rules" / "rules_fssai.json"

_FOODISH = {"food", "beverage", "dairy", "bakery", "confectionery"}

_LICENCE_RE = re.compile(
    r"\b(?:fssai|lic(?:ence|ense)?(?:\s*(?:no|number|#))?)[\s:.-]*([0-9]{5,14})\b",
    re.I,
)
_VEG_RE = re.compile(r"\b(?:veg(?:etarian)?|non[\s-]?veg(?:etarian)?)\b", re.I)
_ING_RE = re.compile(r"\bingredients?\b", re.I)
_DATE_RE = re.compile(
    r"\b(?:mfg|pkd|packed|best\s*before|use\s*by|exp(?:iry)?)\b",
    re.I,
)


def load_fssai_rules(path: Path = RULES_PATH) -> List[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("rules") or [])


def _blob_from_inspection(inspection: ProductInspection) -> str:
    parts: List[str] = []
    for fact in inspection.facts:
        if fact.extracted_value:
            parts.append(str(fact.extracted_value))
        if fact.raw_text:
            parts.append(str(fact.raw_text))
    for decl in inspection.declarations:
        value = getattr(decl, "value", None)
        if value:
            parts.append(str(value))
    return " \n ".join(parts)


def _finding(
    rule: dict,
    status: FactStatus,
    reason: str,
    *,
    missing: Optional[List[str]] = None,
) -> RuleFinding:
    reqs = rule.get("requirements") or []
    req = reqs[0] if reqs else {}
    return RuleFinding(
        rule_id=str(rule["rule_id"]),
        rule_version=str(rule.get("version") or ""),
        status=status,
        requirement_id=req.get("id"),
        requirement_description=req.get("description"),
        reason=reason,
        required_evidence=list(rule.get("evidence_required") or []),
        missing_evidence=list(missing or []),
        confidence=0.4 if status is FactStatus.PASS else 0.2,
        review_required=True,
        verification_status=rule.get("verification_status")
        or "needs_official_verification",
    )


def evaluate_fssai(
    inspection: ProductInspection,
    *,
    rules: Optional[Iterable[dict]] = None,
) -> List[RuleFinding]:
    category = (inspection.product_category or "").strip().lower()
    if category not in _FOODISH:
        return []

    rules = list(rules) if rules is not None else load_fssai_rules()
    blob = _blob_from_inspection(inspection)
    findings: List[RuleFinding] = []

    detectors = {
        "FSSAI-LABEL-LICENCE": (_LICENCE_RE, "fssai_licence_number", "FSSAI licence/registration number"),
        "FSSAI-LABEL-VEG-NONVEG": (_VEG_RE, "veg_nonveg_mark", "vegetarian/non-vegetarian mark"),
        "FSSAI-LABEL-INGREDIENTS": (_ING_RE, "ingredients_list", "ingredients list"),
        "FSSAI-LABEL-DATE": (_DATE_RE, "date_marking", "date marking"),
    }

    by_id = {r.get("rule_id"): r for r in rules}
    for rule_id, (pattern, evidence_key, label) in detectors.items():
        rule = by_id.get(rule_id)
        if not rule:
            continue
        if pattern.search(blob):
            findings.append(
                _finding(
                    rule,
                    FactStatus.PASS,
                    f"Observed text consistent with a {label}. "
                    "This is an automated screen, not a verified FSSAI finding.",
                )
            )
        else:
            findings.append(
                _finding(
                    rule,
                    FactStatus.UNCERTAIN,
                    f"{label} was not detected in the provided images. "
                    "That is not a determination that the pack is non-compliant.",
                    missing=[evidence_key],
                )
            )
    return findings


def module_status(findings: List[RuleFinding]) -> str:
    """Aggregate FSSAI-only status. Never silently merge into LMPC overall_status."""
    if not findings:
        return "NOT_APPLICABLE"
    if any(f.status is FactStatus.FAIL for f in findings):
        return FactStatus.FAIL.value
    if any(f.status is FactStatus.UNCERTAIN for f in findings):
        return FactStatus.UNCERTAIN.value
    if all(f.status is FactStatus.EXEMPT for f in findings):
        return FactStatus.EXEMPT.value
    if all(f.status is FactStatus.PASS for f in findings):
        return FactStatus.PASS.value
    return FactStatus.UNCERTAIN.value
