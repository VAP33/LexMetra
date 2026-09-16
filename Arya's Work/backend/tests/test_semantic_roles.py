from lexmetra_rules import rule_detection, segmentation
from lexmetra_rules.clause_segmentation import segment_clauses
from lexmetra_rules.models import SemanticRole
from lexmetra_rules.semantic_roles import classify_clause, refine_roles_with_parent_context
from tests.fixtures.semantic_v2_regression_text import make_clean_pages


def _clauses_for(rule_id):
    pages = make_clean_pages()
    candidates = rule_detection.detect_headings(pages)
    spans = segmentation.segment_rules(pages, candidates)
    span = next(s for s in spans if s.raw_number == rule_id)
    return segment_clauses(span)


def _classify_all(clauses):
    return refine_roles_with_parent_context([(c,) + classify_clause(c) for c in clauses])


def test_effective_date_role_detected():
    role, conf, sig = classify_clause(_clauses_for("1")[0])
    assert role == SemanticRole.EFFECTIVE_DATE
    assert conf >= 0.7


def test_definition_role_detected_from_quoted_means_pattern():
    role, conf, sig = classify_clause(_clauses_for("2")[0])
    assert role == SemanticRole.DEFINITION


def test_generic_includes_does_not_trigger_false_definition():
    """'includes' appearing generically (not in a quoted-term pattern)
    must not be misread as a definition."""
    from lexmetra_rules.clause_segmentation import ClauseSpan
    from lexmetra_rules.models import ClauseType

    clause = ClauseSpan(
        clause_id="x", parent_clause_id=None, clause_type=ClauseType.BODY,
        text="Every package includes a declaration of net quantity and shall bear the manufacturer's name.",
        page_start=1, page_end=1,
    )
    role, conf, sig = classify_clause(clause)
    assert role != SemanticRole.DEFINITION


def test_exemption_role_for_nothing_shall_apply_pattern():
    entries = _classify_all(_clauses_for("3"))
    by_id = {c.clause_id: (role, conf) for c, role, conf, sig in entries}
    assert by_id["3(1)"][0] == SemanticRole.EXEMPTION
    assert by_id["3(2)"][0] == SemanticRole.EXEMPTION
    assert by_id["3(3)"][0] == SemanticRole.EXEMPTION


def test_obligation_role_for_shall_pattern():
    role, conf, sig = classify_clause(_clauses_for("6")[0])
    assert role == SemanticRole.OBLIGATION


def test_prohibition_beats_obligation_for_shall_not():
    from lexmetra_rules.clause_segmentation import ClauseSpan
    from lexmetra_rules.models import ClauseType

    clause = ClauseSpan(
        clause_id="x", parent_clause_id=None, clause_type=ClauseType.BODY,
        text="A retailer shall not sell any package that does not bear the required declarations.",
        page_start=1, page_end=1,
    )
    role, conf, sig = classify_clause(clause)
    assert role == SemanticRole.PROHIBITION


def test_permission_role_for_may():
    from lexmetra_rules.clause_segmentation import ClauseSpan
    from lexmetra_rules.models import ClauseType

    clause = ClauseSpan(
        clause_id="x", parent_clause_id=None, clause_type=ClauseType.BODY,
        text="The manufacturer may declare additional voluntary information on the label.",
        page_start=1, page_end=1,
    )
    role, conf, sig = classify_clause(clause)
    assert role == SemanticRole.PERMISSION


def test_penalty_role_detected():
    from lexmetra_rules.clause_segmentation import ClauseSpan
    from lexmetra_rules.models import ClauseType

    clause = ClauseSpan(
        clause_id="x", parent_clause_id=None, clause_type=ClauseType.BODY,
        text="Any person who contravenes this rule shall be punishable with a fine of five thousand rupees.",
        page_start=1, page_end=1,
    )
    role, conf, sig = classify_clause(clause)
    assert role == SemanticRole.PENALTY


def test_enumerated_subclauses_inherit_parent_obligation():
    """This is regression item D from the brief: Rule 6's declaration
    list items must be recognized as requirements of the parent
    obligation, not classified independently as OTHER/CONDITION."""
    entries = _classify_all(_clauses_for("6"))
    by_id = {c.clause_id: role for c, role, conf, sig in entries}
    assert by_id["6"] == SemanticRole.OBLIGATION
    for sub_id in ["6(1)", "6(2)", "6(3)", "6(4)", "6(5)"]:
        assert by_id[sub_id] == SemanticRole.OBLIGATION, f"{sub_id} should inherit OBLIGATION"


def test_explanation_clause_type_forces_explanation_role():
    from lexmetra_rules.clause_segmentation import ClauseSpan
    from lexmetra_rules.models import ClauseType

    clause = ClauseSpan(
        clause_id="9.explanation1", parent_clause_id="9", clause_type=ClauseType.EXPLANATION,
        text="Explanation.\u2014For the purposes of this rule, package includes any wrapper.",
        page_start=1, page_end=1,
    )
    role, conf, sig = classify_clause(clause)
    assert role == SemanticRole.EXPLANATION


def test_table_clause_type_does_not_become_threshold_by_default():
    from lexmetra_rules.clause_segmentation import ClauseSpan
    from lexmetra_rules.models import ClauseType

    clause = ClauseSpan(
        clause_id="6.table1", parent_clause_id="6", clause_type=ClauseType.TABLE,
        text="500 1000 1500", page_start=1, page_end=1,
    )
    role, conf, sig = classify_clause(clause)
    assert role != SemanticRole.OBLIGATION
    assert conf < 0.7
