"""
VLM semantic verifier for ambiguous declaration wording.

The VLM is a SECONDARY REVIEW ASSISTANT. It never determines legal compliance,
changes a rule-engine verdict, invents legal requirements, or supplies missing
facts.

Contract:
    extracted evidence -> VLM ambiguity check -> optional review flag/note

If the API is unavailable or the response cannot be validated, this module
fails closed by returning a review-required result. It never fabricates a
successful verification.

The default provider is Anthropic when ANTHROPIC_API_KEY is configured.
A provider-agnostic callable can also be supplied for tests or future hosted
models, which keeps the legal pipeline independent of one vendor.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional


VERIFIER_SYSTEM_PROMPT = """You assist a Legal Metrology compliance screening tool.

You receive exactly one extracted declaration field and the already-selected
rule requirement supplied by the application.

Your ONLY task is to identify whether the extracted wording is genuinely
ambiguous enough that a human reviewer should inspect the evidence.

You MUST NOT:
- decide PASS, FAIL, EXEMPT, or legal compliance;
- override or reinterpret the supplied rule requirement;
- invent a rule, threshold, exemption, citation, date, or legal conclusion;
- infer facts that are not present in the supplied evidence;
- claim that a declaration is missing when the input only shows uncertain OCR;
- treat spelling/OCR uncertainty as a legal violation.

If the wording is clear enough from the supplied text, return ambiguous=false.
If the wording could reasonably be interpreted in more than one way, or the
text is too unclear to safely interpret, return ambiguous=true.

