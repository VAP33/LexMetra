import json

from lexmetra_rules.pipeline import run_pipeline_from_pages


def test_pipeline_result_is_json_serializable(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    dumped = result.model_dump(mode="json")
    payload = json.dumps(dumped)
    reloaded = json.loads(payload)
    assert reloaded["document_id"] == "doc-1"
    assert len(reloaded["rules"]) == len(result.rules)


def test_extracted_rule_json_round_trip(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    rule = result.rules[0]
    payload = rule.model_dump_json()
    from lexmetra_rules.models import ExtractedRule
    restored = ExtractedRule.model_validate_json(payload)
    assert restored == rule


def test_enum_fields_serialize_to_plain_strings(synthetic_pages):
    result = run_pipeline_from_pages(synthetic_pages, document_id="doc-1", source="Test Reg")
    dumped = result.model_dump(mode="json")
    rule = dumped["rules"][0]
    assert isinstance(rule["review_status"], str)
    assert isinstance(rule["classification"]["review_status"], str)
