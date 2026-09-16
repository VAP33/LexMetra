from engine import ComplianceEngine, Evidence, RuleEngine

def test_compliance_engine_import_and_minimal_evaluation():
    engine = ComplianceEngine(rules_path=None)
    report = engine.evaluate({"product": {"name": "Example"}})
    assert report is not None
    assert isinstance(report.results, list)

def test_existing_rule_engine_api_is_preserved():
    assert RuleEngine is not None
    assert Evidence is not None
