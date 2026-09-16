from lexmetra_rules import rule_detection, segmentation
from lexmetra_rules.clause_extraction import (
    extract_applies_to,
    extract_bound_thresholds,
    extract_condition_info,
    extract_exception_info,
    extract_requirement_info,
)
from lexmetra_rules.clause_segmentation import ClauseSpan, segment_clauses
from lexmetra_rules.extraction.thresholds import extract_thresholds as old_whole_text_extractor
from lexmetra_rules.models import ClauseType, SemanticRole
from tests.fixtures.semantic_v2_regression_text import make_clean_pages


def _clauses_for(rule_id):
    pages = make_clean_pages()
    candidates = rule_detection.detect_headings(pages)
    spans = segmentation.segment_rules(pages, candidates)
    span = next(s for s in spans if s.raw_number == rule_id)
    return span, segment_clauses(span)


def test_rule2_four_litre_regression_old_extractor_would_have_included_it():
    """Documents the bug being fixed: the OLD whole-rule-text extractor
    genuinely did pick up the unrelated '4 litre' example."""
    span, _ = _clauses_for("2")
    old_result = old_whole_text_extractor(span.text)
    assert any(t.value == 4.0 and t.unit == "litre" for t in old_result)


def test_rule2_four_litre_is_excluded_by_new_clause_scoped_extraction():
    """The actual fix: a DEFINITION clause's illustrative number must
    never be promoted to a bound threshold."""
    _, clauses = _clauses_for("2")
    definition_clause = clauses[0]
    bound, notes = extract_bound_thresholds(definition_clause, SemanticRole.DEFINITION)
    assert bound == []
    assert any("4" in n and "litre" in n for n in notes)


def test_rule3_thresholds_bind_to_their_own_subclauses_not_the_whole_rule():
    _, clauses = _clauses_for("3")
    by_id = {c.clause_id: c for c in clauses}
    bound_31, _ = extract_bound_thresholds(by_id["3(1)"], SemanticRole.EXEMPTION)
    bound_32, _ = extract_bound_thresholds(by_id["3(2)"], SemanticRole.EXEMPTION)
    bound_33, _ = extract_bound_thresholds(by_id["3(3)"], SemanticRole.EXEMPTION)
    assert [(t.value, t.unit) for t in bound_31] == [(25.0, "kg")]
    assert [(t.value, t.unit) for t in bound_32] == [(25.0, "litre")]
    assert [(t.value, t.unit) for t in bound_33] == [(50.0, "kg")]
    # Every bound threshold must carry the clause_id it actually came from.
    assert bound_31[0].clause_id == "3(1)"
    assert bound_32[0].clause_id == "3(2)"
    assert bound_33[0].clause_id == "3(3)"


def test_threshold_applies_to_is_grounded_in_same_clause():
    clause = ClauseSpan(
        clause_id="7", parent_clause_id=None, clause_type=ClauseType.BODY,
        text="Every package shall declare the net quantity in a font not less than 3 mm in height.",
        page_start=1, page_end=1,
    )
    bound, notes = extract_bound_thresholds(clause, SemanticRole.OBLIGATION)
    assert len(bound) == 1
    assert bound[0].applies_to == "font"
    assert bound[0].applies_to_confidence > 0


def test_threshold_with_no_determinable_applies_to_is_still_bound_but_flagged():
    clause = ClauseSpan(
        clause_id="x", parent_clause_id=None, clause_type=ClauseType.OBLIGATION if False else ClauseType.BODY,
        text="Every consignment shall not exceed 25 kg.",
        page_start=1, page_end=1,
    )
    bound, notes = extract_bound_thresholds(clause, SemanticRole.OBLIGATION)
    assert len(bound) == 1
    # "consignment" is not in the applies_to vocabulary — must not be guessed.
    assert bound[0].applies_to is None
    assert any("could not be determined" in n for n in notes)


def test_condition_extraction_scoped_to_own_clause():
    clause = ClauseSpan(
        clause_id="9", parent_clause_id=None, clause_type=ClauseType.BODY,
        text="Where the commodity is imported, the country of origin shall be declared.",
        page_start=1, page_end=1,
    )
    info = extract_condition_info(clause)
    assert info is not None
    assert info.clause_id == "9"
    assert "imported" in info.condition_text.lower()


def test_requirement_subject_action_object_split():
    clause = ClauseSpan(
        clause_id="7", parent_clause_id=None, clause_type=ClauseType.BODY,
        text="Every package shall declare the net quantity on the label.",
        page_start=1, page_end=1,
    )
    info = extract_requirement_info(clause)
    assert info.subject == "Every package"
    assert "declare" in info.action
    assert info.requirement_text == clause.text


def test_requirement_without_shall_leaves_subject_and_action_none():
    clause = ClauseSpan(
        clause_id="6(2)", parent_clause_id="6", clause_type=ClauseType.SUBRULE,
        text="(2) the common or generic name of the commodity;",
        page_start=1, page_end=1,
    )
    info = extract_requirement_info(clause)
    assert info.subject is None
    assert info.action is None
    assert info.requirement_text == clause.text


def test_requirement_uses_inherited_subject_when_provided():
    clause = ClauseSpan(
        clause_id="6(2)", parent_clause_id="6", clause_type=ClauseType.SUBRULE,
        text="(2) the common or generic name of the commodity;",
        page_start=1, page_end=1,
    )
    info = extract_requirement_info(clause, inherited_subject="Every package")
    assert info.subject == "Every package"


def test_exception_bound_to_preceding_operative_clause():
    clause = ClauseSpan(
        clause_id="9.proviso1", parent_clause_id="9", clause_type=ClauseType.PROVISO,
        text="Provided that this exemption shall not apply to tea sold loose.",
        page_start=1, page_end=1,
    )
    info = extract_exception_info(clause, SemanticRole.EXEMPTION, modifies_clause_id="9")
    assert info.modifies_clause_id == "9"
    assert info.is_exemption is True


def test_exception_with_no_preceding_operative_clause_is_flagged_not_guessed():
    clause = ClauseSpan(
        clause_id="9.proviso1", parent_clause_id="9", clause_type=ClauseType.PROVISO,
        text="Provided that this shall not apply in certain circumstances.",
        page_start=1, page_end=1,
    )
    info = extract_exception_info(clause, SemanticRole.EXEMPTION, modifies_clause_id=None)
    assert info.modifies_clause_id is None


def test_applies_to_restricted_to_terms_in_same_clause():
    clause = ClauseSpan(
        clause_id="6(1)", parent_clause_id="6", clause_type=ClauseType.SUBRULE,
        text="(1) the name and address of the manufacturer or packer or importer;",
        page_start=1, page_end=1,
    )
    entities = extract_applies_to(clause)
    assert set(entities) == {"manufacturer", "packer", "importer"}


def test_applies_to_empty_when_no_vocab_term_present():
    clause = ClauseSpan(
        clause_id="x", parent_clause_id=None, clause_type=ClauseType.BODY,
        text="This provision has no relevant entity terms in it at all.",
        page_start=1, page_end=1,
    )
    assert extract_applies_to(clause) == []
