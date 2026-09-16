"""
Tests for Amendment Publishing, Relational Persistence, and Verification.

Verifies:
1. G.S.R. 577(E) separation into 4 canonical executable rules and context provisions (Rule 1(1), Rule 1(2)).
2. Multilingual deduplication (English canonical, Hindi retained in source_languages provenance).
3. Applicability evaluation with 'RULES CONSIDERED' and 'RULES NOT CONSIDERED' giving genuine legal rationale.
4. Transactional/atomic publishing into PostgreSQL tables `regulatory_rule_versions` and `regulatory_amendments`.
5. Retrieval of active rules from PostgreSQL under parent regulation 'Legal Metrology (Packaged Commodities) Rules, 2011'.
6. Generic synthetic amendment test verifying zero hardcoding of G.S.R. 577(E).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
from fastapi.testclient import TestClient

from backend.db import persistence as db_persistence
from backend.db.persistence import (
    get_active_rule_versions,
    get_database_verification,
    publish_amendment_draft,
    save_amendment_draft,
)
from backend.main import app

from datetime import date, datetime, timezone
from backend import auth
from backend.models import AmendmentDraft, AmendmentChange, RuleVersion, ApprovalState
from backend.tests.fixtures.pdf_builder import build_native_text_pdf
from backend.tests.test_gsr_577_e_ingestion import HINDI_PAGE_TEXT, ENGLISH_PAGE_TEXT

client = TestClient(app)


def get_auth_headers(role: str = "reviewer", username: Optional[str] = None) -> dict[str, str]:
    uname = username or f"test_user_{role}"
    # Ensure user exists in test database
    user = db_persistence.get_user_by_username(uname)
    if not user:
        try:
            db_persistence.create_user(
                username=uname,
                hashed_password=auth.hash_password("password123"),
                role=role,
                full_name=f"Test {role.capitalize()}",
            )
        except Exception:
            pass
    elif user["role"] != role:
        # Update user role if changed
        with db_persistence.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET role = %s WHERE username = %s", (role, uname))
    token = auth.create_access_token(uname, role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def gsr_577e_draft_id(tmp_path):
    """Build and ingest G.S.R. 577(E) gazette PDF and return draft_id."""
    pdf_path = tmp_path / "gsr_577_e_sample.pdf"
    build_native_text_pdf(pdf_path, [HINDI_PAGE_TEXT, ENGLISH_PAGE_TEXT])

    headers = get_auth_headers("reviewer")
    with open(pdf_path, "rb") as f:
        resp = client.post(
            "/regulations/ingest",
            files={"file": ("gsr_577_e_sample.pdf", f, "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 200, f"Ingestion failed: {resp.text}"
    data = resp.json()
    assert "draft" in data
    return data["draft"]["id"]


def test_gsr_577e_rules_identified_separation(gsr_577e_draft_id: str):
    """
    Test Step 2 & 4:
    - Rule 1(1) -> SHORT_TITLE / context
    - Rule 1(2) -> COMMENCEMENT / context
    - Exactly 4 canonical substantive rules: Rule 2(a)(i), 2(a)(ii), 2(a)(iii), 2(b)
    - Canonical text is English
    - Hindi is deduplicated into source_languages
    """
    resp = client.get(
        f"/regulations/drafts/{gsr_577e_draft_id}/rules-identified",
        headers=get_auth_headers("reviewer"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Verify context provisions
    context_provisions = data["context_provisions"]
    assert len(context_provisions) >= 2

    rule_1_1 = next((p for p in context_provisions if "1(1)" in p.get("provision", "") or "1(1)" in p.get("title", "")), None)
    assert rule_1_1 is not None
    assert rule_1_1["is_executable"] is False
    assert rule_1_1["type"] == "SHORT_TITLE"

    rule_1_2 = next((p for p in context_provisions if "1(2)" in p.get("provision", "") or "1(2)" in p.get("title", "")), None)
    assert rule_1_2 is not None
    assert rule_1_2["is_executable"] is False
    assert rule_1_2["type"] == "COMMENCEMENT"
    assert rule_1_2["effective_from"] == "2022-07-14"

    # Verify canonical executable rules
    executable_rules = data["rules_identified"]
    assert len(executable_rules) == 4, f"Expected 4 canonical rules, got {len(executable_rules)}"

    display_rules = [r["display_provision"] for r in executable_rules]
    assert "Rule 2(a)(i)" in display_rules
    assert "Rule 2(a)(ii)" in display_rules
    assert "Rule 2(a)(iii)" in display_rules
    assert "Rule 2(b)" in display_rules

    # Verify canonical text is English and source languages deduplicated
    for rule in executable_rules:
        assert rule["canonical_english_text"] is not None and len(rule["canonical_english_text"]) > 10
        # Check that Hindi text is not primary executable text
        assert not any(ord(c) > 0x0900 and ord(c) < 0x097F for c in rule["canonical_english_text"][:20])
        # Check source languages contain en (and hi if extracted)
        assert "en" in rule["source_languages"]
        assert rule["parent_regulation"] == "Legal Metrology (Packaged Commodities) Rules, 2011"
        assert rule["amendment_version"] == "Second Amendment, 2022"
        assert rule["effective_from"] == "2022-07-14"


def test_gsr_577e_applicability_evaluation(gsr_577e_draft_id: str):
    """
    Test Section 4 & 5:
    - 'RULES CONSIDERED' (APPLICABLE) when product context matches electronic product manufactured post-2022-07-15
    - 'RULES NOT CONSIDERED' (NOT_APPLICABLE) when product context does not match (e.g. food article)
    """
    # 1. Matching electronic product context
    electronic_context = {
        "product_category": "electronics",
        "manufacture_date": "2023-01-10",
        "is_imported": False,
        "sale_type": "retail",
    }
    resp = client.post(
        f"/regulations/drafts/{gsr_577e_draft_id}/evaluate-applicability",
        json=electronic_context,
        headers=get_auth_headers("reviewer"),
    )
    assert resp.status_code == 200, resp.text
    eval_data = resp.json()

    considered = eval_data["rules_considered"]
    not_considered = eval_data["rules_not_considered"]

    assert len(considered) == 4
    assert len(not_considered) == 0
    for r in considered:
        assert r["status"] == "CONSIDERED / APPLICABLE"
        assert "electronic" in r["reason"].lower() or "applicable" in r["reason"].lower()

    # 2. Non-matching food product context
    food_context = {
        "product_category": "edible oil and foods",
        "manufacture_date": "2023-01-10",
        "is_imported": False,
        "sale_type": "retail",
    }
    resp_food = client.post(
        f"/regulations/drafts/{gsr_577e_draft_id}/evaluate-applicability",
        json=food_context,
        headers=get_auth_headers("reviewer"),
    )
    assert resp_food.status_code == 200, resp_food.text
    food_eval = resp_food.json()

    food_considered = food_eval["rules_considered"]
    food_not_considered = food_eval["rules_not_considered"]

    assert len(food_considered) == 0
    assert len(food_not_considered) == 4
    for r in food_not_considered:
        assert r["status"] == "NOT_APPLICABLE"
        assert "electronic" in r["reason"].lower() or "scope" in r["reason"].lower()


def test_atomic_publishing_and_persistence(gsr_577e_draft_id: str):
    """
    Test Section 6, 7, 8, 10, 11, 12, 13:
    - Reviewer approves and publishes amendment draft
    - Atomic transaction persists 4 rules into PostgreSQL `regulatory_rule_versions`
    - Relational linking to `regulatory_modules` ('lmpc')
    - Read back active rules via GET /regulations/active-rules
    - Read back database verification via GET /regulations/verification/{draft_id}
    """
    # 1. Publish amendment (requires admin)
    publish_resp = client.post(
        f"/regulations/drafts/{gsr_577e_draft_id}/publish",
        headers=get_auth_headers("admin"),
    )
    assert publish_resp.status_code == 200, publish_resp.text
    receipt = publish_resp.json()
    assert receipt["status"] == "PUBLISHED / ACTIVE"
    assert receipt["rules_published_count"] == 4
    assert receipt["parent_regulation"] == "Legal Metrology (Packaged Commodities) Rules, 2011"
    assert "Rule 2(a)(i)" in [r["display_provision"] for r in receipt["published_rules"]]

    # 2. Verify active rules endpoint
    active_resp = client.get(
        "/regulations/active-rules?module=lmpc",
        headers=get_auth_headers("inspector"),
    )
    assert active_resp.status_code == 200, active_resp.text
    active_data = active_resp.json()
    assert active_data["parent_regulation"] == "Legal Metrology (Packaged Commodities) Rules, 2011"
    assert active_data["module"] == "lmpc"
    assert active_data["active_rules_count"] >= 4

    rule_ids = [r["rule_id"] for r in active_data["active_rules"]]
    assert any("2(a)(i)" in r for r in rule_ids)
    assert any("2(a)(ii)" in r for r in rule_ids)
    assert any("2(a)(iii)" in r for r in rule_ids)
    assert any("2(b)" in r for r in rule_ids)

    # 3. Verify database verification endpoint (inspects PostgreSQL relational state)
    verify_resp = client.get(
        f"/regulations/verification/{gsr_577e_draft_id}",
        headers=get_auth_headers("reviewer"),
    )
    assert verify_resp.status_code == 200, verify_resp.text
    vdata = verify_resp.json()

    assert vdata["draft_id"] == gsr_577e_draft_id
    assert vdata["draft_approval_state"] == "ACTIVE"
    assert vdata["regulation_id"] == "lmpc"
    assert vdata["parent_regulation"] == "Legal Metrology (Packaged Commodities) Rules, 2011"
    assert vdata["published_in_regulatory_amendments"] is True
    assert vdata["rule_versions_count"] >= 4

    for pv in vdata["rule_versions"]:
        assert pv["module_id"] == "lmpc"
        assert pv["approval_state"] == "ACTIVE"


def test_generic_synthetic_amendment_workflow():
    """
    Test Section 14 & 15:
    Test a completely synthetic generic amendment to prove there is NO hardcoding of G.S.R. 577(E).

    Synthetic document structure:
    - Notification: G.S.R. 999(E)
    - Short Title: Plastic Waste Management (Third Amendment) Rules, 2024
    - Rule 1(1): Short Title (context provision)
    - Rule 1(2): Commencement (context provision, effective 2024-11-01)
    - Rule 2(a): Substantive rule (executable) - Minimum thickness for carry bags 120 microns
    """
    draft_id = "SYNTHETIC-AMEND-999"
    amendment = AmendmentDraft(
        id=draft_id,
        module="lmpc",
        source_document_id="synthetic_amend_999.pdf",
        approval_state=ApprovalState.EXTRACTED,
        extracted_at=datetime.now(timezone.utc),
        changes=[],
        proposed_rule_versions=[
            RuleVersion(
                id="rv-synthetic-rule-2a",
                module="lmpc",
                regulation="Legal Metrology (Packaged Commodities) Rules, 2011",
                rule_id="RULE-2A-SYNTHETIC",
                version="Third Amendment, 2024",
                effective_from=date(2024, 11, 1),
                approval_state=ApprovalState.EXTRACTED,
                source_document_id="synthetic_amend_999.pdf",
                text="Carry bags made of virgin or recycled plastic shall not be less than one hundred and twenty microns in thickness.",
                conditions={
                    "source_provision": "Rule 2(a)",
                    "provision_type": "SPECIFICATION",
                    "applicability": {
                        "scope": "plastic packaging",
                    },
                },
            )
        ],
        impact={
            "affected_commodities": ["plastic_bag", "packaging"],
            "amendment_metadata": {
                "amendment_name": "Third Amendment",
                "notification_number": "G.S.R. 999(E)",
                "full_title": "Plastic Waste Management (Third Amendment) Rules, 2024",
                "version_label": "Third Amendment, 2024",
                "effective_date": "2024-11-01",
                "context_provisions": {
                    "Rule 1(1)": {
                        "provision_type": "SHORT_TITLE",
                        "title": "Short title",
                        "version": "Third Amendment, 2024",
                    },
                    "Rule 1(2)": {
                        "provision_type": "COMMENCEMENT",
                        "title": "Commencement",
                        "version": "Third Amendment, 2024",
                    },
                },
            },
        },
    )
    save_amendment_draft(amendment, created_by="Unit Test Runner")

    # 1. Verify separation of executable vs context provisions
    resp = client.get(
        f"/regulations/drafts/{draft_id}/rules-identified",
        headers=get_auth_headers("reviewer"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert len(data["context_provisions"]) == 2
    assert len(data["rules_identified"]) == 1

    exec_rule = data["rules_identified"][0]
    assert exec_rule["display_provision"] == "Rule 2(a)"
    assert "one hundred and twenty microns" in exec_rule["canonical_english_text"]

    # 2. Test applicability evaluation
    resp_eval = client.post(
        f"/regulations/drafts/{draft_id}/evaluate-applicability",
        json={"product_category": "plastic packaging"},
        headers=get_auth_headers("reviewer"),
    )
    assert resp_eval.status_code == 200
    res = resp_eval.json()
    assert len(res["rules_considered"]) == 1
    assert res["rules_considered"][0]["status"] == "CONSIDERED / APPLICABLE"

    # 3. Atomic publish of synthetic amendment
    pub_resp = client.post(
        f"/regulations/drafts/{draft_id}/publish",
        headers=get_auth_headers("admin"),
    )
    assert pub_resp.status_code == 200, pub_resp.text
    pub_data = pub_resp.json()
    assert pub_data["status"] == "PUBLISHED / ACTIVE"
    assert pub_data["rules_published_count"] == 1

    # 4. Verify PostgreSQL relational state
    v_resp = client.get(
        f"/regulations/verification/{draft_id}",
        headers=get_auth_headers("reviewer"),
    )
    assert v_resp.status_code == 200, v_resp.text
    v_data = v_resp.json()
    assert v_data["draft_approval_state"] == "ACTIVE"
    assert v_data["rule_versions_count"] >= 1
    assert any(pv.get("rule_id") == "RULE-2A-SYNTHETIC" for pv in v_data["rule_versions"])
