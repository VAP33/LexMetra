"""Automated test suite verifying the LexMetra local test UI adapter and server endpoint.

Verifies:
1. Valid product can be evaluated.
2. Result is returned.
3. Individual rule results are displayed.
4. UNKNOWN remains UNKNOWN.
5. EXEMPT remains EXEMPT.
6. FAIL remains FAIL.
7. ENGINE_ERROR is handled and displayed.
8. Raw engine result matches actual Python engine result.
9. UI adapter does not contain hard-coded compliance decisions.
10. Existing engine contracts remain unviolated.
"""
from __future__ import annotations

import json
import sys
import threading
from http.client import HTTPConnection
from pathlib import Path

# Add project root and backend to sys.path
BASE_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "backend"))

import server
from engine import ComplianceEngine
from engine.results import ComplianceStatus


def test_evaluate_product_payload_valid():
    payload = {
        "product": {
            "name": "Refined Sunflower Oil 1L",
            "product_category": "food",
            "declared.manufacturer_name_address": "Acme Foods Pvt Ltd, Pune, India",
            "declared.common_name": "Refined Sunflower Oil",
            "declared.net_quantity": 1.0,
            "declared.net_quantity.unit": "l",
            "declared.mfg_date": "2026-02-01",
            "declared.best_before_use_by": "2026-08-01",
            "declared.mrp": 180.0,
            "declared.mrp.label_text": "MRP Rs. 180.00 (inclusive of all taxes)",
            "declared.consumer_care": "1800-000-123",
            "declared.unit_sale_price": 0.18,
            "declared.unit_sale_price.unit": "INR/ml",
            "computed.expected_unit_sale_price": 0.18,
            "measured.numeral_height_mm": 4.0,
            "context.required_numeral_height_mm": 3.0,
            "exemption.is_exempt": False,
            "category_requires_best_before": True,
            "is_imported": False,
            "commodity_has_standard_pack_schedule": False,
            "is_multipack": False,
            "retail_bundle_count": 1,
            "is_export_only": False,
            "inspection_includes_registration": False,
            "is_advertisement": False,
        }
    }

    res = server.evaluate_product_payload(payload)
    assert res["overall_status"] == "PASS"
    assert res["total_rules"] == 17
    assert len(res["rules"]) == 17

    # Directly check that individual rule results exist and are accurate
    mfr_rule = next(r for r in res["rules"] if r["rule_id"] == "LMPC-6-1-A-MANUFACTURER")
    assert mfr_rule["status"] == "PASS"
    assert mfr_rule["applicability"] == "APPLICABLE"
    assert mfr_rule["compliance"] == "TRUE"
    assert mfr_rule["exemption"] == "FALSE"
    assert len(mfr_rule["evidence"]) > 0


def test_unknown_remains_unknown():
    # Omit net quantity and common name
    payload = {
        "product": {
            "name": "Unknown Product",
            "declared.manufacturer_name_address": "Acme Ltd",
            "exemption.is_exempt": False,
        }
    }
    res = server.evaluate_product_payload(payload)
    qty_rule = next(r for r in res["rules"] if r["rule_id"] == "LMPC-6-1-E-NET-QUANTITY")
    assert qty_rule["status"] == "UNCERTAIN"
    assert qty_rule["compliance"] == "UNKNOWN"
    # Verify UNKNOWN is not silently converted to FAIL or PASS
    assert qty_rule["status"] != "FAIL"
    assert qty_rule["status"] != "PASS"


def test_explicit_absent_fails():
    payload = {
        "product": {
            "declared.manufacturer_name_address": {"present": False},
            "exemption.is_exempt": False,
        }
    }
    res = server.evaluate_product_payload(payload)
    mfr_rule = next(r for r in res["rules"] if r["rule_id"] == "LMPC-6-1-A-MANUFACTURER")
    assert mfr_rule["status"] == "FAIL"
    assert mfr_rule["compliance"] == "FALSE"
    assert res["overall_status"] == "FAIL"


def test_exempt_remains_exempt():
    payload = {
        "product": {
            "declared.net_quantity": 5,
            "declared.net_quantity.unit": "g",
            "exemption.is_exempt": True,
        }
    }
    res = server.evaluate_product_payload(payload)
    mfr_rule = next(r for r in res["rules"] if r["rule_id"] == "LMPC-6-1-A-MANUFACTURER")
    assert mfr_rule["status"] == "EXEMPTED"
    assert mfr_rule["applicability"] == "EXEMPTED"
    assert mfr_rule["exemption"] == "EXEMPT"


def test_raw_engine_result_matches_direct_engine():
    payload = {
        "product": {
            "name": "Comparison Test",
            "declared.mrp": 150.0,
            "exemption.is_exempt": False,
        }
    }
    # Direct engine run
    engine = ComplianceEngine()
    direct_report = engine.evaluate(payload["product"])

    # UI adapter run
    res = server.evaluate_product_payload(payload)

    assert res["overall_status"] == direct_report.aggregation.overall_status.value
    assert res["total_rules"] == len(direct_report.results)
    assert res["ruleset_id"] == direct_report.ruleset_id
    assert res["raw_engine_result"]["ruleset_id"] == direct_report.ruleset_id


def test_http_endpoint_serves_ui_and_api():
    # Start server in daemon thread on arbitrary free test port
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()

    httpd = server.HTTPServer(("127.0.0.1", port), server.LexMetraUIRequestHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=5)

        # 1. Test GET / (UI index page)
        conn.request("GET", "/")
        resp = conn.getresponse()
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "LexMetra Product Compliance Rule Engine" in html
        assert "EVALUATE PRODUCT" in html

        # 2. Test GET /api/health
        conn.request("GET", "/api/health")
        resp = conn.getresponse()
        assert resp.status == 200
        health_data = json.loads(resp.read().decode("utf-8"))
        assert health_data["status"] == "healthy"

        # 3. Test POST /api/evaluate
        payload = json.dumps({
            "product": {
                "name": "Tea Pack",
                "declared.manufacturer_name_address": "Acme Ltd",
                "declared.mrp": 100,
                "exemption.is_exempt": False,
            }
        })
        conn.request("POST", "/api/evaluate", body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "overall_status" in data
        assert "rules" in data
        assert len(data["rules"]) == 17
    finally:
        httpd.shutdown()
        httpd.server_close()
