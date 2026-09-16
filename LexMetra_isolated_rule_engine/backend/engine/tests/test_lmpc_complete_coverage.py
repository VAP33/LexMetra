"""Tests for complete LMPC Rules 1-34 coverage and execution."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine import (
    ComplianceEngine,
    ComplianceStatus,
    RuleEngine,
    load_ruleset,
)
from engine.validate import find_problems

RULES_PATH = (
    Path(__file__).resolve().parents[3]
    / "rules"
    / "generic"
    / "lmpc_complete_rules.json"
)


def test_complete_ruleset_loads_and_validates():
    ruleset = load_ruleset(RULES_PATH)
    assert ruleset.ruleset_id == "IN-LMPC-2011"
    assert len(ruleset.rules) >= 34

    problems = find_problems(ruleset)
    assert not problems, f"Validation problems found: {problems}"


def test_administrative_provisions_resolve_to_not_considered():
    ruleset = load_ruleset(RULES_PATH)
    engine = ComplianceEngine(ruleset=ruleset)
    report = engine.evaluate(
        {
            "product": {
                "name": "Standard Biscuit",
                "declared.manufacturer_name_address": "Acme Ltd",
                "declared.common_name": "Biscuits",
                "declared.net_quantity": 100,
                "declared.net_quantity.unit": "g",
                "declared.mfg_date": "2026-01-01",
                "declared.mrp": 25.0,
                "declared.consumer_care": "care@acme.com",
            }
        }
    )

    # Rule 1 (Title) and Rule 2 (Definitions) and Rule 34 (Repeal) are administrative
    r1 = report.by_id("LMPC-1-TITLE-COMMENCEMENT")
    assert r1 is not None
    assert r1.status == ComplianceStatus.NOT_CONSIDERED

    r2 = report.by_id("LMPC-2-DEFINITIONS")
    assert r2 is not None
    assert r2.status == ComplianceStatus.NOT_CONSIDERED

    r34 = report.by_id("LMPC-34-REPEAL-SAVINGS")
    assert r34 is not None
    assert r34.status == ComplianceStatus.NOT_CONSIDERED


def test_provenance_and_cross_references_retained():
    ruleset = load_ruleset(RULES_PATH)
    engine = ComplianceEngine(ruleset=ruleset)
    report = engine.evaluate({"product": {"name": "Test Product"}})

    r5 = report.by_id("LMPC-5-STANDARD-PACK-SIZE")
    assert r5 is not None
    assert "Second Schedule" in r5.cross_references
    assert r5.rule_type == "package_size_rules"

    r6_1_a = report.by_id("LMPC-6-1-A-MANUFACTURER")
    assert r6_1_a is not None
    assert "Rule 10" in r6_1_a.cross_references
    assert r6_1_a.legal_source == "Legal Metrology (Packaged Commodities) Rules, 2011"
    assert r6_1_a.provision == "Rule 6(1)(a)/(b)/(c)"


def test_small_pack_rule_26_a_exemption():
    ruleset = load_ruleset(RULES_PATH)
    engine = ComplianceEngine(ruleset=ruleset)

    # 5g sample pack is exempt under Rule 26(a)
    report = engine.evaluate(
        {
            "product": {
                "name": "Sample Sachet",
                "declared.net_quantity": 5,
                "declared.net_quantity.unit": "g",
            }
        }
    )

    r26a = report.by_id("LMPC-26-A-SMALL-PACK")
    assert r26a is not None
    assert r26a.status == ComplianceStatus.PASS


def test_third_schedule_unit_symbol_rule():
    ruleset = load_ruleset(RULES_PATH)
    engine = ComplianceEngine(ruleset=ruleset)

    # Valid SI symbol 'g' passes Rule 13
    report_valid = engine.evaluate(
        {
            "product": {
                "name": "Biscuits",
                "declared.net_quantity.unit": "g",
            }
        }
    )
    r13_valid = report_valid.by_id("LMPC-13-THIRD-SCHEDULE-UNITS")
    assert r13_valid is not None
    assert r13_valid.status == ComplianceStatus.PASS

    # Invalid symbol 'gms' fails Rule 13
    report_invalid = engine.evaluate(
        {
            "product": {
                "name": "Biscuits",
                "declared.net_quantity.unit": "gms",
            }
        }
    )
    r13_invalid = report_invalid.by_id("LMPC-13-THIRD-SCHEDULE-UNITS")
    assert r13_invalid is not None
    assert r13_invalid.status == ComplianceStatus.FAIL
