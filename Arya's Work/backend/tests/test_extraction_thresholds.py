from lexmetra_rules.extraction import extract_thresholds


def test_extracts_numeral_threshold_with_lte_operator():
    thresholds = extract_thresholds("A package not exceeding 20 g is exempt from this requirement.")
    assert len(thresholds) == 1
    assert thresholds[0].value == 20.0
    assert thresholds[0].unit == "g"
    assert thresholds[0].operator == "lte"


def test_extracts_numeral_threshold_with_gt_operator():
    thresholds = extract_thresholds("Packages exceeding 500 ml shall comply with rule 6.")
    assert thresholds[0].operator == "gt"
    assert thresholds[0].value == 500.0
    assert thresholds[0].unit == "ml"


def test_extracts_word_form_threshold():
    thresholds = extract_thresholds(
        "Where the net quantity does not exceed twenty grams, the "
        "requirement shall not apply."
    )
    assert any(t.value == 20.0 and t.unit == "grams" for t in thresholds)


def test_extracts_multiple_thresholds_in_one_rule():
    thresholds = extract_thresholds(
        "The net weight or measure of the commodity is ten grams or "
        "ten millilitres or less."
    )
    values_units = {(t.value, t.unit) for t in thresholds}
    assert (10.0, "grams") in values_units
    assert (10.0, "millilitres") in values_units


def test_no_threshold_returns_empty():
    thresholds = extract_thresholds("Every package shall bear the name of the manufacturer.")
    assert thresholds == []


def test_threshold_preserves_source_text_verbatim_context():
    text = "A package not exceeding 20 g is exempt from this requirement."
    thresholds = extract_thresholds(text)
    assert "20 g" in thresholds[0].source_text or "20" in thresholds[0].source_text


def test_does_not_convert_units():
    """1 kg must be preserved as (1, 'kg'), never silently converted to 1000 g."""
    thresholds = extract_thresholds("A package of 1 kg or less is exempt.")
    assert thresholds[0].value == 1.0
    assert thresholds[0].unit == "kg"
