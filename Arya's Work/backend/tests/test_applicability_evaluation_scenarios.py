"""
Focused tests for LexMetra applicability evaluation logic (Task #2).

Verifies:
1. Scenario A: Electronic product manufactured in August 2022 -> July 15, 2022 trigger satisfied (APPLICABLE).
2. Scenario B: Electronic product manufactured in June 2022 -> July 15, 2022 trigger NOT satisfied (NOT_APPLICABLE).
3. Scenario C: Non-electronic food article -> electronic scope condition NOT satisfied (NOT_APPLICABLE).
4. Scenario D: Electronic product manufactured post-period (e.g. August 2023) -> 1-year applicability end date exceeded (NOT_APPLICABLE).
5. Scenario E: Missing/uncertain evidence (missing manufacture_date or product_category) -> UNCERTAIN.
6. Date Integrity & Non-Collapsing: Confirms amendment effective date (2022-07-14), applicability start/trigger date (2022-07-15),
   and applicability end date (2023-07-15) are strictly maintained as separate dates.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.tests.test_amendment_publishing_and_verification import get_auth_headers
from backend.tests.fixtures.pdf_builder import build_native_text_pdf
from backend.tests.test_gsr_577_e_ingestion import HINDI_PAGE_TEXT, ENGLISH_PAGE_TEXT

client = TestClient(app)


@pytest.fixture
def gsr_577e_draft_id(tmp_path: Path) -> str:
    """Build and ingest G.S.R. 577(E) gazette PDF and return draft_id."""
    pdf_path = tmp_path / "gsr_577_e_applicability_test.pdf"
    build_native_text_pdf(pdf_path, [HINDI_PAGE_TEXT, ENGLISH_PAGE_TEXT])

    headers = get_auth_headers("reviewer")
    with open(pdf_path, "rb") as f:
        resp = client.post(
            "/regulations/ingest",
            files={"file": ("gsr_577_e_applicability_test.pdf", f, "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 200, f"Ingestion failed: {resp.text}"
    data = resp.json()
    assert "draft" in data
    return data["draft"]["id"]


def test_scenario_a_electronic_product_aug_2022_trigger_satisfied(gsr_577e_draft_id: str):
    """
    SCENARIO A:
    Electronic product manufactured in August 2022 (e.g. 2022-08-01).
    Expected: The July 15, 2022 trigger is satisfied -> CONSIDERED / APPLICABLE.
    """
    context = {
        "product_category": "electronics",
        "manufacture_date": "2022-08-01",
        "is_imported": False,
        "sale_type": "retail",
    }
    resp = client.post(
        f"/regulations/drafts/{gsr_577e_draft_id}/evaluate-applicability",
        json=context,
        headers=get_auth_headers("reviewer"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    considered = data["rules_considered"]
    not_considered = data["rules_not_considered"]

    assert len(considered) == 4, f"Expected 4 applicable rules, got {len(considered)}"
    assert len(not_considered) == 0

    rule_names = [r["rule"] for r in considered]
    assert "Rule 2(a)(i)" in rule_names
    assert "Rule 2(a)(ii)" in rule_names
    assert "Rule 2(a)(iii)" in rule_names

    for r in considered:
        assert r["status"] == "CONSIDERED / APPLICABLE"
        assert "post-2022-07-15" in r["reason"] or "applicable" in r["reason"].lower()


def test_scenario_b_electronic_product_jun_2022_pre_trigger_not_satisfied(gsr_577e_draft_id: str):
    """
    SCENARIO B:
    Electronic product manufactured in June 2022 (e.g. 2022-06-01).
    Expected: The July 15, 2022 trigger is NOT satisfied -> NOT_APPLICABLE.
    """
    context = {
        "product_category": "electronics",
        "manufacture_date": "2022-06-01",
        "is_imported": False,
        "sale_type": "retail",
    }
    resp = client.post(
        f"/regulations/drafts/{gsr_577e_draft_id}/evaluate-applicability",
        json=context,
        headers=get_auth_headers("reviewer"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    considered = data["rules_considered"]
    not_considered = data["rules_not_considered"]

    # All electronic rules conditioned on post-July 15 2022 should be NOT_APPLICABLE
    assert len(considered) == 0
    assert len(not_considered) == 4

    for r in not_considered:
        assert r["status"] == "NOT_APPLICABLE"
        assert "substantive trigger date" in r["reason"]
        assert "2022-07-15" in r["reason"]
        assert "2022-06-01" in r["reason"]


def test_scenario_c_non_electronic_food_article_scope_not_satisfied(gsr_577e_draft_id: str):
    """
    SCENARIO C:
    Non-electronic food article (e.g. packaged_food, mfg: 2022-08-01).
    Expected: The electronic-product applicability condition is NOT satisfied -> NOT_APPLICABLE.
    """
    context = {
        "product_category": "packaged_food",
        "manufacture_date": "2022-08-01",
        "is_imported": False,
        "sale_type": "retail",
    }
    resp = client.post(
        f"/regulations/drafts/{gsr_577e_draft_id}/evaluate-applicability",
        json=context,
        headers=get_auth_headers("reviewer"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    considered = data["rules_considered"]
    not_considered = data["rules_not_considered"]

    assert len(considered) == 0
    assert len(not_considered) == 4

    for r in not_considered:
        assert r["status"] == "NOT_APPLICABLE"
        assert "packaged_food" in r["reason"]
        assert "requires electronic product" in r["reason"]


def test_scenario_d_electronic_product_post_applicability_end_date(gsr_577e_draft_id: str):
    """
    SCENARIO D:
    Electronic product manufactured after the 1-year applicability end date (e.g. August 2023).
    Expected: Since the applicability duration is 1 year from 2022-07-15 (ending 2023-07-15),
    an electronic product manufactured on 2023-08-01 is NOT_APPLICABLE because the transition period has elapsed.
    """
    context = {
        "product_category": "electronics",
        "manufacture_date": "2023-08-01",
        "is_imported": False,
        "sale_type": "retail",
    }
    resp = client.post(
        f"/regulations/drafts/{gsr_577e_draft_id}/evaluate-applicability",
        json=context,
        headers=get_auth_headers("reviewer"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    considered = data["rules_considered"]
    not_considered = data["rules_not_considered"]

    assert len(considered) == 0
    assert len(not_considered) == 4

    for r in not_considered:
        assert r["status"] == "NOT_APPLICABLE"
        assert "after applicability period end date" in r["reason"] or "2023-07-15" in r["reason"]


def test_scenario_e_missing_evidence_is_uncertain(gsr_577e_draft_id: str):
    """
    SCENARIO E:
    Missing evidence:
    1. manufacture_date missing -> cannot verify post-trigger date -> UNCERTAIN.
    2. product_category missing -> cannot verify electronic scope -> UNCERTAIN.
    """
    # 1. Missing manufacture_date
    context_no_mfg = {
        "product_category": "electronics",
        "manufacture_date": None,
    }
    resp1 = client.post(
        f"/regulations/drafts/{gsr_577e_draft_id}/evaluate-applicability",
        json=context_no_mfg,
        headers=get_auth_headers("reviewer"),
    )
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()
    assert len(data1["rules_considered"]) == 0
    assert len(data1["rules_not_considered"]) == 4
    for r in data1["rules_not_considered"]:
        assert r["status"] == "UNCERTAIN"
        assert "Manufacture date is not provided" in r["reason"]

    # 2. Missing product_category
    context_no_cat = {
        "product_category": None,
        "manufacture_date": "2022-08-01",
    }
    resp2 = client.post(
        f"/regulations/drafts/{gsr_577e_draft_id}/evaluate-applicability",
        json=context_no_cat,
        headers=get_auth_headers("reviewer"),
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert len(data2["rules_considered"]) == 0
    assert len(data2["rules_not_considered"]) == 4
    for r in data2["rules_not_considered"]:
        assert r["status"] == "UNCERTAIN"
        assert "Product category is not provided" in r["reason"]


def test_date_integrity_three_distinct_dates_not_collapsed(gsr_577e_draft_id: str):
    """
    Confirms that:
      - amendment effective date (2022-07-14)
      - applicability start/trigger date (2022-07-15)
      - applicability end date (2023-07-15)
    are strictly distinct and NEVER collapsed into a single date.
    """
    context = {
        "product_category": "electronics",
        "manufacture_date": "2022-08-01",
    }
    resp = client.post(
        f"/regulations/drafts/{gsr_577e_draft_id}/evaluate-applicability",
        json=context,
        headers=get_auth_headers("reviewer"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    for item in data["rules_considered"]:
        app = item["applicability_condition"]
        eff_date = app.get("amendment_effective_date")
        trigger_date = app.get("manufactured_packed_imported_after")
        end_date = app.get("applicability_end_date")
        duration = app.get("duration")

        # 1. Effective date is 2022-07-14 (from commencement / Gazette publication)
        assert eff_date == "2022-07-14", f"Expected effective date 2022-07-14, got {eff_date}"

        # 2. Trigger date is 2022-07-15 (from substantive Rule 2(a)(i) trigger)
        assert trigger_date == "2022-07-15", f"Expected trigger date 2022-07-15, got {trigger_date}"

        # 3. Applicability end date is 2023-07-15 (trigger date + 1 year duration)
        assert end_date == "2023-07-15", f"Expected end date 2023-07-15, got {end_date}"

        # 4. Duration is 1 year
        assert duration == "1 year"

        # 5. Strictly confirm all 3 dates are distinct!
        assert eff_date != trigger_date, "amendment effective date and trigger date must not be collapsed!"
        assert trigger_date != end_date, "trigger date and end date must not be collapsed!"
        assert eff_date != end_date, "effective date and end date must not be collapsed!"
