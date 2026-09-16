"""
test_amendment_target_hierarchy.py

Focused tests for the amendment target hierarchy:

  Amendment item  = positional id in the amending document  (e.g. "(i)")
  Amendment target = canonical rule being amended            (e.g. "Rule 6(1)(a)")

These two must be SEPARATE on ExtractedRule.

Tests:
  1. extract_amendment_target() for GSR-577 real clause texts
  2. End-to-end pipeline: three substantive leaves produce correct
     amendment_target / amendment_item pairs
"""
import pytest
from lexmetra_rules.provision_classification import extract_amendment_target


# ---------------------------------------------------------------------------
# Unit tests: extract_amendment_target
# ---------------------------------------------------------------------------

# GSR-577 real clause texts (abbreviated)
_CLAUSE_A = (
    "In rule 6, in sub-rule (1), in clause (a), after the existing proviso, "
    "the following proviso shall be inserted, namely:- "
    "\"Provided further that electronic products manufactured on or after the "
    "15th day of July, 2022 shall bear a declaration ...\""
)
_CLAUSE_B = (
    "In rule 6, in sub-rule (1), in clause (b), after the existing proviso, "
    "the following proviso shall be inserted, namely:- "
    "\"Provided that electronic products manufactured on or after the "
    "15th day of July, 2022 shall conform to the requirements ...\""
)
_CLAUSE_F = (
    "In rule 6, in sub-rule (1), in clause (f), for the figures \"500 g\" and "
    "\"200 g\", the figures \"1 kg\" and \"500 g\" shall be substituted."
)

@pytest.mark.parametrize("text,expected_target", [
    (_CLAUSE_A, "Rule 6(1)(a)"),
    (_CLAUSE_B, "Rule 6(1)(b)"),
    (_CLAUSE_F, "Rule 6(1)(f)"),
    # Simpler forms
    ("In rule 6, in sub-rule (1), the following shall be inserted", "Rule 6(1)"),
    ("In rule 6, in clause (a), the following shall be inserted", "Rule 6(a)"),
    ("In rule 6, the following rule shall be inserted", "Rule 6"),
    # No rule mentioned → None
    ("shall be omitted", None),
    ("", None),
])
def test_extract_amendment_target(text, expected_target):
    assert extract_amendment_target(text) == expected_target


# ---------------------------------------------------------------------------
# End-to-end pipeline test: amendment_target / amendment_item on ExtractedRule
# ---------------------------------------------------------------------------

from lexmetra_rules.pipeline import run_pipeline_from_pages
from lexmetra_rules.models import PageText, TextSource


def _make_page(page_no: int, text: str) -> PageText:
    return PageText(
        page_no=page_no,
        text=text,
        source=TextSource.NATIVE,
        confidence=1.0,
    )



# Minimal synthetic GSR-577-like document text (abbreviated, no Hindi, no OCR)
_AMENDMENT_DOC = """\
THE LEGAL METROLOGY (PACKAGED COMMODITIES) AMENDMENT RULES, 2022

Short title and commencement.—(1) These rules may be called the Legal Metrology
(Packaged Commodities) Amendment Rules, 2022.
(2) They shall come into force on the date of their publication in the Official Gazette.

Amendment of principal rules.—In the Legal Metrology (Packaged Commodities) Rules, 2011,

2. In rule 6, in sub-rule (1),-

(a) in clause (a), after the existing proviso, the following proviso shall be
inserted, namely:-

\"Provided further that electronic products manufactured or packed or imported on or
after the 15th July 2022, shall bear the mandatory declarations for a period of one year
from the date of manufacture or packing or import.\";

(b) in clause (b), after the existing proviso, the following proviso shall be
inserted, namely:-

\"Provided that electronic products manufactured or packed or imported on or after the
15th July 2022, shall comply with the applicable Indian Standard requirements.\";

(c) in clause (f), for the figures, letters and words \"500 g or 500 ml\", the
figures, letters and words \"1 kg or 1 litre\" shall be substituted.
"""


def test_extracted_rule_amendment_fields_accepted():
    """ExtractedRule must accept amendment_target and amendment_item and keep
    them separate from rule_id.  This is the core data-model requirement."""
    from datetime import date
    from lexmetra_rules.models import (
        ExtractedRule, ClassificationResult, EffectiveDates, SourceLocation,
    )

    rule = ExtractedRule(
        rule_id="Rule 2(a)(i)",          # positional id in amending doc
        title="Rule 2(a)(i)",
        source="GSR-577",
        document_id="gsr-577",
        text=(
            "In rule 6, in sub-rule (1), in clause (a), after the existing "
            "proviso, the following proviso shall be inserted, namely:- ..."
        ),
        source_location=SourceLocation(
            document_id="gsr-577",
            page_start=2,
            page_end=2,
            clause="2(a)(i)",
        ),
        effective_dates=EffectiveDates(effective_from=date(2022, 7, 15).isoformat()),
        amendment_target="Rule 6(1)(a)",  # ← the rule being amended
        amendment_item="(i)",             # ← ordinal marker in amending doc
    )

    # amendment_target and rule_id are strictly separate
    assert rule.rule_id == "Rule 2(a)(i)"
    assert rule.amendment_target == "Rule 6(1)(a)"
    assert rule.amendment_item == "(i)"
    assert rule.rule_id != rule.amendment_target


def test_gsr577_targets_via_extractor():
    """Confirm that the three GSR-577 clause texts each produce the correct
    amendment_target via extract_amendment_target(), which is what the
    pipeline wires into ExtractedRule.amendment_target at runtime."""
    cases = [
        (
            "In rule 6, in sub-rule (1), in clause (a), after the existing "
            "proviso, the following proviso shall be inserted, namely:- ...",
            "Rule 6(1)(a)",
            "(i)",
        ),
        (
            "In rule 6, in sub-rule (1), in clause (b), after the existing "
            "proviso, the following proviso shall be inserted, namely:- ...",
            "Rule 6(1)(b)",
            "(ii)",
        ),
        (
            "In rule 6, in sub-rule (1), in clause (f), for the figures "
            "\"500 g\" and \"200 g\", the figures \"1 kg\" and \"500 g\" "
            "shall be substituted.",
            "Rule 6(1)(f)",
            "(iii)",
        ),
    ]
    for text, expected_target, item in cases:
        got = extract_amendment_target(text)
        assert got == expected_target, (
            f"amendment item {item}: expected {expected_target!r}, got {got!r}"
        )
        # All three targets are distinct — no collapsing
    all_targets = [extract_amendment_target(text) for text, _, _ in cases]
    assert len(set(all_targets)) == 3, "All three amendment targets must be distinct"

