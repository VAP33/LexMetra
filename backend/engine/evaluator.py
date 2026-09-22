"""
The generic rule engine (section 4, 20, 21).

``RuleEngine.evaluate()`` is the one place that turns (rules + evidence +
context) into an explainable compliance result. It performs, per rule, in
order, and records every stage in the audit trail:

    INPUT -> RULE SELECTED -> APPLICABILITY -> EXEMPTION CHECK ->
    CONDITION EVALUATION -> VALUE NORMALIZATION -> CALCULATION ->
    COMPARISON -> EVIDENCE -> RULE RESULT -> AGGREGATION -> OVERALL RESULT

Nothing in this module knows about any specific regulation, product
category, or field name -- it only knows how to walk the generic ``Rule``
structure defined in ``rule_model.py``.
"""

from __future__ import annotations

import copy
import datetime as _dt
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .aggregate import AggregationPolicy, aggregate
from .calc import CalcTrace, run_derived
from .conditions import ConditionTrace, Tri, evaluate_condition
from .dependency import topological_order
from .errors import RuleConfigurationError
from .evidence import Evidence, EvidenceValue
from .results import (
    ApplicabilityStatus,
    ComplianceDecisionPackage,
    ComplianceStatus,
    EngineReport,
    EvidenceCitation,
    RequirementResult,
    RuleResult,
)
from .rule_model import Requirement, Rule, RuleSet
from .validate import validate_ruleset

DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.55


def _tri_to_applicability(t: Tri) -> ApplicabilityStatus:
    return {
        Tri.TRUE: ApplicabilityStatus.APPLICABLE,
        Tri.FALSE: ApplicabilityStatus.NOT_APPLICABLE,
        Tri.UNKNOWN: ApplicabilityStatus.UNCERTAIN,
    }[t]


def _tri_to_compliance(t: Tri) -> ComplianceStatus:
    return {
        Tri.TRUE: ComplianceStatus.PASS,
        Tri.FALSE: ComplianceStatus.FAIL,
        Tri.UNKNOWN: ComplianceStatus.UNCERTAIN,
    }[t]


def _matches_applies_to(rule: Rule, context: Dict[str, Any]) -> Optional[bool]:
    """
    Simple declarative scope match against ``rule.applies_to``, e.g.
    ``{"product_category": ["food", "cosmetics"], "sale_type": ["retail"]}``.
    A missing key in ``applies_to`` means "no restriction on that axis".
    A context value of "all" in the rule's list also matches everything.
    Returns None (unknown) if a required context key was not supplied at all.
    """
    if not rule.applies_to:
        return True

    for key, allowed in rule.applies_to.items():
        if not isinstance(allowed, list):
            allowed = [allowed]

        allowed_norm = [str(a).strip().lower() for a in allowed]

        if "all" in allowed_norm:
            continue

        if key not in context or context[key] is None:
            return None

        value = str(context[key]).strip().lower()

        if value not in allowed_norm:
            return False

    return True


def _collect_evidence_citations(
    trace: ConditionTrace,
    evidence: Evidence,
) -> List[EvidenceCitation]:
    citations: List[EvidenceCitation] = []

    def _walk(t: ConditionTrace) -> None:
        if t.field:
            ev = evidence.get_evidence_value(t.field)

            citations.append(
                EvidenceCitation(
                    field=t.field,
                    observed_value=t.observed,
                    normalized_value=(
                        getattr(ev, "normalized_value", None)
                        or (ev.value if ev else None)
                    )
                    if ev
                    else t.observed,
                    confidence=ev.confidence if ev else None,
                    source_text=ev.source_text if ev else None,
                    source_page=ev.source_page if ev else None,
                    provenance=ev.provenance if ev else None,
                    image_id=getattr(ev, "image_id", None) if ev else None,
                    bbox=getattr(ev, "bbox", None) if ev else None,
                    verification_status=(
                        getattr(ev, "verification_status", None)
                        if ev
                        else None
                    ),
                    usable=ev.is_usable() if ev else None,
                    quality_state=(
                        getattr(ev, "quality_state", None)
                        if ev
                        else None
                    ),
                )
            )

        for c in t.children:
            _walk(c)

    _walk(trace)

    # De-duplicate by field, keep first occurrence.
    seen = set()
    unique: List[EvidenceCitation] = []

    for c in citations:
        if c.field in seen:
            continue

        seen.add(c.field)
        unique.append(c)

    return unique


