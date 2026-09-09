#!/usr/bin/env python3
"""
Standalone Live Demo Server for Legal Metrology (LMPC) Compliance Platform.
"""

from __future__ import annotations

import cgi
import json
import os
import sys
import time
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_BACKEND = Path(__file__).resolve().parent
_ROOT = _BACKEND.parent
for _p in (str(_BACKEND), str(_BACKEND / "tools"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import pydantic  # noqa: F401
except ModuleNotFoundError:
    import pydantic_shim
    pydantic_shim.install()

import capture_session
import rule_engine
from schema import (
    BBox,
    CalibrationInfo,
    CalibrationMethod,
    FactStatus,
    GeometryType,
    MeasurementMode,
    SurfaceObservation,
)
import report

DEFAULT_PORT = 8000
IN_MEMORY_INSPECTIONS: list[dict] = []
IN_MEMORY_AUDIT: list[dict] = []


def _generate_demo_token(username: str = "inspector_demo") -> str:
    return f"demo-jwt-token-{username}-{int(time.time())}"


class DemoHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def _send_json(self, data: dict | list, status: int = 200) -> None:
        raw = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/dashboard", "/dashboard.html"):
            dashboard_file = _ROOT / "frontend" / "dashboard.html"
            content = dashboard_file.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path in ("/capture", "/capture.html"):
            capture_file = _ROOT / "frontend" / "capture.html"
            content = capture_file.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/health":
            self._send_json({"status": "ok", "mode": "demo_live_server", "version": "2.0-unified"})
            return

        if path == "/inspections":
            query = parse_qs(parsed.query)
            needs_review = query.get("needs_review", ["false"])[0].lower() == "true"
            items = IN_MEMORY_INSPECTIONS
            if needs_review:
                items = [i for i in items if i.get("review_required") and not i.get("reviewed")]
            summary_list = [
                {
                    "inspection_id": i["inspection_id"],
                    "product_id": i.get("product_id", "DEMO-PROD"),
                    "overall_status": i["overall_status"],
                    "mrp": i.get("mrp"),
                    "created_at": i.get("created_at"),
                    "reviewed": i.get("reviewed", False),
                }
                for i in items
            ]
            self._send_json(summary_list)
            return

        if path.startswith("/inspections/") and path.endswith("/report.pdf"):
            insp_id = path.split("/")[2]
            found = next((i for i in IN_MEMORY_INSPECTIONS if i["inspection_id"] == insp_id), None)
            if not found:
                self._send_json({"detail": "Inspection not found"}, 404)
                return
            pdf_bytes = report.generate_inspection_report(found["inspection_object"])
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'attachment; filename="report_{insp_id}.pdf"')
            self.send_header("Content-Length", str(len(pdf_bytes)))
            self.end_headers()
            self.wfile.write(pdf_bytes)
            return

        if path.startswith("/inspections/"):
            insp_id = path.split("/")[2]
            found = next((i for i in IN_MEMORY_INSPECTIONS if i["inspection_id"] == insp_id), None)
            if not found:
                self._send_json({"detail": "Inspection not found"}, 404)
                return
            self._send_json(found)
            return

        self._send_json({"detail": f"Path '{path}' not found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/auth/login", "/auth/login/"):
            token = _generate_demo_token("inspector")
            self._send_json({
                "access_token": token,
                "token_type": "bearer",
                "username": "inspector_demo",
                "role": "admin",
            })
            return

        if path in ("/scan", "/scan/"):
            ctype, pdict = cgi.parse_header(self.headers.get("Content-Type", ""))
            fields = {}
            filename = f"scan_{uuid.uuid4().hex[:8]}.jpg"
            if ctype == "multipart/form-data":
                pdict["boundary"] = bytes(pdict["boundary"], "utf-8")
                parsed_data = cgi.parse_multipart(self.rfile, pdict)
                for k, v in parsed_data.items():
                    if k == "file":
                        continue
                    fields[k] = v[0].decode("utf-8") if isinstance(v[0], bytes) else str(v[0])
            else:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                fields = {k: v[0] for k, v in parse_qs(body).items()}

            product_id = fields.get("product_id", "DEMO-PROD-001")
            sale_type = fields.get("sale_type", "retail")
            product_category = fields.get("product_category", "food")
            net_qty = float(fields.get("net_quantity_value", 100.0))
            net_unit = fields.get("net_quantity_unit", "g")
            mrp = float(fields.get("mrp", 50.0)) if fields.get("mrp") else None
            pdp_area = float(fields.get("pdp_area_cm2", 45.0)) if fields.get("pdp_area_cm2") else None

            # Build synthetic/OCR-like observation fields
            classified = {
                "mrp": {
                    "value": f"MRP Rs {mrp:.2f}" if mrp else "MRP Rs 50.00",
                    "confidence": 0.92,
                    "bbox": (120, 640, 300, 28),
                    "numeric_value": mrp or 50.0,
                },
                "net_quantity": {
                    "value": f"Net Wt {net_qty:g} {net_unit}",
                    "confidence": 0.89,
                    "bbox": (118, 600, 210, 26),
                    "numeric_value": net_qty,
                    "numeric_unit": net_unit,
                },
                "manufacturer_name": {
                    "value": "Acme Consumer Products Ltd, Mumbai 400001",
                    "confidence": 0.85,
                    "bbox": (115, 700, 420, 52),
                },
                "common_name": {
                    "value": "Refined Edible Commodity",
                    "confidence": 0.88,
                    "bbox": (115, 450, 350, 30),
                },
                "mfg_date": {
                    "value": "08/2026",
                    "confidence": 0.82,
                    "bbox": (118, 560, 190, 24),
                },
                "consumer_care": {
                    "value": "care@acme.in | 1800-222-333",
                    "confidence": 0.80,
                    "bbox": (115, 760, 380, 25),
                },
            }

            classified = capture_session.stamp_provenance(classified, image_id=filename, surface_id="surf-01")
            bridged = capture_session.bridge_classified_fields(classified)
            extractions = {
                field: capture_session.build_raw_extraction(field, data)
                for field, data in bridged.items()
            }

            inspection_id = f"{product_id}:scan-{uuid.uuid4().hex[:8]}"
            res = rule_engine.run_inspection(
                inspection_id=inspection_id,
                sale_type=sale_type,
                product_category=product_category,
                net_quantity_value=net_qty,
                net_quantity_unit=net_unit,
                mrp=mrp,
                extractions=extractions,
                pdp_area_cm2=pdp_area,
                is_imported=False,
                dimensions_relevant=False,
                best_before_applicable=False,
            )

            res_dict = json.loads(res.model_dump_json())
            record = {
                "inspection_id": inspection_id,
                "product_id": product_id,
                "sale_type": sale_type,
                "overall_status": res.overall_status.value,
                "mrp": mrp,
                "facts": res_dict.get("facts", []),
                "findings": res_dict.get("findings", []),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "reviewed": False,
                "review_required": res.review_required,
                "reviewer_note": None,
                "inspection_object": res,
            }
            IN_MEMORY_INSPECTIONS.insert(0, record)

            response_payload = {
                "inspection": res_dict,
                "raw_ocr_lines": [
                    {"text": d["value"], "bbox": d.get("bbox"), "confidence": d["confidence"]}
                    for d in classified.values() if isinstance(d, dict) and "value" in d
                ],
                "raw_ocr_fields": classified,
                "resolved_inputs": {"mrp": mrp, "quantity_value": net_qty, "quantity_unit": net_unit},
                "sticker_suspects": [],
                "nearest_matches": [
                    {"product_id": "PREV-BATCH-101", "image_id": "ref001.jpg", "score": 0.94}
                ],
                "price_or_label_change_flag": None,
            }
            self._send_json(response_payload)
            return

        if path.startswith("/inspections/") and path.endswith("/review"):
            insp_id = path.split("/")[2]
            found = next((i for i in IN_MEMORY_INSPECTIONS if i["inspection_id"] == insp_id), None)
            if not found:
                self._send_json({"detail": "Inspection not found"}, 404)
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body) if body else {}
            found["reviewed"] = True
            found["reviewer_note"] = data.get("note", "Reviewed and verified")
            self._send_json({"status": "ok", "inspection_id": insp_id, "reviewed": True})
            return

        self._send_json({"detail": f"Cannot POST to {path}"}, 404)


def run_server(port: int = DEFAULT_PORT) -> None:
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, DemoHandler)
    print(f"\n========================================================")
    print(f"  LMPC Legal Metrology Compliance - Live Demo Server")
    print(f"========================================================")
    print(f"  * Dashboard:  http://localhost:{port}/")
    print(f"  * Calibrated: http://localhost:{port}/capture")
    print(f"  * Health API: http://localhost:{port}/health")
    print(f"========================================================\n", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()


if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    run_server(p)
