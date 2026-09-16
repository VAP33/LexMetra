"""
Integration tests against the live FastAPI app.

Require PostgreSQL reachable via DATABASE_URL. Skipped automatically when the
database is not available (see tests/conftest.py).
"""

from __future__ import annotations

from pathlib import Path

DATASET_IMAGE = (
    Path(__file__).resolve().parent.parent.parent
    / "dataset" / "images" / "prod001_compliant.png"
)


def test_health_endpoint(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_scan_without_auth_is_rejected(api_client):
    resp = api_client.post(
        "/scan",
        data={"product_id": "x", "net_quantity_value": "100", "net_quantity_unit": "g"},
    )
    assert resp.status_code == 401


def test_inspect_requires_auth(api_client):
    resp = api_client.post("/inspect", json={
        "inspection_id": "no-auth-test",
        "net_quantity_value": 100,
        "net_quantity_unit": "g",
        "fields": {},
    })
    assert resp.status_code == 401


def test_inspect_end_to_end_with_auth(api_client, inspector_token):
    resp = api_client.post(
        "/inspect",
        json={
            "inspection_id": "pytest-inspect-1",
            "sale_type": "retail",
            "product_category": "household",
            "net_quantity_value": 100,
            "net_quantity_unit": "g",
            "mrp": 50,
            "fields": {
                "manufacturer_name": {"value": "ACME Pvt Ltd, Pune", "confidence": 0.9},
                "common_name": {"value": "Detergent Powder", "confidence": 0.9},
                "net_quantity": {"value": "100 g", "confidence": 0.9},
                "consumer_care": {"value": "1800-000-000", "confidence": 0.9},
                "unit_sale_price": {"value": "Rs 50/100g", "confidence": 0.9},
            },
        },
        headers={"Authorization": f"Bearer {inspector_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["inspection_id"] == "pytest-inspect-1"
    assert body["overall_status"] in {"PASS", "UNCERTAIN", "FAIL", "EXEMPT"}


def test_reviewer_action_requires_reviewer_role(api_client, inspector_token):
    # An inspector-only account must not be able to mark reviews.
    resp = api_client.post(
        "/inspections/pytest-inspect-1/review",
        json={"note": "test"},
        headers={"Authorization": f"Bearer {inspector_token}"},
    )
    assert resp.status_code in {403, 404}


def test_scan_full_pipeline_with_real_image(api_client, admin_token):
    if not DATASET_IMAGE.exists():
        import pytest
        pytest.skip("Synthetic dataset image not present in this checkout.")

    with open(DATASET_IMAGE, "rb") as fh:
        resp = api_client.post(
            "/scan",
            files={"file": ("prod001_compliant.png", fh, "image/png")},
            data={
                "product_id": "pytest-prod-001",
                "sale_type": "retail",
                "product_category": "food",
                "net_quantity_value": "100",
                "net_quantity_unit": "g",
                "mrp": "50",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "inspection" in body
    assert body["inspection"]["overall_status"] in {"PASS", "UNCERTAIN", "FAIL", "EXEMPT"}

    inspection_id = body["inspection"]["inspection_id"]

    report_resp = api_client.get(
        f"/inspections/{inspection_id}/report.pdf",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert report_resp.status_code == 200
    assert report_resp.headers["content-type"] == "application/pdf"
    assert report_resp.content.startswith(b"%PDF")


def test_audit_log_requires_admin(api_client, inspector_token):
    resp = api_client.get(
        "/audit-log", headers={"Authorization": f"Bearer {inspector_token}"}
    )
    assert resp.status_code == 403


def test_multi_surface_session_end_to_end(api_client, admin_token):
    """
    Regression test for the JSONB double-decode bug: a session's per-capture
    OCR fields must survive being written to and read back from Postgres, be
    correctly merged/bridged, and drive a real PASS/FAIL/UNCERTAIN verdict at
    finalize() — not silently degrade to empty evidence.
    """
    if not DATASET_IMAGE.exists():
        import pytest
        pytest.skip("Synthetic dataset image not present in this checkout.")

    headers = {"Authorization": f"Bearer {admin_token}"}

    create_resp = api_client.post(
        "/sessions",
        json={
            "product_id": "pytest-session-001",
            "sale_type": "retail",
            "product_category": "food",
            "net_quantity_value": 100,
            "net_quantity_unit": "g",
            "mrp": 50,
        },
        headers=headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]

    with open(DATASET_IMAGE, "rb") as fh:
        capture_resp = api_client.post(
            f"/sessions/{session_id}/captures",
            files={"file": ("front.png", fh, "image/png")},
            data={"surface_type": "front"},
            headers=headers,
        )
    assert capture_resp.status_code == 200, capture_resp.text
    capture_body = capture_resp.json()
    # This is the field-bridge regression check: after the fix, a single
    # clean label photo should already report >0 coverage, not 0.0.
    assert capture_body["cumulative_coverage"] > 0.0

    status_resp = api_client.get(f"/sessions/{session_id}", headers=headers)
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    # Coverage read back from the DB must match what add_capture computed —
    # this is exactly what the JSONB double-decode bug broke (it silently
    # reset to 0.0 on read-back).
    assert status_body["cumulative_coverage"] == capture_body["cumulative_coverage"]

    finalize_resp = api_client.post(f"/sessions/{session_id}/finalize", headers=headers)
    assert finalize_resp.status_code == 200, finalize_resp.text
    inspection = finalize_resp.json()
    assert inspection["overall_status"] in {"PASS", "FAIL", "UNCERTAIN", "EXEMPT"}

    # At least one Rule 6 fact must have actually consumed the captured
    # evidence (PASS), proving the merged/bridged fields reached the engine
    # rather than finalizing against an empty extraction map.
    statuses = {f["field"]: f["status"] for f in inspection["facts"]}
    assert "PASS" in statuses.values(), statuses

    # Finalizing twice must be rejected, not silently re-run.
    second_finalize = api_client.post(f"/sessions/{session_id}/finalize", headers=headers)
    assert second_finalize.status_code == 409


def test_session_capture_requires_auth(api_client):
    resp = api_client.post("/sessions", json={
        "product_id": "no-auth", "net_quantity_value": 100, "net_quantity_unit": "g",
    })
    assert resp.status_code == 401


def test_finalize_empty_session_is_rejected(api_client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    create_resp = api_client.post(
        "/sessions",
        json={
            "product_id": "pytest-empty-session",
            "net_quantity_value": 100,
            "net_quantity_unit": "g",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]

    finalize_resp = api_client.post(f"/sessions/{session_id}/finalize", headers=headers)
    assert finalize_resp.status_code == 400
