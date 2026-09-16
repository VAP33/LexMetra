import json
from unittest.mock import MagicMock, patch

from lexmetra_rules import llm_assist


def test_is_ollama_available_false_when_unreachable():
    # Nothing is listening on this port in the test environment — this
    # exercises the real "connection refused" path, not a mock.
    assert llm_assist.is_ollama_available(base_url="http://localhost:1") is False


def test_query_clause_returns_none_when_unreachable():
    result = llm_assist.query_clause(
        "Every package shall bear the manufacturer's name.",
        base_url="http://localhost:1",
    )
    assert result is None


def test_query_clause_returns_none_on_malformed_json_response():
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {"response": "not valid json {{{"}
    with patch.object(llm_assist.requests, "post", return_value=fake_resp):
        result = llm_assist.query_clause("Every package shall bear a name.")
    assert result is None


def test_query_clause_discards_ungrounded_fields():
    clause_text = "Every package shall bear the manufacturer's name."
    llm_output = {
        "semantic_role": "OBLIGATION",
        "requirement_subject": "Every package",  # grounded
        "requirement_action": "must be incinerated after use",  # NOT in source text
        "applies_to": "manufacturer's name",  # grounded
        "confidence": "certain",
    }
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {"response": json.dumps(llm_output)}
    with patch.object(llm_assist.requests, "post", return_value=fake_resp):
        result = llm_assist.query_clause(clause_text)

    assert result is not None
    assert result.requirement_subject == "Every package"
    assert result.applies_to == "manufacturer's name"
    assert result.requirement_action is None  # discarded — not grounded
    assert any("requirement_action" in f for f in result.discarded_fields)


def test_query_clause_rejects_unrecognized_semantic_role():
    clause_text = "Every package shall bear the manufacturer's name."
    llm_output = {
        "semantic_role": "TOTALLY_MADE_UP_ROLE",
        "requirement_subject": None,
        "requirement_action": None,
        "applies_to": None,
        "confidence": "uncertain",
    }
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {"response": json.dumps(llm_output)}
    with patch.object(llm_assist.requests, "post", return_value=fake_resp):
        result = llm_assist.query_clause(clause_text)

    assert result is not None
    assert result.semantic_role is None
    assert any("semantic_role" in f for f in result.discarded_fields)


def test_query_clause_defaults_confidence_to_uncertain_when_missing():
    clause_text = "Every package shall bear the manufacturer's name."
    llm_output = {"semantic_role": "OBLIGATION"}
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {"response": json.dumps(llm_output)}
    with patch.object(llm_assist.requests, "post", return_value=fake_resp):
        result = llm_assist.query_clause(clause_text)
    assert result.confidence == "uncertain"


def test_query_clause_never_raises_on_network_exception():
    with patch.object(llm_assist.requests, "post", side_effect=ConnectionError("refused")):
        result = llm_assist.query_clause("Every package shall bear a name.")
    assert result is None


def test_prompt_never_contains_more_than_the_single_clause():
    """The brief is explicit: never send the whole document, only the
    already-segmented clause. This checks the prompt-building logic
    embeds exactly the given clause text and nothing else document-sized."""
    clause_text = "Every package shall bear the manufacturer's name."
    prompt = llm_assist._PROMPT_TEMPLATE.format(
        clause_text=clause_text, roles=sorted(llm_assist._ALLOWED_ROLES)
    )
    assert clause_text in prompt
    # Sanity bound: a single clause's prompt should be small, not
    # document-sized (this would catch an accidental whole-document dump).
    assert len(prompt) < 4000
