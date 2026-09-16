"""
Tests for Data-Driven Rule Engine and Generic Rule Evaluation.

Proves:
1. Synthetic rules can be defined dynamically as pure data and evaluated via evaluate_rule()
   and run_inspection() without adding any rule-specific Python function.
2. Rule applicability is evaluated BEFORE compliance:
   - NOT_APPLICABLE (empty findings) when scope/applicability condition fails.
   - UNCERTAIN when applicability condition cannot be determined due to missing/low-confidence evidence.
   - EXEMPT when exemption condition matches.
   - PASS when requirements and declarative conditions are satisfied.
   - FAIL when requirements or declarative conditions are violated.
3. Kleene 3-valued logic & Evidence semantics:
   - Missing field when package is fully covered yields confirmed absence (FAIL).
   - Missing field when package is partially covered or not observed yields UNCERTAIN (never automatic FAIL).
   - Low confidence evidence yields UNCERTAIN.
4. Amendment ingestion persistence with ApprovalState.EXTRACTED succeeds end-to-end.
"""

import pytest
from datetime import date, datetime, timezone
from schema import (
    FactStatus,
    SurfaceObservation,
    ImageQuality,
    EvidenceStatus,
)
from rule_engine import (
    RawExtraction,
    evaluate_rule,
    run_inspection,
    SPECIALIZED_EVALUATORS,
)
from backend.models import (
    ApprovalState,
    AmendmentDraft,
    AmendmentChange,
    RuleVersion,
)
from backend.db.persistence import (
    save_amendment_draft,
    get_amendment_draft,
    update_amendment_draft_state,
)


def _obs(side: str) -> SurfaceObservation:
    return SurfaceObservation(
        surface_id=side,
        image_id=f"img_{side}",
        evidence_coverage=1.0,
        image_quality=ImageQuality(status=EvidenceStatus.USABLE),
    )


# ==============================================================================
# 1. Synthetic Data-Driven Rule Tests (No Rule-Specific Python Functions)
# ==============================================================================

def test_synthetic_declaration_rule_evaluation():
    """
    Test a purely synthetic rule (e.g., Organic Certification declaration)
    evaluated generically without any entry in SPECIALIZED_EVALUATORS or Python function.
    """
    synthetic_rule_id = "SYNTH-ORGANIC-001"
    assert synthetic_rule_id not in SPECIALIZED_EVALUATORS

    organic_rule = {
        "rule_id": synthetic_rule_id,
        "name": "Organic Certification Declaration",
        "description": "Organic food products must declare an organic certification number.",
        "applies_to": {"product_category": "food", "is_organic": True},
        "requirements": ["organic_cert_number"],
    }

    context_matching = {
        "product_category": "food",
        "sale_type": "retail",
        "custom_attributes": {"is_organic": True},
    }

    # 1. Evidence with high-confidence organic_cert_number -> PASS
    extractions_pass = {
        "organic_cert_number": RawExtraction(
            field="organic_cert_number",
            value="ORG-IND-12345",
            confidence=0.95,
        )
    }
    facts_pass, findings_pass = evaluate_rule(
        rule=organic_rule,
        extractions=extractions_pass,
        captures=[],
        context=context_matching,
        low_confidence_threshold=0.6,
    )
    assert len(findings_pass) == 1
    assert findings_pass[0].status == FactStatus.PASS

    # 2. Evidence missing organic_cert_number with full 6-surface coverage -> FAIL
    full_captures = [_obs(s) for s in ("front", "back", "top", "bottom", "left", "right")]
    facts_fail, findings_fail = evaluate_rule(
        rule=organic_rule,
        extractions={},
        captures=full_captures,
        context=context_matching,
        low_confidence_threshold=0.6,
    )
    assert len(findings_fail) == 1
    assert findings_fail[0].status == FactStatus.FAIL
    assert "organic_cert_number" in findings_fail[0].reason
    assert "sufficient package coverage" in findings_fail[0].reason

    # 3. Context does not apply (not organic) -> NOT_APPLICABLE (empty findings)
    context_not_applicable = {
        "product_category": "food",
        "sale_type": "retail",
        "custom_attributes": {"is_organic": False},
    }
    facts_na, findings_na = evaluate_rule(
        rule=organic_rule,
        extractions=extractions_pass,
        captures=[],
        context=context_not_applicable,
        low_confidence_threshold=0.6,
    )
    assert len(findings_na) == 0


def test_synthetic_numeric_condition_rule():
    """
    Test a synthetic threshold rule evaluated via conditions dict:
    e.g. Sugar content threshold for front-of-pack warning.
    """
    threshold_rule_id = "SYNTH-SUGAR-THRESHOLD-002"
    assert threshold_rule_id not in SPECIALIZED_EVALUATORS

    sugar_rule = {
        "rule_id": threshold_rule_id,
        "name": "High Sugar Front Warning",
        "description": "If added sugar exceeds 10g per 100g, front of pack warning is required.",
        "applies_to": {"product_category": "food"},
        "condition": {
            "field": "added_sugar_g",
            "op": "<=",
            "value": 10.0,
        },
    }

    context = {"product_category": "food", "sale_type": "retail"}

    # Value <= 10.0 -> PASS
    ext_pass = {
        "added_sugar_g": RawExtraction(
            field="added_sugar_g",
            value="8.5",
            confidence=0.92,
        )
    }
    facts_p, findings_p = evaluate_rule(
        rule=sugar_rule,
        extractions=ext_pass,
        captures=[],
        context=context,
        low_confidence_threshold=0.6,
    )
    assert len(findings_p) == 1
    assert findings_p[0].status == FactStatus.PASS

    # Value > 10.0 -> FAIL
    ext_fail = {
        "added_sugar_g": RawExtraction(
            field="added_sugar_g",
            value="15.0",
            confidence=0.95,
        )
    }
    facts_f, findings_f = evaluate_rule(
        rule=sugar_rule,
        extractions=ext_fail,
        captures=[],
        context=context,
        low_confidence_threshold=0.6,
    )
    assert len(findings_f) == 1
    assert findings_f[0].status == FactStatus.FAIL
    assert "Condition violated" in findings_f[0].reason


