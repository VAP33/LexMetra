from lexmetra_rules.extraction import extract_conditions


def test_extracts_import_condition():
    conditions = extract_conditions(
        "Every package of an imported commodity shall declare the "
        "country of origin, if the commodity is imported into India."
    )
    assert len(conditions) >= 1
    assert any(c.condition_type == "import_status" for c in conditions)


def test_extracts_package_size_condition():
    conditions = extract_conditions(
        "Where the net quantity of a pre-packaged commodity does not "
        "exceed twenty grams, the requirement shall not apply."
    )
    assert len(conditions) >= 1
    assert any(c.condition_type == "package_size" for c in conditions)


def test_extracts_sale_type_condition():
    conditions = extract_conditions(
        "This rule shall apply subject to the condition that the sale "
        "is a wholesale transaction and not a retail sale."
    )
    assert any(c.condition_type == "sale_type" for c in conditions)


def test_no_condition_markers_returns_empty():
    conditions = extract_conditions("Every package shall bear the name of the manufacturer.")
    assert conditions == []


def test_condition_source_text_is_traceable():
    text = "In the case of an imported commodity, the country of origin shall be declared."
    conditions = extract_conditions(text)
    assert conditions
    assert conditions[0].source_text in text or conditions[0].source_text == text.strip()
