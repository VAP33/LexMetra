"""
Aggregation: turn many per-rule results into one explainable overall result
(section 19). Deliberately NOT "count PASS vs FAIL".

Default policy (overridable via ``AggregationPolicy``):
  1. Any ENGINE_ERROR on a rule that is APPLICABLE/UNCERTAIN-applicability
     -> overall ENGINE_ERROR (a broken rule must not silently disappear).
  2. Any FAIL on a rule with severity "critical" -> overall FAIL.
  3. Any FAIL at all (non-critical) -> overall FAIL, UNLESS only lower
     severities failed and the policy is configured to tolerate that (not
     the default -- default is conservative: any FAIL is a FAIL).
  4. No FAIL, but any UNCERTAIN among applicable rules -> overall UNCERTAIN.
  5. All applicable rules PASS (others NOT_APPLICABLE/EXEMPTED) -> PASS.
  6. No applicable rules at all -> NOT_APPLICABLE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .results import AggregationExplanation, ComplianceStatus, RuleResult


@dataclass
class AggregationPolicy:
    #: severities whose FAIL always forces overall FAIL regardless of anything else
    critical_severities: tuple = ("critical", "major")
    #: if True, a FAIL on a non-critical severity can be outweighed and only
    #: pushes the overall result to UNCERTAIN instead of FAIL (opt-in; the
    #: conservative default is False -- any FAIL is a FAIL).
    downgrade_minor_fail_to_uncertain: bool = False
    #: if True, when all applicable obligations are EXEMPTED, report overall EXEMPTED
    #: instead of NOT_APPLICABLE.
    allow_exempt_overall: bool = False


def aggregate(results: List[RuleResult], policy: AggregationPolicy = AggregationPolicy()) -> AggregationExplanation:
    counts: Dict[str, int] = {}
    for r in results:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1

    engine_errors = [r for r in results if r.status is ComplianceStatus.ENGINE_ERROR]
    if engine_errors:
        return AggregationExplanation(
            overall_status=ComplianceStatus.ENGINE_ERROR,
            reason=(f"{len(engine_errors)} rule(s) could not be evaluated due to a "
                    f"configuration error: {[r.rule_id for r in engine_errors]}. "
                    "No compliance verdict can be issued until this is fixed."),
            counts=counts, policy="engine_error_blocks_verdict",
        )

    critical_fails = [r for r in results if r.status is ComplianceStatus.FAIL
                       and r.severity in policy.critical_severities]
    if critical_fails:
        return AggregationExplanation(
            overall_status=ComplianceStatus.FAIL,
            reason=(f"{len(critical_fails)} critical/major rule(s) failed: "
                    f"{[r.rule_id for r in critical_fails]}."),
            counts=counts, critical_failures=[r.rule_id for r in critical_fails],
            policy="any_critical_fail_forces_fail",
        )

    other_fails = [r for r in results if r.status is ComplianceStatus.FAIL]
    if other_fails:
        if policy.downgrade_minor_fail_to_uncertain:
            return AggregationExplanation(
                overall_status=ComplianceStatus.UNCERTAIN,
                reason=(f"{len(other_fails)} non-critical rule(s) failed "
                        f"({[r.rule_id for r in other_fails]}); policy downgrades this to "
                        "UNCERTAIN pending review rather than an automatic FAIL."),
                counts=counts, policy="minor_fail_downgraded_to_uncertain",
            )
        return AggregationExplanation(
            overall_status=ComplianceStatus.FAIL,
            reason=f"{len(other_fails)} rule(s) failed: {[r.rule_id for r in other_fails]}.",
            counts=counts, policy="any_fail_forces_fail",
        )

    uncertain = [r for r in results if r.status is ComplianceStatus.UNCERTAIN]
    if uncertain:
        return AggregationExplanation(
            overall_status=ComplianceStatus.UNCERTAIN,
            reason=(f"No rule failed, but {len(uncertain)} rule(s) could not be "
                    f"conclusively evaluated from available evidence: "
                    f"{[r.rule_id for r in uncertain]}."),
            counts=counts, policy="any_uncertain_blocks_pass",
        )

    applicable_pass = [r for r in results if r.status is ComplianceStatus.PASS]
    if applicable_pass:
        return AggregationExplanation(
            overall_status=ComplianceStatus.PASS,
            reason=(f"All {len(applicable_pass)} applicable rule(s) passed "
                    f"({counts.get('NOT_APPLICABLE', 0)} not applicable, "
                    f"{counts.get('EXEMPTED', 0)} exempted)."),
            counts=counts, policy="all_applicable_passed",
        )

    exempted = [r for r in results if r.status is ComplianceStatus.EXEMPTED]
    if exempted and policy.allow_exempt_overall:
        return AggregationExplanation(
            overall_status=ComplianceStatus.EXEMPTED,
            reason=(f"All applicable obligations were exempted ({len(exempted)} rule(s) exempted, "
                    f"{counts.get('NOT_APPLICABLE', 0)} not applicable)."),
            counts=counts, policy="all_applicable_exempted",
        )

    return AggregationExplanation(
        overall_status=ComplianceStatus.NOT_APPLICABLE,
        reason="No rule in this ruleset was applicable to this product/evidence.",
        counts=counts, policy="no_applicable_rules",
    )
