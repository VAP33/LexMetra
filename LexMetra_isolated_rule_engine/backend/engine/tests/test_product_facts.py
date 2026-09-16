"""Tests for Canonical Product Facts normalization layer."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine import (
    ComplianceEngine,
    ComplianceStatus,
    Evidence,
    FactState,
    CanonicalProductFacts,
    normalize_to_canonical_facts,
    product_to_evidence,
)


def test_fact_state_known():
    raw = {
        "product": {
            "name": "Tea",
            "mrp": 250.0,
        }
    }
    facts = normalize_to_canonical_facts(raw)
    mrp_fact = facts.get_fact("product.mrp")
    assert mrp_fact is not None
    assert mrp_fact.state == FactState.KNOWN
    assert mrp_fact.value == 250.0

    ev = facts.to_evidence()
    assert ev.fields["product.mrp"].is_present() is True
    assert ev.fields["product.mrp"].value == 250.0


def test_fact_state_explicitly_absent():
    raw = {
        "product": {
            "name": "Biscuits",
            "declared.mrp": {"present": False},
        }
    }
    facts = normalize_to_canonical_facts(raw)
    fact = facts.get_fact("declared.mrp")
    assert fact is not None
    assert fact.state == FactState.EXPLICITLY_ABSENT

    ev = facts.to_evidence()
    assert ev.fields["declared.mrp"].present is False
    assert ev.fields["declared.mrp"].is_present() is False


def test_fact_state_unknown_when_omitted():
    raw = {
        "product": {
            "name": "Soap",
        }
    }
    facts = normalize_to_canonical_facts(raw)
    assert facts.get_fact("declared.mrp") is None

    ev = facts.to_evidence()
    assert "declared.mrp" not in ev.fields
    # Looking up an omitted field via resolve returns MISSING, not False
    from engine.evidence import MISSING
    assert ev.resolve("declared.mrp") is MISSING


def test_nested_quantity_bridging():
    raw = {
        "product": {
            "name": "Sunflower Oil",
            "quantity": {
                "value": 1.0,
                "unit": "l",
            }
        }
    }
    facts = normalize_to_canonical_facts(raw)
    assert facts.get_fact("product.quantity.value") is not None
    assert facts.get_fact("declared.net_quantity") is not None
    assert facts.get_fact("declared.net_quantity").value == 1.0
    assert facts.get_fact("declared.net_quantity").unit == "l"
    assert facts.get_fact("declared.net_quantity.unit").value == "l"

    ev = facts.to_evidence()
    assert ev.fields["declared.net_quantity"].value == 1.0
    assert ev.fields["declared.net_quantity"].unit == "l"
    assert ev.fields["declared.net_quantity.unit"].value == "l"


def test_compliance_engine_evaluation_with_canonical_facts():
    engine = ComplianceEngine()
    
    # Missing MRP entirely -> UNCERTAIN, not FAIL (unknown != false)
    report_missing = engine.evaluate({
        "product": {
            "name": "Sample Product",
            "manufacturer_name_address": "ABC Corp, Mumbai",
            "common_name": "Sample",
            "quantity": {"value": 500, "unit": "g"},
            "mfg_date": "2026-01-01",
            "consumer_care": "care@abc.com",
        }
    })
    mrp_res = report_missing.by_id("LMPC-6-1-DA-MRP")
    assert mrp_res is not None
    assert mrp_res.status == ComplianceStatus.UNCERTAIN

    # When exemption status is unknown, result is UNCERTAIN (exemption uncertainty prevents false failure)
    report_unresolved_exemption = engine.evaluate({
        "product": {
            "name": "Sample Product",
            "mrp": {"present": False},
        }
    })
    mrp_res_unresolved = report_unresolved_exemption.by_id("LMPC-6-1-DA-MRP")
    assert mrp_res_unresolved is not None
    assert mrp_res_unresolved.status == ComplianceStatus.UNCERTAIN
    assert "Exemption uncertainty" in mrp_res_unresolved.reason

    # When product is confirmed non-exempt and MRP is explicitly absent -> FAIL
    report_absent = engine.evaluate({
        "product": {
            "name": "Sample Product",
            "manufacturer_name_address": "ABC Corp, Mumbai",
            "common_name": "Sample",
            "quantity": {"value": 500, "unit": "g"},
            "mfg_date": "2026-01-01",
            "consumer_care": "care@abc.com",
            "mrp": {"present": False},
            "exemption": {"is_exempt": False},
        }
    })
    mrp_res_absent = report_absent.by_id("LMPC-6-1-DA-MRP")
    assert mrp_res_absent is not None
    assert mrp_res_absent.status == ComplianceStatus.FAIL


def test_product_to_evidence_accepts_evidence_and_mapping():
    ev_in = Evidence()
    ev_in.set_field("custom_field", "custom_val")
    ev_out = product_to_evidence(ev_in)
    assert ev_out is ev_in

    mapping_in = {"product": {"name": "Test"}}
    ev_from_map = product_to_evidence(mapping_in)
    assert isinstance(ev_from_map, Evidence)
    assert ev_from_map.fields["product.name"].value == "Test"
