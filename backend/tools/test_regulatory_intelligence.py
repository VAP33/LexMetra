"""End-to-end test for Regulatory Intelligence & Versioned Rule Management."""

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_regulatory_workflow():
    print("=== Testing Regulatory Intelligence Workflow ===")

    # 1. GET active version
    res = client.get("/regulatory/active-version")
    assert res.status_code == 200, f"Failed GET active-version: {res.text}"
    active_ver = res.json()
    print(f"[OK] Active Version: {active_ver['version_id']} ({active_ver['status']}), Rules: {active_ver['rule_count']}")
    assert active_ver["version_id"] == "LM-2026.01"
    assert active_ver["status"] == "ACTIVE"

    # 2. Upload sample Gazette Amendment
    sample_text = (
        "MINISTRY OF CONSUMER AFFAIRS, FOOD AND PUBLIC DISTRIBUTION\n"
        "NOTIFICATION\n"
        "New Delhi, the 12th September, 2026\n"
        "G.S.R. 892(E).—In exercise of powers under the Legal Metrology Act, 2009...\n"
        "1. Rule 6(12): Machine-readable dynamic QR code for e-commerce packages.\n"
        "2. Rule 6(11): Minimum font height of USP >= 50% of MRP font height.\n"
        "3. Rule 26(a): Exemption clause III for fortified food packages below 10g is repealed."
    )
    files = {"file": ("Gazette_Notification_2026.pdf", sample_text.encode("utf-8"), "application/pdf")}
    res = client.post("/regulatory/upload-amendment", files=files)
    assert res.status_code == 200, f"Failed upload-amendment: {res.text}"
    proposal = res.json()
    proposal_id = proposal["proposal_id"]
    deltas = proposal["delta_changes"]
    print(f"[OK] Uploaded Gazette Amendment -> Proposal {proposal_id}")
    print(f"     Target Version: {proposal['target_version_id']}")
    print(f"     Extracted Deltas: {len(deltas)} ({[d['type'] for d in deltas]})")
    assert len(deltas) == 3
    assert {d["type"] for d in deltas} == {"NEW", "CHANGE", "DELETE"}

    # 3. Review proposal (Approve all deltas)
    for d in deltas:
        d["status"] = "APPROVED"
    res = client.post(f"/regulatory/proposals/{proposal_id}/review", json={"reviewed_deltas": deltas})
    assert res.status_code == 200, f"Failed review proposal: {res.text}"
    reviewed = res.json()
    assert reviewed["status"] == "APPROVED"
    print(f"[OK] Reviewed Proposal {proposal_id} -> Status: APPROVED")

    # 4. Request 6-digit challenge code
    res = client.post(f"/regulatory/proposals/{proposal_id}/request-auth")
    assert res.status_code == 200, f"Failed request-auth: {res.text}"
    auth_data = res.json()
    auth_code = auth_data["auth_code_hint"]
    print(f"[OK] Generated 6-Digit Challenge Code: {auth_code}")
    assert len(auth_code) == 6

    # 5. Publish amendment with auth code
    res = client.post(f"/regulatory/proposals/{proposal_id}/publish", json={"auth_code": auth_code})
    assert res.status_code == 200, f"Failed publish proposal: {res.text}"
    publish_result = res.json()
    new_ver = publish_result["new_version"]
    print(f"[OK] Published New Immutable Version: {new_ver['version_id']} ({new_ver['status']})")
    assert new_ver["version_id"] == "LM-2026.02"
    assert new_ver["status"] == "ACTIVE"

    # 6. Verify version list and superseding
    res = client.get("/regulatory/versions")
    assert res.status_code == 200
    versions = res.json()["versions"]
    print(f"[OK] Version Registry contains {len(versions)} versions:")
    for v in versions:
        print(f"     - {v['version_id']}: {v['status']} (Rules: {v['rule_count']})")

    active_versions = [v for v in versions if v["status"] == "ACTIVE"]
    superseded_versions = [v for v in versions if v["status"] == "SUPERSEDED"]
    assert len(active_versions) == 1
    assert active_versions[0]["version_id"] == "LM-2026.02"
    assert any(v["version_id"] == "LM-2026.01" for v in superseded_versions)

    print("\nALL REGULATORY INTELLIGENCE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_regulatory_workflow()
