from lexmetra_rules.models import (
    BoundThreshold,
    Clause,
    ClauseType,
    ConditionInfo,
    EffectiveDates,
    ExceptionInfo,
    RequirementInfo,
    ReviewStatus,
    SemanticRole,
)
from lexmetra_rules.validation import validate_clause


def _base_clause(**overrides) -> Clause:
    defaults = dict(
        clause_id="6",
        rule_id="6",
        parent_clause_id=None,
        clause_type=ClauseType.BODY,
        page_start=1,
        page_end=1,
        source_text="Every package shall bear the manufacturer's name.",
        semantic_role=SemanticRole.OBLIGATION,
        role_confidence=0.85,
        role_signals=["\"shall\""],
        confidence=0.8,
        review_status=ReviewStatus.NEEDS_REVIEW,
    )
    defaults.update(overrides)
    return Clause(**defaults)


def test_definition_clause_with_thresholds_is_a_validation_error():
    threshold = BoundThreshold(
        value=4.0, unit="litre", operator=None, applies_to="commodity",
        applies_to_confidence=0.5, clause_id="2", source_text="4 litre", page=1,
    )
    clause = _base_clause(clause_id="2", semantic_role=SemanticRole.DEFINITION, thresholds=[threshold])
    errors, warnings = validate_clause(clause)
    assert any("DEFINITION clause must not carry" in e for e in errors)


def test_threshold_clause_id_mismatch_is_an_error():
    threshold = BoundThreshold(
        value=25.0, unit="kg", operator="lte", applies_to="commodity",
        applies_to_confidence=0.5, clause_id="3(2)", source_text="25 kg", page=1,
    )
    clause = _base_clause(clause_id="3(1)", semantic_role=SemanticRole.EXEMPTION, thresholds=[threshold])
    errors, warnings = validate_clause(clause)
    assert any("clause_id mismatch" in e for e in errors)


def test_gazette_reference_in_threshold_source_is_an_error():
    threshold = BoundThreshold(
        value=629.0, unit="%", operator=None, applies_to=None,
        applies_to_confidence=0.0, clause_id="1", source_text="G.S.R. 629 dated", page=1,
    )
    clause = _base_clause(clause_id="1", thresholds=[threshold])
    errors, warnings = validate_clause(clause)
    assert any("Gazette" in e for e in errors)


def test_page_number_as_threshold_source_is_an_error():
    threshold = BoundThreshold(
        value=44.0, unit="%", operator=None, applies_to=None,
        applies_to_confidence=0.0, clause_id="1", source_text="44", page=1,
    )
    clause = _base_clause(clause_id="1", thresholds=[threshold])
    errors, warnings = validate_clause(clause)
    assert any("page number" in e for e in errors)


def test_date_like_threshold_source_is_an_error():
    threshold = BoundThreshold(
        value=1.0, unit="%", operator=None, applies_to=None,
        applies_to_confidence=0.0, clause_id="1", source_text="1 April 2011", page=1,
    )
    clause = _base_clause(clause_id="1", thresholds=[threshold])
    errors, warnings = validate_clause(clause)
    assert any("date" in e for e in errors)


def test_invalid_effective_date_is_an_error():
    clause = _base_clause(
        semantic_role=SemanticRole.EFFECTIVE_DATE,
        effective_date=EffectiveDates(effective_from="not-a-date"),
    )
    errors, warnings = validate_clause(clause)
    assert any("not a valid ISO date" in e for e in errors)


def test_valid_effective_date_has_no_error():
    clause = _base_clause(
        semantic_role=SemanticRole.EFFECTIVE_DATE,
        effective_date=EffectiveDates(effective_from="2011-04-01"),
    )
    errors, warnings = validate_clause(clause)
    assert errors == []


def test_unbound_exception_produces_warning_not_error():
    exception = ExceptionInfo(
        modifies_clause_id=None, description="Provided that this shall not apply.",
        condition_text=None, is_exemption=True, clause_id="9",
    )
    clause = _base_clause(clause_id="9", semantic_role=SemanticRole.EXEMPTION, exception=exception)
    errors, warnings = validate_clause(clause)
    assert errors == []
    assert any("could not be linked" in w for w in warnings)


def test_mismatched_clause_id_on_condition_is_an_error():
    condition = ConditionInfo(subject=None, condition_type="import_status", condition_text="if imported", clause_id="WRONG")
    clause = _base_clause(clause_id="6", condition=condition)
    errors, warnings = validate_clause(clause)
    assert any("condition.clause_id" in e for e in errors)


def test_low_confidence_with_populated_fields_produces_warning():
    requirement = RequirementInfo(subject=None, action=None, object=None, requirement_text="text", clause_id="6")
    clause = _base_clause(role_confidence=0.2, requirement=requirement)
    errors, warnings = validate_clause(clause)
    assert any("confidence is low" in w for w in warnings)


def test_clean_clause_has_no_errors_or_warnings():
    clause = _base_clause()
    errors, warnings = validate_clause(clause)
    assert errors == []
    assert warnings == []
