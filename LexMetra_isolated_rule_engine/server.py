"""Standalone lightweight HTTP testing server and adapter for LexMetra ComplianceEngine.

Zero external dependencies: uses Python standard library http.server.
Serves the test UI and provides a JSON evaluation endpoint: POST /api/evaluate.
"""
from __future__ import annotations

import json
import os
import sys
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Ensure backend directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine import ComplianceEngine, load_ruleset
from engine.results import ComplianceStatus, RuleResult

DEFAULT_RULES_PATH = BASE_DIR / "rules" / "generic" / "lmpc_rules.json"
COMPLETE_RULES_PATH = BASE_DIR / "rules" / "generic" / "lmpc_complete_rules.json"


def format_rule_for_ui(r: RuleResult) -> Dict[str, Any]:
    """Extract and format engine outcome attributes for direct, accurate UI rendering."""
    trace = r.trace or {}
    stages = {
        s["stage"]: s["detail"]
        for s in trace.get("stages", [])
        if isinstance(s, dict) and "stage" in s
    }

    # Determine exemption decision strictly from trace / status
    ex_check = stages.get("exemption_check")
    if r.status is ComplianceStatus.EXEMPTED:
        exemption_decision = "EXEMPT"
    elif ex_check and isinstance(ex_check, dict):
        ex_res = ex_check.get("result")
        if ex_res == "TRUE":
            exemption_decision = "TRUE"
        elif ex_res == "FALSE":
            exemption_decision = "FALSE"
        else:
            exemption_decision = "UNKNOWN"
    elif r.applicability.value in ("NOT_APPLICABLE", "NOT_CONSIDERED"):
        exemption_decision = "—"
    else:
        if "exemption" in str(r.reason).lower():
            exemption_decision = "UNKNOWN"
        else:
            exemption_decision = "FALSE"

    # Determine compliance decision
    if r.status in (ComplianceStatus.PASS, ComplianceStatus.FAIL):
        compliance_decision = "TRUE" if r.status is ComplianceStatus.PASS else "FALSE"
    elif r.status is ComplianceStatus.UNCERTAIN:
        compliance_decision = "UNKNOWN"
    elif r.status is ComplianceStatus.EXEMPTED:
        compliance_decision = "—"
    elif r.status in (ComplianceStatus.NOT_APPLICABLE, ComplianceStatus.NOT_CONSIDERED):
        compliance_decision = "—"
    else:
        compliance_decision = "ERROR"

    evidence_citations = [e.to_dict() for e in r.evidence]

    return {
        "rule_id": r.rule_id,
        "rule_version": r.rule_version,
        "name": r.name,
        "provision": r.provision or "—",
        "legal_source": r.legal_source or "—",
        "rule_type": r.rule_type,
        "severity": r.severity,
        "priority": r.priority,
        "applicability": r.applicability.value,
        "applicability_reason": r.applicability_reason,
        "exemption": exemption_decision,
        "compliance": compliance_decision,
        "status": r.status.value,
        "reason": r.reason,
        "explanation": r.explanation,
        "missing_evidence": r.missing_evidence,
        "evidence": evidence_citations,
        "calculations": r.calculations,
        "dependencies": r.dependencies,
        "cross_references": r.cross_references,
        "review_required": r.review_required,
        "trace": r.trace,
        "error": r.error,
    }


def evaluate_product_payload(
    payload: Dict[str, Any],
    ruleset_type: str = "default",
) -> Dict[str, Any]:
    """Directly evaluate product JSON payload with ComplianceEngine."""
    if ruleset_type == "complete" and COMPLETE_RULES_PATH.exists():
        ruleset = load_ruleset(COMPLETE_RULES_PATH)
        engine = ComplianceEngine(ruleset=ruleset)
    else:
        engine = ComplianceEngine()

    product_input = payload.get("product", payload)
    context = payload.get("context")

    report = engine.evaluate(product_input, context=context)

    # Transform report into UI-friendly JSON preserving raw engine structures
    formatted_rules = [format_rule_for_ui(r) for r in report.results]

    raw_report_dict = report.to_dict()

    return {
        "overall_status": report.aggregation.overall_status.value,
        "overall_reason": report.aggregation.reason,
        "policy": report.aggregation.policy,
        "counts": report.aggregation.counts,
        "critical_failures": report.aggregation.critical_failures,
        "total_rules": len(report.results),
        "ruleset_id": report.ruleset_id,
        "ruleset_version": report.ruleset_version,
        "rules": formatted_rules,
        "raw_engine_result": raw_report_dict,
    }


class LexMetraUIRequestHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving UI static files and /api/evaluate endpoint."""

    def __init__(self, *args, directory=None, **kwargs):
        ui_dir = str(BASE_DIR / "ui")
        super().__init__(*args, directory=ui_dir, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "healthy", "service": "lexmetra-test-ui"}')
            return

        # Default static file serving from ui/ directory
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/evaluate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
                ruleset_choice = payload.get("_ruleset", "default")
                result = evaluate_product_payload(payload, ruleset_type=ruleset_choice)

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(result, indent=2).encode("utf-8"))
            except Exception as e:
                self.send_response(HTTPStatus.BAD_REQUEST)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                err_data = {"error": str(e), "status": "ENGINE_ERROR"}
                self.wfile.write(json.dumps(err_data).encode("utf-8"))
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()


def run_server(port: int = 8080, host: str = "127.0.0.1") -> None:
    """Run local UI server."""
    server_address = (host, port)
    httpd = HTTPServer(server_address, LexMetraUIRequestHandler)
    print(f"============================================================")
    print(f" LexMetra Rule Engine Test UI Server")
    print(f" Serving at: http://{host}:{port}/")
    print(f" Press Ctrl+C to stop.")
    print(f"============================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping LexMetra UI server...")
        httpd.server_close()


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port=port_arg)
