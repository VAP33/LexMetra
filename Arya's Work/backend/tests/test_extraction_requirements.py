from lexmetra_rules.extraction import extract_requirements


def test_extracts_shall_requirement():
    reqs = extract_requirements(
        "Every package shall bear the name and address of the manufacturer.", "6"
    )
    assert len(reqs) == 1
    assert reqs[0].id == "6.req1"


def test_suggests_canonical_field_for_mrp():
    reqs = extract_requirements(
        "Every package shall declare the maximum retail price inclusive of all taxes.", "6"
    )
    assert any(r.suggested_field == "mrp" for r in reqs)


def test_suggests_canonical_field_for_net_quantity():
    reqs = extract_requirements("The package shall bear the net quantity in grams.", "6")
    assert any(r.suggested_field == "net_quantity" for r in reqs)


def test_no_suggestion_when_no_canonical_term_matches():
    reqs = extract_requirements("The package shall be sturdy and weatherproof.", "6")
    assert reqs
    assert reqs[0].suggested_field is None


def test_multiple_requirements_get_sequential_ids():
    text = (
        "Every package shall bear the name of the manufacturer. "
        "Every package shall also declare the net quantity. "
        "Every package shall bear the maximum retail price."
    )
    reqs = extract_requirements(text, "6")
    assert [r.id for r in reqs] == ["6.req1", "6.req2", "6.req3"]


def test_no_requirement_markers_returns_empty():
    reqs = extract_requirements("This rule concerns definitions only.", "2")
    assert reqs == []
