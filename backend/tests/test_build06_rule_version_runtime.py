from datetime import date

import pytest

from regulatory.models import ApprovalState, RuleVersion
from regulatory.runtime import (
    RuleVersionSelectionError,
    apply_rule_versions,
    coerce_inspection_date,
    version_label,
)


def rv(rule_id, version, start, *, end=None, state=ApprovalState.ACTIVE, ident=None):
    return RuleVersion(
        id=ident or f"{rule_id}-{version}",
        module="lmpc",
        regulation="Legal Metrology (Packaged Commodities) Rules, 2011",
        rule_id=rule_id,
        version=version,
        effective_from=date.fromisoformat(start),
        effective_to=date.fromisoformat(end) if end else None,
        approval_state=state,
    )


def test_dated_runtime_selects_historical_version_without_mutating_catalogue():
    rules = {"R1": {"rule_id": "R1", "version": "catalogue-current", "thresholds": []}}
    versions = [
        rv("R1", "2024", "2024-01-01", end="2026-01-01"),
        rv("R1", "2026", "2026-01-01"),
    ]

    resolved, selected = apply_rule_versions(
        rules, versions, inspection_date="2025-12-31"
    )

    assert resolved["R1"]["version"] == "2024"
    assert selected["R1"].version == "2024"
    assert rules["R1"]["version"] == "catalogue-current"
    assert version_label(selected) == "2024"


def test_future_version_is_not_selected():
    rules = {"R1": {"rule_id": "R1"}}
    versions = [rv("R1", "2027", "2027-01-01")]
    with pytest.raises(RuleVersionSelectionError):
        apply_rule_versions(rules, versions, inspection_date="2026-09-10")


def test_unapproved_version_is_not_selected():
    rules = {"R1": {"rule_id": "R1"}}
    versions = [rv("R1", "2026", "2026-01-01", state=ApprovalState.APPROVED)]
    with pytest.raises(RuleVersionSelectionError):
        apply_rule_versions(rules, versions, inspection_date=date(2026, 9, 10))


def test_overlapping_versions_are_rejected_by_selector():
    rules = {"R1": {"rule_id": "R1"}}
    versions = [
        rv("R1", "A", "2025-01-01"),
        rv("R1", "B", "2026-01-01"),
    ]
    with pytest.raises(RuleVersionSelectionError):
        apply_rule_versions(rules, versions, inspection_date="2026-09-10")


def test_invalid_date_is_rejected():
    with pytest.raises(ValueError):
        coerce_inspection_date("10/09/2026")


def test_run_inspection_carries_selected_version_and_date(monkeypatch):
    import rule_engine

    monkeypatch.setattr(
        rule_engine,
        "load_rules",
        lambda: {"LMPC-2011-R6-DECLARATIONS": {"rule_id": "LMPC-2011-R6-DECLARATIONS", "version": "catalogue-current", "requirements": []}},
    )
    selected = rv("LMPC-2011-R6-DECLARATIONS", "2026.1", "2026-01-01")

    result = rule_engine.run_inspection(
        inspection_id="build06-runtime",
        sale_type="retail",
        product_category="generic",
        net_quantity_value=100,
        net_quantity_unit="g",
        mrp=10,
        extractions={},
        inspection_date="2026-09-10",
        rule_versions=[selected],
    )

    assert result.inspection_date == "2026-09-10"
    assert result.applicable_rule_version == "2026.1"
