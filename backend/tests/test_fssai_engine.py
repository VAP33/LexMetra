from fssai.engine import evaluate_fssai, load_fssai_rules, module_status
from schema import ExtractedFact, FactStatus, ProductInspection


def test_fssai_rules_are_not_in_lmpc_file():
    from pathlib import Path
    lmpc = (Path(__file__).resolve().parents[2] / "rules" / "rules.json").read_text(encoding="utf-8")
    assert "FSSAI-LABEL-LICENCE" not in lmpc
    rules = load_fssai_rules()
    assert {r["rule_id"] for r in rules} >= {"FSSAI-LABEL-LICENCE", "FSSAI-LABEL-VEG-NONVEG"}
    assert all(r.get("verification_status") == "needs_official_verification" for r in rules)
    assert all(r.get("module") == "fssai" for r in rules)


def test_absence_is_uncertain_never_fail():
    inspection = ProductInspection(
        inspection_id="f1",
        product_category="food",
        sale_type="retail",
        facts=[ExtractedFact(field="mrp", extracted_value="Rs 20", status=FactStatus.PASS, confidence=0.9)],
    )
    findings = evaluate_fssai(inspection)
    assert findings
    assert all(f.status is not FactStatus.FAIL for f in findings)
    assert any(f.status is FactStatus.UNCERTAIN for f in findings)
    assert module_status(findings) == "UNCERTAIN"


def test_observed_licence_is_pass_still_unverified():
    inspection = ProductInspection(
        inspection_id="f2",
        product_category="food",
        sale_type="retail",
        facts=[
            ExtractedFact(
                field="notes",
                extracted_value="FSSAI Lic No 10012345678901 veg ingredients Mfg Jan 2026",
                status=FactStatus.UNCERTAIN,
                confidence=0.6,
            )
        ],
    )
    findings = evaluate_fssai(inspection)
    by_id = {f.rule_id: f for f in findings}
    assert by_id["FSSAI-LABEL-LICENCE"].status is FactStatus.PASS
    assert by_id["FSSAI-LABEL-LICENCE"].verification_status == "needs_official_verification"


def test_non_food_skips_fssai():
    inspection = ProductInspection(
        inspection_id="f3",
        product_category="household",
        sale_type="retail",
    )
    assert evaluate_fssai(inspection) == []
    assert module_status([]) == "NOT_APPLICABLE"
