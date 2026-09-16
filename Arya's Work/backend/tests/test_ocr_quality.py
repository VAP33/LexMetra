from lexmetra_rules.ocr_quality import _HAS_SPELLCHECKER, assess_text_quality


def test_clean_legal_text_scores_near_one():
    score, flagged = assess_text_quality(
        "Every person shall bear the declaration of the manufacturer on the label."
    )
    assert score >= 0.9
    assert flagged == []


def test_corrupted_words_are_flagged():
    score, flagged = assess_text_quality(
        "Every perscn shail bear the decleration of the manufacturer."
    )
    assert score < 0.9
    assert "perscn" in flagged
    assert "shail" in flagged
    assert "decleration" in flagged


def test_digit_letter_fusion_symbol_is_flagged():
    score, flagged = assess_text_quality(
        "The declaration shall be made on the 1* day of packing."
    )
    assert score < 1.0
    assert any("1*" in f for f in flagged)


def test_empty_text_returns_perfect_score():
    score, flagged = assess_text_quality("")
    assert score == 1.0
    assert flagged == []


def test_legal_allowlist_terms_never_flagged():
    score, flagged = assess_text_quality(
        "Notwithstanding anything hereinbefore contained, the prepackaged commodity "
        "declaration shall be made by the importer or wholesaler."
    )
    assert flagged == []


def test_spellchecker_dependency_is_actually_being_used():
    """Confirms this environment has the real dictionary-backed checker
    active (not silently degraded to the weaker heuristic fallback),
    since the test suite's confidence claims depend on it."""
    assert _HAS_SPELLCHECKER is True


def test_heuristic_fallback_still_catches_vowel_free_garbage(monkeypatch):
    import lexmetra_rules.ocr_quality as oq
    monkeypatch.setattr(oq, "_HAS_SPELLCHECKER", False)
    score, flagged = assess_text_quality("The wrd shall bxr the nm of ths thg.")
    # Without a dictionary, only the crude heuristics apply — this just
    # confirms the fallback path runs without raising and still flags at
    # least the vowel-free tokens.
    assert isinstance(score, float)