Respond ONLY with JSON:
{
  "ambiguous": true/false,
  "explanation": "plain-language explanation in at most 2 sentences"
}
"""


@dataclass
class VerifierResult:
    ambiguous: bool
    explanation: str
    raw_model_response: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None


def _build_user_prompt(
    field: str,
    extracted_text: str,
    rule_requirement: str,
) -> str:
    return (
        f"Field: {field}\n"
        f"Extracted text: {extracted_text!r}\n"
        f"Rule requirement supplied by the application: {rule_requirement}\n\n"
        "Assess wording ambiguity only. Do not make a compliance decision. "
        "Return JSON only."
    )


def _extract_text_content(response: Any) -> str:
    """Extract text blocks from an Anthropic-style response object."""
    content = getattr(response, "content", None)

    if not isinstance(content, (list, tuple)):
        return ""

    chunks = []
    for block in content:
        if getattr(block, "type", None) == "text":
            value = getattr(block, "text", "")
            if isinstance(value, str):
                chunks.append(value)

    return "".join(chunks).strip()


def _clean_json_text(text: str) -> str:
    """
    Remove only common Markdown code-fence wrappers.

    Do not use broad string stripping such as .strip("`json"), because it can
    remove legitimate characters from the model response.
    """
    text = (text or "").strip()

    match = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    return text


def _parse_response(
    text: str,
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> VerifierResult:
    """
    Parse and validate the strict JSON contract.

    Malformed or structurally invalid output becomes ambiguous=true so the
    pipeline cannot accidentally treat an unavailable/unreliable verifier as
    evidence of clarity.
    """
    cleaned = _clean_json_text(text)

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return VerifierResult(
            ambiguous=True,
            explanation=(
                "The semantic verifier returned an invalid response, so "
                "manual review is required."
            ),
            raw_model_response=cleaned,
            model=model,
            provider=provider,
        )

    if not isinstance(data, dict):
        return VerifierResult(
            ambiguous=True,
            explanation=(
                "The semantic verifier returned an unexpected response shape, "
                "so manual review is required."
            ),
            raw_model_response=cleaned,
            model=model,
            provider=provider,
        )

    ambiguous = data.get("ambiguous")

    # Do not accept arbitrary truthy strings such as "false" as valid booleans.
    if not isinstance(ambiguous, bool):
        return VerifierResult(
            ambiguous=True,
            explanation=(
                "The semantic verifier did not return a valid ambiguity flag, "
                "so manual review is required."
            ),
            raw_model_response=cleaned,
            model=model,
            provider=provider,
        )

    explanation = data.get("explanation", "")
    if not isinstance(explanation, str):
        return VerifierResult(
            ambiguous=True,
            explanation=(
                "The semantic verifier returned invalid explanation text, "
                "so manual review is required."
            ),
            raw_model_response=cleaned,
            model=model,
            provider=provider,
        )

    explanation = " ".join(explanation.split()).strip()

    # Keep the UI/report contract bounded even if a model ignores the prompt.
    sentences = re.split(r"(?<=[.!?])\s+", explanation)
    explanation = " ".join(sentences[:2]).strip()

    if len(explanation) > 500:
        explanation = explanation[:497].rstrip() + "..."

    if not explanation:
        explanation = (
            "No explanation was returned by the semantic verifier; "
            "manual review is required."
            if ambiguous
            else "The wording was assessed as sufficiently clear."
        )

    return VerifierResult(
        ambiguous=ambiguous,
        explanation=explanation,
        raw_model_response=cleaned,
        model=model,
        provider=provider,
    )


def _safe_inputs(
    field: str,
    extracted_text: str,
    rule_requirement: str,
) -> tuple[str, str, str]:
    field = str(field or "").strip()
    extracted_text = str(extracted_text or "").strip()
    rule_requirement = str(rule_requirement or "").strip()

    if not field:
        raise ValueError("field is required")
    if not rule_requirement:
        raise ValueError("rule_requirement is required")

    # An empty extracted value is not something the VLM should interpret as a
    # legal absence. Return a deterministic review flag instead at call time.
    return field[:200], extracted_text[:4000], rule_requirement[:4000]


def verify_ambiguous_field(
    field: str,
    extracted_text: str,
    rule_requirement: str,
    model: str = "claude-sonnet-4-6",
) -> VerifierResult:
    """
    Call Anthropic for ambiguity screening.

    Empty OCR text is handled locally because asking a language model whether
    an empty string is ambiguous adds no useful evidence.

    Raises RuntimeError for missing SDK/key or transport/API failures. The
    caller can convert that operational failure into its normal review state.
    This function never fabricates a model result.
    """
    field, extracted_text, rule_requirement = _safe_inputs(
        field,
        extracted_text,
        rule_requirement,
    )

    if not extracted_text:
        return VerifierResult(
            ambiguous=True,
            explanation=(
                "No extracted wording was available for semantic verification; "
                "manual review of the image evidence is required."
            ),
            model=model,
            provider="local_guard",
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. The semantic verifier requires an "
            "explicit API key and does not fabricate an offline model result."
        )

    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "The anthropic package is not installed. Install the backend "
            "requirements before enabling VLM semantic verification."
        ) from exc

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=220,
            temperature=0,
            system=VERIFIER_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": _build_user_prompt(
                        field,
                        extracted_text,
                        rule_requirement,
                    ),
                }
            ],
        )
    except Exception as exc:
        # Keep the original exception out of the user-facing compliance report,
        # but preserve it as an operational error for the API/log layer.
        raise RuntimeError(
            f"Semantic verifier API call failed: {type(exc).__name__}"
        ) from exc

    text = _extract_text_content(response)

    if not text:
        return VerifierResult(
            ambiguous=True,
            explanation=(
                "The semantic verifier returned no usable text, so manual "
                "review is required."
            ),
            model=model,
            provider="anthropic",
        )

    return _parse_response(
        text,
        model=model,
        provider="anthropic",
    )


def verify_ambiguous_field_with_provider(
    field: str,
    extracted_text: str,
    rule_requirement: str,
    provider_call: Callable[[str], str],
    *,
    model: Optional[str] = None,
    provider_name: str = "custom",
) -> VerifierResult:
    """
    Provider-agnostic test/integration path.

    provider_call receives the complete user prompt and must return the model's
    text response. The same strict parser is then applied.
    """
    field, extracted_text, rule_requirement = _safe_inputs(
        field,
        extracted_text,
        rule_requirement,
    )

    if not extracted_text:
        return VerifierResult(
            ambiguous=True,
            explanation=(
                "No extracted wording was available for semantic verification; "
                "manual review of the image evidence is required."
            ),
            model=model,
            provider="local_guard",
        )

    try:
        response_text = provider_call(
            _build_user_prompt(field, extracted_text, rule_requirement)
        )
    except Exception as exc:
        raise RuntimeError(
            f"Semantic verifier provider call failed: {type(exc).__name__}"
        ) from exc

    return _parse_response(
        response_text,
        model=model,
        provider=provider_name,
    )


def _gemini_provider_call(prompt: str, *, model: str = "gemini-2.5-flash-lite") -> str:
    import google.generativeai as genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. The semantic verifier requires an "
            "explicit API key and does not fabricate an offline model result."
        )
    genai.configure(api_key=api_key)
    client = genai.GenerativeModel(model, system_instruction=VERIFIER_SYSTEM_PROMPT)
    response = client.generate_content(prompt, generation_config={"temperature": 0})
    return (response.text or "").strip()


def verify_ambiguous_field_gemini(
    field: str,
    extracted_text: str,
    rule_requirement: str,
    *,
    model: str = "gemini-2.5-flash-lite",
) -> VerifierResult:
    """Run semantic verification with Google Gemini as the provider."""
    return verify_ambiguous_field_with_provider(
        field,
        extracted_text,
        rule_requirement,
        provider_call=lambda p: _gemini_provider_call(p, model=model),
        model=model,
        provider_name="gemini",
    )


def verify_ambiguous_field_mocked(
    field: str,
    extracted_text: str,
    rule_requirement: str,
    mock_json: str,
) -> VerifierResult:
    """Offline parser/plumbing test. No network call and no API key required."""
    _safe_inputs(field, extracted_text, rule_requirement)
    return _parse_response(
        mock_json,
        model="mock",
        provider="mock",
    )


if __name__ == "__main__":
    examples = [
        '{"ambiguous": true, "explanation": "The date format could be interpreted in more than one way, so a reviewer should inspect the label."}',
        '{"ambiguous": false, "explanation": "The extracted wording is clear enough for the semantic check."}',
        "```json\n{\"ambiguous\": true, \"explanation\": \"The wording is unclear.\"}\n```",
        '{"ambiguous": "false", "explanation": "This is intentionally invalid."}',
        "not json",
    ]

    for example in examples:
        result = verify_ambiguous_field_mocked(
            field="mfg_date",
            extracted_text="MFD 08-26",
            rule_requirement="Month and year of manufacture, clearly stated.",
            mock_json=example,
        )
        print(result)