def _missing_fields(trace: ConditionTrace) -> List[str]:
    missing: List[str] = []

    def _walk(t: ConditionTrace) -> None:
        if t.result is Tri.UNKNOWN and t.field and not t.children:
            missing.append(t.field)

        for c in t.children:
            _walk(c)

    _walk(trace)

    return sorted(set(missing))


def _explain(
    rule: Rule,
    applicability: ApplicabilityStatus,
    status: ComplianceStatus,
    reason: str,
) -> str:
    template = {
        (ComplianceStatus.PASS,): rule.message_pass,
        (ComplianceStatus.FAIL,): rule.message_fail,
        (ComplianceStatus.UNCERTAIN,): rule.message_uncertain,
        (ComplianceStatus.NOT_APPLICABLE,): rule.message_not_applicable,
        (ComplianceStatus.EXEMPTED,): rule.message_exempt,
    }.get((status,))

    parts = [
        f"Rule: {rule.name or rule.rule_id} ({rule.rule_id})",
        f"Applicability: {applicability.value}",
        f"Result: {status.value}",
        f"Reason: {template or reason}",
    ]

    if rule.provision:
        parts.append(
            f"Legal reference: {rule.legal_source or ''} {rule.provision}".strip()
        )

    return "\n".join(parts)


@dataclass
class RuleEngine:
    ruleset: RuleSet
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD
    aggregation_policy: AggregationPolicy = None  # type: ignore[assignment]
    validate_on_init: bool = True

    def __post_init__(self) -> None:
        if self.aggregation_policy is None:
            self.aggregation_policy = AggregationPolicy()

        if self.validate_on_init:
            validate_ruleset(self.ruleset)

    # ------------------------------------------------------------------
    def evaluate(
        self,
        evidence: Evidence,
        context: Optional[Dict[str, Any]] = None,
    ) -> EngineReport:
        merged_context = dict(evidence.context)

        if context:
            merged_context.update(context)

        context = merged_context
        evidence.context.update(context)
        evidence.context.setdefault("rule_results", {})

        order = topological_order(self.ruleset)
        results_by_id: Dict[str, RuleResult] = {}
        all_calculations: List[Dict[str, Any]] = []

        for rule_id in order:
            rule = self.ruleset.by_id(rule_id)

            if rule is None:
                continue

            result = self._evaluate_rule(
                rule,
                evidence,
                context,
                results_by_id,
            )

            results_by_id[rule_id] = result

            evidence.context["rule_results"][rule_id] = {
                "status": result.status.value,
                "applicability": result.applicability.value,
            }

            if result.calculations:
                all_calculations.extend(result.calculations)

        # Preserve the ruleset's declared order in the report, regardless of
        # the dependency-driven internal evaluation order.
        ordered_results = [
            results_by_id[r.rule_id]
            for r in self.ruleset.rules
            if r.rule_id in results_by_id
        ]

        aggregation = aggregate(
            ordered_results,
            self.aggregation_policy,
        )

        # Build canonical compliance decision package (spec section 16).
        as_of_str = str(
            context.get("as_of_date")
            or context.get("inspection_date")
            or _dt.date.today().isoformat()
        )[:10]

        active_versions = [
            {
                "rule_id": r.rule_id,
                "version": r.rule_version or "2011",
            }
            for r in ordered_results
        ]

        decision_pkg = ComplianceDecisionPackage(
            inspection_id=str(
                context.get("inspection_id")
                or f"insp-{uuid.uuid4().hex[:8]}"
            ),
            legal_basis={
                "regulation": (
                    self.ruleset.ruleset_id
                    or "IN-LMPC-2011"
                ),
                "ruleset_id": (
                    self.ruleset.ruleset_id
                    or "IN-LMPC-2011"
                ),
                "ruleset_version": (
                    self.ruleset.ruleset_version
                    or "2011-consolidated"
                ),
                "as_of_date": as_of_str,
                "active_rule_versions": active_versions,
            },
            overall_result=aggregation.overall_status.value,
            summary={
                "rules_selected": len(ordered_results),
                "rules_considered": len(
                    [
                        r
                        for r in ordered_results
                        if r.status
                        is not ComplianceStatus.NOT_CONSIDERED
                    ]
                ),
                "rules_not_considered": len(
                    [
                        r
                        for r in ordered_results
                        if r.status
                        is ComplianceStatus.NOT_CONSIDERED
                    ]
                ),
                "rules_not_applicable": len(
                    [
                        r
                        for r in ordered_results
                        if r.status
                        is ComplianceStatus.NOT_APPLICABLE
                    ]
                ),
                "rules_exempted": len(
                    [
                        r
                        for r in ordered_results
                        if r.status
                        is ComplianceStatus.EXEMPTED
                    ]
                ),
                "rules_passed": len(
                    [
                        r
                        for r in ordered_results
                        if r.status is ComplianceStatus.PASS
                    ]
                ),
                "rules_failed": len(
                    [
                        r
                        for r in ordered_results
                        if r.status is ComplianceStatus.FAIL
                    ]
                ),
                "rules_uncertain": len(
                    [
                        r
                        for r in ordered_results
                        if r.status
                        is ComplianceStatus.UNCERTAIN
                    ]
                ),
                "engine_errors": len(
                    [
                        r
                        for r in ordered_results
                        if r.status
                        is ComplianceStatus.ENGINE_ERROR
                    ]
                ),
            },
            rules=[
                r.to_dict()
                for r in ordered_results
                if r.status
                is not ComplianceStatus.NOT_CONSIDERED
            ],
            rules_not_considered=[
                r.to_dict()
                for r in ordered_results
                if r.status
                is ComplianceStatus.NOT_CONSIDERED
            ],
            evidence=[
                ev.as_dict()
                for ev in evidence.fields.values()
            ],
            calculations=all_calculations,
            dependencies=order,
            audit={
                "ruleset_id": self.ruleset.ruleset_id,
                "policy": aggregation.policy,
                "critical_failures": aggregation.critical_failures,
            },
        )

        return EngineReport(
            results=ordered_results,
            aggregation=aggregation,
            dependency_order=order,
            ruleset_id=self.ruleset.ruleset_id,
            ruleset_version=self.ruleset.ruleset_version,
            decision_package=decision_pkg,
        )

    # ------------------------------------------------------------------
    def _evaluate_rule(
        self,
        rule: Rule,
        evidence: Evidence,
        context: Dict[str, Any],
        prior_results: Dict[str, RuleResult],
    ) -> RuleResult:
        trace: Dict[str, Any] = {
            "rule_id": rule.rule_id,
            "stages": [],
        }

        def stage(name: str, payload: Any) -> None:
            trace["stages"].append(
                {
                    "stage": name,
                    "detail": payload,
                }
            )

        stage(
            "rule_selected",
            {
                "rule_id": rule.rule_id,
                "version": rule.version,
            },
        )

        # 0. Active rule date & status check.
        filter_dates = (
            "as_of_date" in context
            or "inspection_date" in context
            or context.get("filter_by_date", False)
        )

        if filter_dates:
            as_of_str = str(
                context.get("as_of_date")
                or context.get("inspection_date")
            )[:10]

            try:
                as_of = _dt.date.fromisoformat(as_of_str)

                if rule.effective_from:
                    eff_from = _dt.date.fromisoformat(
                        str(rule.effective_from)[:10]
                    )

                    if as_of < eff_from:
                        return self._not_considered(
                            rule,
                            trace,
                            (
                                f"Rule not yet effective on {as_of} "
                                f"(effective from {rule.effective_from})"
                            ),
                        )

                if rule.effective_to:
                    eff_to = _dt.date.fromisoformat(
                        str(rule.effective_to)[:10]
                    )

                    if as_of >= eff_to:
                        return self._not_considered(
                            rule,
                            trace,
                            (
                                f"Rule superseded/expired on "
                                f"{rule.effective_to} "
                                f"(inspected as of {as_of})"
                            ),
                        )

            except Exception:
                pass

        elif rule.status in (
            "not_implemented",
            "not_considered",
            "superseded",
        ):
            return self._not_considered(
                rule,
                trace,
                rule.description
                or f"Rule explicitly marked {rule.status}",
            )

        # Dependency check.
        for dep in rule.depends_on:
            dep_result = prior_results.get(dep)

            if dep_result is None:
                stage(
                    "dependency",
                    f"dependency '{dep}' was not evaluated",
                )

                return self._error_result(
                    rule,
                    trace,
                    f"dependency '{dep}' was not evaluated",
                )

        # 1. Scope match (applies_to).
        scope_match = _matches_applies_to(
            rule,
            context,
        )

        if scope_match is False:
            stage(
                "applicability",
                "out of declared scope (applies_to)",
            )

            return self._not_applicable(
                rule,
                trace,
                (
                    "Rule's declared scope (applies_to) "
                    "does not match this context."
                ),
            )

        if scope_match is None:
            stage(
                "applicability",
                "scope context incomplete",
            )

            return self._uncertain_applicability(
                rule,
                trace,
                "Context needed to evaluate rule scope was not supplied.",
            )

        # 2. Applicability condition.
        try:
            appl_trace = evaluate_condition(
                rule.applicability,
                evidence,
                self.low_confidence_threshold,
                rule.rule_id,
            )

        except RuleConfigurationError as exc:
            return self._error_result(
                rule,
                trace,
                str(exc),
            )

        stage(
            "applicability",
            appl_trace.to_dict(),
        )

        applicability = _tri_to_applicability(
            appl_trace.result
        )

        if applicability is ApplicabilityStatus.NOT_APPLICABLE:
            return self._not_applicable(
                rule,
                trace,
                appl_trace.detail
                or "Applicability condition is false.",
            )

        if applicability is ApplicabilityStatus.UNCERTAIN:
            return self._uncertain_applicability(
                rule,
                trace,
                "Insufficient evidence to determine applicability.",
            )

        # 3. Exemptions.
        for exemption in rule.exemptions:
            try:
                ex_trace = evaluate_condition(
                    exemption.condition,
                    evidence,
                    self.low_confidence_threshold,
                    rule.rule_id,
                )
            except RuleConfigurationError as exc:
                return self._error_result(rule, trace, str(exc))

            stage(
                "exemption_check",
                {
                    "id": exemption.id,
                    **ex_trace.to_dict(),
                },
            )

            if ex_trace.result is Tri.TRUE:
                reason = (
                    exemption.description
                    or f"Exemption '{exemption.id}' applies."
                )

                stage(
                    "rule_result",
                    ComplianceStatus.EXEMPTED.value,
                )

                return RuleResult(
                    rule_id=rule.rule_id,
                    rule_version=rule.version,
                    name=rule.name,
                    applicability=ApplicabilityStatus.EXEMPTED,
                    applicability_reason=reason,
                    status=ComplianceStatus.EXEMPTED,
                    reason=reason,
                    severity=rule.severity,
                    priority=rule.priority,
                    dependencies=list(rule.depends_on),
                    legal_source=rule.legal_source,
                    provision=rule.provision,
                    explanation=_explain(
                        rule,
                        ApplicabilityStatus.EXEMPTED,
                        ComplianceStatus.EXEMPTED,
                        reason,
                    ),
                    trace=trace,
                )

        # 4. Derived calculations.
        calc_dicts: List[Dict[str, Any]] = []

        try:
            calc_traces: List[CalcTrace] = run_derived(
                [
                    d.model_dump()
                    for d in rule.derived
                ],
                evidence,
                rule.rule_id,
            )

            calc_dicts = [
                c.to_dict()
                for c in calc_traces
            ]

        except RuleConfigurationError as exc:
            return self._error_result(
                rule,
                trace,
                str(exc),
            )

        stage(
            "calculation",
            calc_dicts,
        )

        # 5. Requirements (or the bare top-level condition as one implicit
        # requirement).
        requirements: List[Requirement] = list(
            rule.requirements
        )

        if not requirements and rule.condition is not None:
            requirements = [
                Requirement(
                    id=rule.rule_id,
                    description=rule.description,
                    condition=rule.condition,
                )
            ]

        if not requirements and rule.condition is None:
            return self._not_considered(
                rule,
                trace,
                "No requirements or conditions defined for this rule.",
            )

        requirement_results: List[RequirementResult] = []
        all_citations: List[EvidenceCitation] = []
        all_missing: List[str] = []

        try:
            for req in requirements:
                cond_trace = evaluate_condition(
                    req.condition,
                    evidence,
                    self.low_confidence_threshold,
                    rule.rule_id,
                )

                stage(
                    "condition_evaluation",
                    {
                        "requirement_id": req.id,
                        **cond_trace.to_dict(),
                    },
                )

                req_status = _tri_to_compliance(
                    cond_trace.result
                )

                citations = _collect_evidence_citations(
                    cond_trace,
                    evidence,
                )

                missing = _missing_fields(
                    cond_trace
                )

                all_citations.extend(citations)
                all_missing.extend(missing)

                if req_status is ComplianceStatus.PASS:
                    msg = (
                        req.message_pass
                        or (
                            "Requirement satisfied: "
                            f"{req.description or req.id}"
                        )
                    )

                elif req_status is ComplianceStatus.FAIL:
                    msg = (
                        req.message_fail
                        or (
                            "Requirement not satisfied: "
                            f"{req.description or req.id}"
                        )
                    )

                else:
                    msg = (
                        req.message_uncertain
                        or (
                            f"Insufficient evidence for requirement: "
                            f"{req.description or req.id} "
                            f"(missing: {missing})"
                            if missing
                            else
                            f"Insufficient evidence for requirement: "
                            f"{req.description or req.id}"
                        )
                    )

                requirement_results.append(
                    RequirementResult(
                        requirement_id=req.id,
                        description=req.description,
                        status=req_status,
                        reason=msg,
                        evidence=citations,
                    )
                )

        except RuleConfigurationError as exc:
            return self._error_result(
                rule,
                trace,
                str(exc),
            )

        stage(
            "evidence",
            [
                c.to_dict()
                for c in all_citations
            ],
        )

        overall_req_status = (
            self._combine_requirement_statuses(
                [
                    r.status
                    for r in requirement_results
                ]
            )
        )

        reason = "; ".join(
            r.reason
            for r in requirement_results
        ) or "No requirements defined."

        stage(
            "rule_result",
            overall_req_status.value,
        )

        return RuleResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            name=rule.name,
            applicability=ApplicabilityStatus.APPLICABLE,
            applicability_reason=(
                appl_trace.detail
                or "Applicability condition is true."
            ),
            status=overall_req_status,
            reason=reason,
            severity=rule.severity,
            priority=rule.priority,
            requirement_results=requirement_results,
            evidence=list(
                {
                    c.field: c
                    for c in all_citations
                }.values()
            ),
            missing_evidence=sorted(
                set(all_missing)
            ),
            calculations=calc_dicts,
            dependencies=list(rule.depends_on),
            review_required=overall_req_status
            in (
                ComplianceStatus.UNCERTAIN,
                ComplianceStatus.ENGINE_ERROR,
            ),
            legal_source=rule.legal_source,
            provision=rule.provision,
            explanation=_explain(
                rule,
                ApplicabilityStatus.APPLICABLE,
                overall_req_status,
                reason,
            ),
            trace=trace,
        )

    @staticmethod
    def _combine_requirement_statuses(
        statuses: List[ComplianceStatus],
    ) -> ComplianceStatus:
        if not statuses:
            return ComplianceStatus.UNCERTAIN

        if any(
            s is ComplianceStatus.FAIL
            for s in statuses
        ):
            return ComplianceStatus.FAIL

        if any(
            s is ComplianceStatus.UNCERTAIN
            for s in statuses
        ):
            return ComplianceStatus.UNCERTAIN

        return ComplianceStatus.PASS

    @staticmethod
    def _not_applicable(
        rule: Rule,
        trace: Dict[str, Any],
        reason: str,
    ) -> RuleResult:
        trace["stages"].append(
            {
                "stage": "rule_result",
                "detail": ComplianceStatus.NOT_APPLICABLE.value,
            }
        )

        return RuleResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            name=rule.name,
            applicability=ApplicabilityStatus.NOT_APPLICABLE,
            applicability_reason=reason,
            status=ComplianceStatus.NOT_APPLICABLE,
            reason=reason,
            severity=rule.severity,
            priority=rule.priority,
            dependencies=list(rule.depends_on),
            legal_source=rule.legal_source,
            provision=rule.provision,
            explanation=_explain(
                rule,
                ApplicabilityStatus.NOT_APPLICABLE,
                ComplianceStatus.NOT_APPLICABLE,
                reason,
            ),
            trace=trace,
        )

    @staticmethod
    def _uncertain_applicability(
        rule: Rule,
        trace: Dict[str, Any],
        reason: str,
    ) -> RuleResult:
        trace["stages"].append(
            {
                "stage": "rule_result",
                "detail": ComplianceStatus.UNCERTAIN.value,
            }
        )

        return RuleResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            name=rule.name,
            applicability=ApplicabilityStatus.UNCERTAIN,
            applicability_reason=reason,
            status=ComplianceStatus.UNCERTAIN,
            reason=reason,
            severity=rule.severity,
            priority=rule.priority,
            dependencies=list(rule.depends_on),
            review_required=True,
            legal_source=rule.legal_source,
            provision=rule.provision,
            explanation=_explain(
                rule,
                ApplicabilityStatus.UNCERTAIN,
                ComplianceStatus.UNCERTAIN,
                reason,
            ),
            trace=trace,
        )

    @staticmethod
    def _error_result(
        rule: Rule,
        trace: Dict[str, Any],
        message: str,
    ) -> RuleResult:
        trace["stages"].append(
            {
                "stage": "rule_result",
                "detail": ComplianceStatus.ENGINE_ERROR.value,
            }
        )

        return RuleResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            name=rule.name,
            applicability=ApplicabilityStatus.UNCERTAIN,
            applicability_reason="Rule configuration error.",
            status=ComplianceStatus.ENGINE_ERROR,
            reason=message,
            severity=rule.severity,
            priority=rule.priority,
            dependencies=list(rule.depends_on),
            review_required=True,
            legal_source=rule.legal_source,
            provision=rule.provision,
            explanation=(
                f"ENGINE/RULE CONFIGURATION ERROR for "
                f"{rule.rule_id}: {message}"
            ),
            trace=trace,
            error=message,
        )

    @staticmethod
    def _not_considered(
        rule: Rule,
        trace: Dict[str, Any],
        reason: str,
    ) -> RuleResult:
        trace["stages"].append(
            {
                "stage": "rule_result",
                "detail": ComplianceStatus.NOT_CONSIDERED.value,
            }
        )

        return RuleResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            name=rule.name,
            applicability=ApplicabilityStatus.NOT_APPLICABLE,
            applicability_reason=reason,
            status=ComplianceStatus.NOT_CONSIDERED,
            reason=reason,
            severity=rule.severity,
            priority=rule.priority,
            dependencies=list(rule.depends_on),
            legal_source=rule.legal_source,
            provision=rule.provision,
            explanation=(
                f"Rule {rule.rule_id} was NOT CONSIDERED: "
                f"{reason}"
            ),
            trace=trace,
        )