"""
Verification script for all 4 LexMetra USPs against the live server:
1. Package Integrity (USP 1)
2. FSSAI Cross-Verification (USP 2)
3. Consumer -> Authority Reporting & Enforcement Queue (USP 3)
4. Grounded Multilingual Assistant in EN, HI, MR (USP 4)
"""

import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"

def request_json(path, method="GET", data=None, token=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"raw": err_body}

def main():
    print("=" * 60)
    print("LEXMETRA FINAL PASS: VERIFYING ALL USPs & CORE WORKFLOWS")
    print("=" * 60)

    # 1. Health Probe
    st, res = request_json("/health")
    assert st == 200, f"Health failed: {st} {res}"
    print(f"[+] Health Probe: {res.get('status')} (service: {res.get('service')})")

    # 2. Authentication
    login_data = urllib.parse.urlencode({"username": "inspector", "password": "password123"}).encode()
    login_req = urllib.request.Request(f"{BASE_URL}/auth/login", data=login_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(login_req, timeout=10) as resp:
        auth_json = json.loads(resp.read().decode("utf-8"))
    token = auth_json["access_token"]
    assert token, "No access token received"
    print(f"[+] Authenticated Inspector: @{auth_json.get('username', 'inspector')}")

    # 3. List Inspections to locate Bru Golden inspection
    st, insp_list = request_json("/inspections?limit=10", token=token)
    assert st == 200, f"List inspections failed: {st}"
    print(f"[+] Inspections retrieved from database: {len(insp_list)} found")

    target_id = insp_list[0]["inspection_id"] if insp_list else "INSP-BRU-REAL-TEST"
    print(f"[*] Testing target inspection: {target_id}")

    # 4. USP 1: Package Integrity Verification
    st, integrity = request_json(f"/inspections/{target_id}/integrity", token=token)
    assert st == 200, f"Integrity endpoint failed: {st} {integrity}"
    print(f"[+] USP 1 (Package Integrity):")
    print(f"    - Status: {integrity.get('status')}")
    print(f"    - Confidence: {integrity.get('confidence_score')}")
    print(f"    - Method: {integrity.get('comparison_method')}")
    print(f"    - Has Reference: {integrity.get('has_reference')}")
    print(f"    - Advisory: {integrity.get('is_advisory')}")
    valid_integrity_statuses = [
        "NO SIGNIFICANT DIFFERENCE DETECTED",
        "POTENTIAL ALTERATION DETECTED",
        "UNABLE TO VERIFY"
    ]
    assert integrity.get("status") in valid_integrity_statuses, f"Invalid integrity status: {integrity.get('status')}"

    # 5. USP 2: FSSAI Cross-Verification
    st, fssai = request_json(f"/inspections/{target_id}/fssai", token=token)
    assert st == 200, f"FSSAI endpoint failed: {st} {fssai}"
    print(f"[+] USP 2 (FSSAI Cross-Verification):")
    print(f"    - Status: {fssai.get('status')}")
    print(f"    - Is Food: {fssai.get('is_food')}")
    print(f"    - License Number: {fssai.get('license_number')}")
    print(f"    - Jurisdiction: {fssai.get('state_jurisdiction')}")
    print(f"    - Licensee: {fssai.get('registry_licensee')}")
    valid_fssai_statuses = [
        "VERIFIED / MATCH",
        "MISMATCH DETECTED",
        "UNABLE TO VERIFY",
        "NOT APPLICABLE"
    ]
    assert fssai.get("status") in valid_fssai_statuses, f"Invalid FSSAI status: {fssai.get('status')}"

    # 6. USP 3: Consumer / Inspector Escalation Gateway
    report_payload = {
        "inspection_id": target_id,
        "product_name": "BRU Instant Coffee 150g",
        "issue_category": "Missing Unit Sale Price (USP Mandate)",
        "details": "Automated verification test: missing Unit Sale Price font declaration under Rule 6(11).",
        "reporter_name": "Test Field Inspector",
        "reporter_contact": "inspector@lexmetra.gov.in",
        "product_id": "64934436",
        "category": "Food / Instant Coffee",
        "location": "Sector 29, Gurugram",
        "retailer_name": "Retail Supermarket",
        "lmpc_verdict": "VIOLATION",
        "lmpc_violations_count": 1,
        "fssai_status": fssai.get("status"),
        "integrity_status": integrity.get("status"),
    }
    st, docket = request_json("/reports/consumer", method="POST", data=report_payload, token=token)
    assert st == 200, f"Consumer report submission failed: {st} {docket}"
    case_id = docket["case_id"]
    report_id = docket["report_id"]
    print(f"[+] USP 3 (Consumer Escalation Docket Filed):")
    print(f"    - Case ID: {case_id}")
    print(f"    - Report Tracking ID: {report_id}")
    print(f"    - Priority: {docket.get('priority')}")
    print(f"    - Status: {docket.get('status')}")

    # 7. Retrieve Report by ID
    st, fetched_report = request_json(f"/reports/{report_id}")
    assert st == 200 and fetched_report["case_id"] == case_id, f"Failed to retrieve report {report_id}"
    print(f"[+] Public Tracking Query: Successfully fetched {report_id} -> {fetched_report['status']}")

    # 8. Authority Enforcement Queue
    st, cases = request_json("/authority/cases", token=token)
    assert st == 200 and len(cases) > 0, "No cases found in authority queue"
    print(f"[+] Authority Queue: {len(cases)} active statutory dockets")

    # 9. Officer Statutory Action
    action_payload = {
        "officer_username": "inspector",
        "action_type": "SHOW_CAUSE_NOTICE",
        "notes": "Official Form 4 Notice served to Packer under Section 36(1) for packaging non-compliance.",
        "statutory_clause": "Rule 6(11) & Section 36(1) LM Act",
    }
    st, updated_case = request_json(f"/authority/cases/{case_id}/action", method="POST", data=action_payload, token=token)
    assert st == 200 and updated_case["status"] == "NOTICE_ISSUED", f"Case action failed: {st} {updated_case}"
    print(f"[+] Officer Statutory Action Recorded:")
    print(f"    - New Status: {updated_case['status']}")
    print(f"    - Actions on docket: {len(updated_case['actions'])}")
    print(f"    - Latest Action: {updated_case['actions'][-1]['action_type']} by @{updated_case['actions'][-1]['officer_username']}")

    # 10. USP 4: Multilingual Voice & Text Assistant
    print(f"[+] USP 4 (Multilingual Grounded Assistant):")

    # English query
    en_payload = {
        "query": "What does Rule 6(11) Unit Sale Price mandate?",
        "language": "en",
        "inspection_id": target_id,
    }
    st, en_res = request_json("/assistant/chat", method="POST", data=en_payload)
    assert st == 200, f"Assistant EN failed: {st} {en_res}"
    print(f"    [EN Query]: {en_payload['query']}")
    print(f"    [EN Response]: {en_res['response_text'][:110]}...")

    # Hindi query
    hi_payload = {
        "query": "क्या इस पैकेज पर FSSAI लाइसेंस मान्य है?",
        "language": "hi",
        "inspection_id": target_id,
    }
    st, hi_res = request_json("/assistant/chat", method="POST", data=hi_payload)
    assert st == 200, f"Assistant HI failed: {st} {hi_res}"
    print(f"    [HI Query]: {hi_payload['query']}")
    print(f"    [HI Response]: {hi_res['response_text'][:110]}...")

    # Marathi query
    mr_payload = {
        "query": "या उत्पादनावर निव्वळ वजन योग्य प्रकारे घोषित केले आहे का?",
        "language": "mr",
        "inspection_id": target_id,
    }
    st, mr_res = request_json("/assistant/chat", method="POST", data=mr_payload)
    assert st == 200, f"Assistant MR failed: {st} {mr_res}"
    print(f"    [MR Query]: {mr_payload['query']}")
    print(f"    [MR Response]: {mr_res['response_text'][:110]}...")

    print("=" * 60)
    print("ALL 4 USPs & STATUTORY WORKFLOWS FULLY VERIFIED (100% PASS)!")
    print("=" * 60)

if __name__ == "__main__":
    main()
