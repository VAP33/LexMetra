"""
test_amendment_operation_classification.py

Focused tests for classify_amendment_operation().

Covers:
  - Simple canonical patterns (INSERT, REMOVE, SUBSTITUTE, NEW_RULE)
  - GSR-577 real clause text from the current Legal Metrology PDF
      (i)  Rule 6(1)(a) → INSERT
      (ii) Rule 6(1)(b) → INSERT
      (iii)Rule 6(1)(f) → SUBSTITUTE
  - Hindi-language patterns
  - UNKNOWN fallback for unrecognised text
"""
import pytest
from lexmetra_rules.provision_classification import classify_amendment_operation


# ---------------------------------------------------------------------------
# Canonical single-phrase patterns
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    # INSERT
    ("shall be inserted", "INSERT"),
    ("shall stand inserted", "INSERT"),
    ("shall be added", "INSERT"),
    ("the following proviso shall be inserted", "INSERT"),
    ("the following sub-rule shall be inserted", "INSERT"),
    ("the following clause shall be inserted", "INSERT"),
    ("the following words shall be inserted", "INSERT"),
    # REMOVE
    ("shall be omitted", "REMOVE"),
    ("shall stand omitted", "REMOVE"),
    ("shall be deleted", "REMOVE"),
    ("shall stand deleted", "REMOVE"),
    ("shall be removed", "REMOVE"),
    # SUBSTITUTE
    ("shall be substituted", "SUBSTITUTE"),
    ("shall stand substituted", "SUBSTITUTE"),
    ("shall be replaced", "SUBSTITUTE"),
    # NEW_RULE
    ("the following rule shall be inserted", "NEW_RULE"),
    ("the following section shall be inserted", "NEW_RULE"),
    ("following new rule", "NEW_RULE"),
    ("following new section", "NEW_RULE"),
    # UNKNOWN
    ("the rule prescribes a labelling requirement", "UNKNOWN"),
    ("", "UNKNOWN"),
])
def test_canonical_patterns(text, expected):
    assert classify_amendment_operation(text) == expected


# NEW_RULE must win over INSERT
def test_new_rule_wins_over_insert():
    text = "the following new rule shall be inserted after rule 6"
    assert classify_amendment_operation(text) == "NEW_RULE"


# Case-insensitivity
def test_case_insensitive_omitted():
    assert classify_amendment_operation("SHALL BE OMITTED") == "REMOVE"

def test_case_insensitive_substituted():
    assert classify_amendment_operation("Shall Be Substituted") == "SUBSTITUTE"


# Whitespace normalisation (simulates OCR artefacts)
def test_ocr_spaces_omitted():
    assert classify_amendment_operation("shall  be   omitted") == "REMOVE"

def test_ocr_spaces_inserted():
    assert classify_amendment_operation("shall  be   inserted") == "INSERT"


# GSR-577 real amendment clauses
_GSR_577_CLAUSES = [
    (
        'In rule 6, in sub-rule (1), in clause (a), after the existing proviso, '
        'the following proviso shall be inserted, namely:- '
        '"Provided further that electronic products manufactured on or after the '
        '15th day of July, 2022 shall bear a declaration ..."',
        "INSERT",
    ),
    (
        'In rule 6, in sub-rule (1), in clause (b), after the existing proviso, '
        'the following proviso shall be inserted, namely:- '
        '"Provided that electronic products manufactured on or after the '
        '15th day of July, 2022 shall conform to the requirements ..."',
        "INSERT",
    ),
    (
        'In rule 6, in sub-rule (1), in clause (f), for the figures "500 g" and '
        '"200 g", the figures "1 kg" and "500 g" shall be substituted.',
        "SUBSTITUTE",
    ),
]

@pytest.mark.parametrize("text,expected", _GSR_577_CLAUSES)
def test_gsr577_real_clauses(text, expected):
    assert classify_amendment_operation(text) == expected


# Hindi patterns
def test_hindi_insert():
    assert classify_amendment_operation("अंतःस्थापित किया जाएगा") == "INSERT"

def test_hindi_remove():
    assert classify_amendment_operation("लोप किया जाएगा") == "REMOVE"

def test_hindi_substitute():
    assert classify_amendment_operation("प्रतिस्थापित किया जाएगा") == "SUBSTITUTE"
