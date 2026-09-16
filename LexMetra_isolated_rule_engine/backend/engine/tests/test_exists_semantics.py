"""
Regression tests for the ``exists`` operator's three-valued semantics (P1 fix).

The invariant being enforced:

    MISSING != FALSE

Specifically, ``exists`` must distinguish three cases:

    1. No EvidenceValue, path resolves to MISSING (field never supplied by
       upstream) → Tri.UNKNOWN → UNCERTAIN
       Rationale: "I don't know whether this field exists on the label."

    2. EvidenceValue with present=False (upstream explicitly observed the
       field is absent from the label) → Tri.FALSE → FAIL
       Rationale: "Upstream searched the label and found it missing."

    3. EvidenceValue with a usable value, or path exists in context
       → Tri.TRUE → PASS
       Rationale: "Field is present and usable."

Before the fix, cases 1 and 2 were both returning Tri.FALSE, which turned
"insufficient evidence" into a compliance violation — a direct violation of
the invariant ``missing evidence != violation``.

These tests do NOT depend on any specific regulation, only on the generic
engine's contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from engine import Evidence, RuleEngine, load_ruleset_from_dict
from engine.conditions import Tri, evaluate_condition
from engine.results import ApplicabilityStatus, ComplianceStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(rule: dict) -> RuleEngine:
    return RuleEngine(load_ruleset_from_dict({"rules": [rule]}))


def _run(rule: dict, evidence: Evidence, context: dict | None = None) -> object:
    return _make_engine(rule).evaluate(evidence, context or {}).results[0]


_RULE = {
    "rule_id": "EXIST-TEST",
    "condition": {"op": "exists", "field": "target_field"},
}

_APPL_RULE = {
    "rule_id": "EXIST-APPL-TEST",
    "applicability": {"op": "exists", "field": "target_field"},
    "condition": {"op": "always"},
}


# ---------------------------------------------------------------------------
# Unit-level: evaluate_condition directly
# ---------------------------------------------------------------------------

def test_exists_on_never_supplied_field_is_unknown():
    """A field that was never registered at all must yield UNKNOWN."""
    ev = Evidence()
    trace = evaluate_condition(
        {"op": "exists", "field": "never_registered"},
        ev,
    )
    assert trace.result is Tri.UNKNOWN, (
        f"Expected UNKNOWN for absent field, got {trace.result}"
    )


def test_exists_on_present_false_evidence_value_is_false():
    """An EvidenceValue with present=False must yield FALSE (deterministic absence)."""
    ev = Evidence()
    ev.set_field("target_field", None, present=False)
    trace = evaluate_condition(
        {"op": "exists", "field": "target_field"},
        ev,
    )
    assert trace.result is Tri.FALSE, (
        f"Expected FALSE for present=False EvidenceValue, got {trace.result}"
    )


def test_exists_on_present_true_evidence_value_is_true():
    """An EvidenceValue with a real value must yield TRUE."""
    ev = Evidence()
    ev.set_field("target_field", "some value")
    trace = evaluate_condition(
        {"op": "exists", "field": "target_field"},
        ev,
    )
    assert trace.result is Tri.TRUE, (
        f"Expected TRUE for populated EvidenceValue, got {trace.result}"
    )


def test_exists_on_context_value_is_true():
    """A value present only in context (not as an EvidenceValue) must yield TRUE."""
    ev = Evidence()
    ev.set_context("target_field", "context_value")
    trace = evaluate_condition(
        {"op": "exists", "field": "target_field"},
        ev,
    )
    assert trace.result is Tri.TRUE, (
        f"Expected TRUE for context value, got {trace.result}"
    )


def test_exists_on_unusable_evidence_value_is_unknown():
    """An EvidenceValue marked unusable is not absent — the field exists but
    cannot be reliably read.  That is UNKNOWN, not FALSE or TRUE."""
    ev = Evidence()
    ev.set_field("target_field", "garbled", quality_state="CONFLICTING", usable=False)
    trace = evaluate_condition(
        {"op": "exists", "field": "target_field"},
        ev,
    )
    assert trace.result is Tri.UNKNOWN, (
        f"Expected UNKNOWN for unusable EvidenceValue, got {trace.result}"
    )


def test_exists_on_low_confidence_value_is_true():
    """Confidence filtering applies to VALUE comparisons, not exists().
    A low-confidence EvidenceValue still tells us the field was observed;
    exists() should return TRUE."""
    ev = Evidence()
    ev.set_field("target_field", "value", confidence=0.1)
    trace = evaluate_condition(
        {"op": "exists", "field": "target_field"},
        ev,
        low_conf=0.9,  # well above the field's confidence
    )
    # exists() does not apply the confidence gate — it only checks presence.
    assert trace.result is Tri.TRUE, (
        f"Expected TRUE: exists() does not apply confidence gate, got {trace.result}"
    )


# ---------------------------------------------------------------------------
# Engine-level: full rule evaluation
# ---------------------------------------------------------------------------

def test_rule_is_uncertain_when_field_never_supplied():
    """A requirement of form 'exists field' must yield UNCERTAIN (not FAIL)
    when the field was never supplied at all.  MISSING != FALSE."""
    result = _run(_RULE, Evidence())
    assert result.status is ComplianceStatus.UNCERTAIN, (
        f"Expected UNCERTAIN for never-supplied field, got {result.status}"
    )
    assert result.applicability is ApplicabilityStatus.APPLICABLE


def test_rule_fails_when_field_explicitly_absent():
    """A requirement of form 'exists field' must yield FAIL when upstream
    explicitly marks the field as not present (the deterministic case)."""
    ev = Evidence()
    ev.set_field("target_field", None, present=False)
    result = _run(_RULE, ev)
    assert result.status is ComplianceStatus.FAIL, (
        f"Expected FAIL for present=False, got {result.status}"
    )
    assert result.applicability is ApplicabilityStatus.APPLICABLE


def test_rule_passes_when_field_present():
    """A requirement of form 'exists field' must yield PASS when the field
    has a real value."""
    ev = Evidence()
    ev.set_field("target_field", "present")
    result = _run(_RULE, ev)
    assert result.status is ComplianceStatus.PASS, (
        f"Expected PASS for present field, got {result.status}"
    )


def test_applicability_uncertain_when_gate_field_never_supplied():
    """When an applicability condition uses exists() and the field was never
    supplied, applicability must be UNCERTAIN — the rule is a candidate but
    we cannot determine whether it applies."""
    result = _run(_APPL_RULE, Evidence())
    assert result.applicability is ApplicabilityStatus.UNCERTAIN, (
        f"Expected UNCERTAIN applicability, got {result.applicability}"
    )
    assert result.status is ComplianceStatus.UNCERTAIN


def test_applicability_not_applicable_when_field_explicitly_absent():
    """When an applicability condition uses exists() and upstream has
    explicitly marked the gate field absent, the rule is NOT_APPLICABLE."""
    ev = Evidence()
    ev.set_field("target_field", None, present=False)
    result = _run(_APPL_RULE, ev)
    assert result.applicability is ApplicabilityStatus.NOT_APPLICABLE, (
        f"Expected NOT_APPLICABLE, got {result.applicability}"
    )
    assert result.status is ComplianceStatus.NOT_APPLICABLE


def test_applicability_applicable_when_field_present():
    """When an applicability condition uses exists() and the field is present,
    the rule is APPLICABLE."""
    ev = Evidence()
    ev.set_field("target_field", "exists")
    result = _run(_APPL_RULE, ev)
    assert result.applicability is ApplicabilityStatus.APPLICABLE, (
        f"Expected APPLICABLE, got {result.applicability}"
    )
    assert result.status is ComplianceStatus.PASS


# ---------------------------------------------------------------------------
# Missing operator inherits correct semantics via _op_exists
# ---------------------------------------------------------------------------

def test_missing_on_never_supplied_field_is_unknown():
    """missing() is the logical complement of exists().
    If exists() → UNKNOWN, then missing() → UNKNOWN."""
    ev = Evidence()
    trace = evaluate_condition(
        {"op": "missing", "field": "never_registered"},
        ev,
    )
    assert trace.result is Tri.UNKNOWN, (
        f"Expected UNKNOWN for 'missing' on absent field, got {trace.result}"
    )


def test_missing_on_present_false_field_is_true():
    """missing() on a present=False EvidenceValue must be TRUE."""
    ev = Evidence()
    ev.set_field("target_field", None, present=False)
    trace = evaluate_condition(
        {"op": "missing", "field": "target_field"},
        ev,
    )
    assert trace.result is Tri.TRUE, (
        f"Expected TRUE for 'missing' on present=False, got {trace.result}"
    )


def test_missing_on_present_field_is_false():
    """missing() on a field with a real value must be FALSE."""
    ev = Evidence()
    ev.set_field("target_field", "here")
    trace = evaluate_condition(
        {"op": "missing", "field": "target_field"},
        ev,
    )
    assert trace.result is Tri.FALSE, (
        f"Expected FALSE for 'missing' on present field, got {trace.result}"
    )


# ---------------------------------------------------------------------------
# Three-valued interaction: AND / OR with exists() UNKNOWN
# ---------------------------------------------------------------------------

def test_and_with_exists_unknown_and_false_gives_false():
    """In AND, FALSE dominates UNKNOWN — correct K3 behaviour."""
    ev = Evidence()
    ev.set_field("confirmed_absent", None, present=False)
    # "absent_field" never registered → UNKNOWN
    trace = evaluate_condition(
        {
            "op": "and",
            "args": [
                {"op": "exists", "field": "absent_field"},     # UNKNOWN
                {"op": "exists", "field": "confirmed_absent"}, # FALSE
            ],
        },
        ev,
    )
    assert trace.result is Tri.FALSE, (
        f"Expected FALSE (FALSE dominates UNKNOWN in AND), got {trace.result}"
    )


def test_or_with_exists_unknown_and_true_gives_true():
    """In OR, TRUE dominates UNKNOWN — correct K3 behaviour."""
    ev = Evidence()
    ev.set_field("present_field", "yes")
    # "absent_field" never registered → UNKNOWN
    trace = evaluate_condition(
        {
            "op": "or",
            "args": [
                {"op": "exists", "field": "absent_field"},  # UNKNOWN
                {"op": "exists", "field": "present_field"}, # TRUE
            ],
        },
        ev,
    )
    assert trace.result is Tri.TRUE, (
        f"Expected TRUE (TRUE dominates UNKNOWN in OR), got {trace.result}"
    )


def test_and_with_two_unknown_exists_gives_unknown():
    """Two UNKNOWN operands in AND → UNKNOWN."""
    ev = Evidence()
    trace = evaluate_condition(
        {
            "op": "and",
            "args": [
                {"op": "exists", "field": "field_a"},
                {"op": "exists", "field": "field_b"},
            ],
        },
        ev,
    )
    assert trace.result is Tri.UNKNOWN


# ---------------------------------------------------------------------------
# Invariant: empty product does not produce FAIL via exists
# ---------------------------------------------------------------------------

def test_empty_evidence_yields_uncertain_not_fail_for_exists_rule():
    """The core invariant: passing an empty Evidence object to a rule whose
    requirement uses exists() must never produce FAIL.  Before the fix this
    was FAIL; after the fix it must be UNCERTAIN."""
    result = _run(
        {
            "rule_id": "MUST-HAVE-FIELD",
            "condition": {"op": "exists", "field": "mandatory_field"},
        },
        Evidence(),
    )
    assert result.status is not ComplianceStatus.FAIL, (
        "REGRESSION: empty Evidence produced FAIL — missing evidence must not "
        "be treated as a violation."
    )
    assert result.status is ComplianceStatus.UNCERTAIN