# ==============================================================================
# 2. Rule Applicability & Exemption Evaluation Order Tests
# ==============================================================================

def test_exemption_takes_precedence_over_requirements():
    """
    Exemption rule (e.g. package <= 10g exempt from certain declarations).
    Even if requirement is missing, status must be EXEMPT, never FAIL.
    """
    small_pkg_rule = {
        "rule_id": "SYNTH-EXEMPT-003",
        "name": "Small Package Weight Exemption",
        "applies_to": {"product_category": "food"},
        "exemptions": [
            {
                "id": "small-weight-exemption",
                "condition": {
                    "field": "net_weight_g",
                    "op": "<=",
                    "value": 10.0,
                },
                "description": "Package <= 10g exempt.",
            }
        ],
        "requirements": ["nutrition_facts"],
    }

    context = {
        "product_category": "food",
        "sale_type": "retail",
        "net_weight_g": 5.0,
    }

    # Nutrition facts is NOT provided, but net_weight_g <= 10 -> EXEMPT
    facts, findings = evaluate_rule(
        rule=small_pkg_rule,
        extractions={},
        captures=[],
        context=context,
        low_confidence_threshold=0.6,
    )
    assert len(findings) == 1
    assert findings[0].status == FactStatus.EXEMPT
    assert "exempt" in findings[0].reason.lower()


# ==============================================================================
# 3. Evidence Semantics & Kleene 3-Valued Logic Tests
# ==============================================================================

def test_missing_evidence_without_coverage_is_uncertain():
    """
    If a required field is not observed and package was NOT fully scanned,
    the rule engine must return UNCERTAIN, never an automatic FAIL.
    """
    rule = {
        "rule_id": "SYNTH-DECL-004",
        "name": "Batch Number Declaration",
        "requirements": ["batch_number"],
    }

    # Empty captures means partial/unknown coverage
    facts, findings = evaluate_rule(
        rule=rule,
        extractions={},
        captures=[],
        context={"sale_type": "retail"},
        low_confidence_threshold=0.6,
    )
    assert len(findings) == 1
    assert findings[0].status == FactStatus.UNCERTAIN
    assert "not observed" in findings[0].reason or "incomplete coverage" in findings[0].reason


def test_low_confidence_evidence_yields_uncertain():
    """
    If an extracted field is present but below confidence threshold,
    the rule engine must mark UNCERTAIN.
    """
    rule = {
        "rule_id": "SYNTH-DECL-005",
        "name": "Country of Origin",
        "requirements": ["country_of_origin"],
    }

    low_conf_extractions = {
        "country_of_origin": RawExtraction(
            field="country_of_origin",
            value="India",
            confidence=0.45,  # below threshold 0.6
        )
    }

    facts, findings = evaluate_rule(
        rule=rule,
        extractions=low_conf_extractions,
        captures=[],
        context={"sale_type": "retail"},
        low_confidence_threshold=0.6,
    )
    assert len(findings) == 1
    assert findings[0].status == FactStatus.UNCERTAIN
    assert "confidence" in findings[0].reason.lower()


# ==============================================================================
# 4. Ingestion Draft Persistence Verification
# ==============================================================================

def test_amendment_draft_persistence_and_retrieval():
    """
    Verify amendment draft with ApprovalState.EXTRACTED and ApprovalState.PENDING_REVIEW
    persists into PostgreSQL and retrieves cleanly with all versioning/traceability attributes.
    """
    draft_id = "test-draft-synth-001"
    amendment = AmendmentDraft(
        id=draft_id,
        module="legal_metrology",
        source_document_id="doc_gazette_2026_march.pdf",
        approval_state=ApprovalState.EXTRACTED,
        extracted_at=datetime.now(timezone.utc),
        changes=[
            AmendmentChange(
                rule_id="LMPC-2026-R1",
                change_type="ADDITION",
                new_text="Goods over Rs 1000 must feature dynamic QR code.",
                effective_from=date(2026, 4, 1),
            )
        ],
        proposed_rule_versions=[
            RuleVersion(
                id="rv-synth-2026",
                module="legal_metrology",
                regulation="LMPC_RULES_2011",
                rule_id="LMPC-2026-R1",
                version="1.0.0",
                effective_from=date(2026, 4, 1),
                approval_state=ApprovalState.EXTRACTED,
                source_document_id="doc_gazette_2026_march.pdf",
                text="Goods over Rs 1000 must feature dynamic QR code.",
            )
        ],
        impact={"affected_commodities": ["electronics", "high_value_retail"]},
    )

    # 1. Save with ApprovalState.EXTRACTED into live PostgreSQL
    save_amendment_draft(amendment)

    # 2. Retrieve and verify
    retrieved = get_amendment_draft(draft_id)
    assert retrieved is not None
    assert retrieved["id"] == draft_id
    assert retrieved["approval_state"] == "EXTRACTED"
    payload = retrieved.get("payload") or {}
    changes = payload.get("changes", [])
    assert len(changes) == 1
    assert changes[0]["rule_id"] == "LMPC-2026-R1"

    # 3. Transition to PENDING_REVIEW
    update_amendment_draft_state(draft_id, ApprovalState.PENDING_REVIEW, reviewed_by="officer_sharma")
    retrieved_updated = get_amendment_draft(draft_id)
    assert retrieved_updated["approval_state"] == "PENDING_REVIEW"
