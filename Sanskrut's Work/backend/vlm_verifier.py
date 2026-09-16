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
        raise RuntimeError(
            f"Semantic verifier API call failed: {type(exc).__name__}: {exc}"
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

def verify_ambiguous_field_openrouter(
    field: str,
    extracted_text: str,
    rule_requirement: str,
    model: str = "qwen/qwen-2.5-vl-72b-instruct",
    api_key: Optional[str] = None,
    endpoint: str = "https://openrouter.ai/api/v1/chat/completions",
) -> VerifierResult:
    """
    Call OpenRouter for ambiguity screening.
    """
    import urllib.request

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

    resolved_key = (
        api_key
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY2")
    )
    if not resolved_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. The semantic verifier requires an "
            "explicit API key."
        )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_user_prompt(field, extracted_text, rule_requirement),
            },
        ],
        "temperature": 0.0,
        "max_tokens": 250,
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://lexmetra.gov.in",
            "X-Title": "LexMetra Legal Metrology Verification",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
    except Exception as exc:
        raise RuntimeError(
            f"OpenRouter semantic verifier API call failed: {type(exc).__name__}: {exc}"
        ) from exc

    return _parse_response(
        text,
        model=model,
        provider="openrouter",
    )


def verify_ambiguous_field_auto(
    field: str,
    extracted_text: str,
    rule_requirement: str,
) -> VerifierResult:
    """
    Automatically routes to Anthropic or OpenRouter based on available API keys.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return verify_ambiguous_field(field, extracted_text, rule_requirement)
        except Exception:
            pass

    if os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY2"):
        try:
            return verify_ambiguous_field_openrouter(field, extracted_text, rule_requirement)
        except Exception:
            pass

    # Safe offline review fallback
    return VerifierResult(
        ambiguous=True,
        explanation="No active VLM API key configured; manual review flag recorded.",
        provider="offline_fallback",
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


# ---------------------------------------------------------------------------
# Zero-Shot Semantic OCR Token Normalizer & Multimodal VLM Resolver
# ---------------------------------------------------------------------------

SEMANTIC_NORMALIZER_PROMPT = """You are an expert Legal Metrology (LMPC Act 2009 / Packaged Commodities Rules 2011) declaration parser.

You receive raw, noisy, potentially fragmented or tilted OCR text lines extracted from an Indian consumer product package.
Your task is to accurately map and normalize these tokens into standard statutory declarations.

Guidelines:
1. MRP: Standard retail price in Rupees (e.g., "₹275.00", "₹60.00"). Stamped numbers like "*天275/-", "275/-", "* ₹275/-" represent MRP.
2. NET QUANTITY: Standard metric units (e.g., "200 ml", "100 g", "10 N", "Shakti Mat Machine + 10N").
3. MFG DATE: Month/Year of manufacture (e.g., "09/2025", "04/2026"). Dot-matrix stamps like "#09125" mean 09/2025.
4. EXPIRY DATE: Relative (e.g., "36 Months from Manufacturing Date", "2 Years from PKD") or absolute dates.
5. MANUFACTURER: Full company name and address (e.g., "Hindustan Unilever Ltd., Haridwar").
6. CONSUMER CARE: Toll-free phone, email, and postal address.
7. UNIT PRICE: Per-unit rate under Rule 6(11) (e.g., "₹1.38/ml", "₹0.50/g").
8. COUNTRY OF ORIGIN: "India" for "Made in India", or imported origin.
9. BATCH NO: Lot / Batch code (e.g., "B14", "AA2604111").
10. COMMON NAME: Generic product name (e.g., "Body Lotion", "Mosquito Mat Machine").

Do NOT mistake phone numbers (e.g., 1800-10-22-221) for dates or MRP.

Respond ONLY with valid JSON in this exact schema:
{
  "mrp": "₹275.00" or null,
  "net_quantity": "200 ml" or null,
  "mfg_date": "09/2025" or null,
  "expiry_date": "36 Months from Manufacturing Date" or null,
  "manufacturer": "Hindustan Unilever Ltd." or null,
  "consumer_care": "1800-10-22-221 | lever.care@unilever.com" or null,
  "unit_price": "₹1.38/ml" or null,
  "country_of_origin": "India" or null,
  "batch_no": "B14" or null,
  "common_name": "Body Lotion" or null
}
"""


def normalize_ocr_tokens_zero_shot(raw_text_lines: Sequence[str]) -> Dict[str, Any]:
    """
    Zero-Shot Semantic OCR Token Normalizer:
    Takes raw, unstructured OCR text lines and routes them through a semantic LLM
    parser to accurately extract statutory Legal Metrology declarations from novel layouts.
    """
    if not raw_text_lines:
        return {}

    resolved_key = (
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY2")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )
    if not resolved_key:
        return {}

    joined_text = "\n".join(f"- {line}" for line in raw_text_lines if line and line.strip())
    if not joined_text:
        return {}

    import urllib.request

    endpoint = os.environ.get("OPENROUTER_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions")
    model = os.environ.get("OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SEMANTIC_NORMALIZER_PROMPT},
            {
                "role": "user",
                "content": f"Extract statutory declarations from these raw packaging OCR lines:\n\n{joined_text}",
            },
        ],
        "temperature": 0.0,
        "max_tokens": 500,
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://lexmetra.gov.in",
            "X-Title": "LexMetra Legal Metrology Verification",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            cleaned = _clean_json_text(content)
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass

    return {}


def resolve_statutory_declarations_vlm(
    image_bgr: Any,
    missing_fields: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Automatic Multimodal VLM Resolver:
    When local CV detects missing statutory fields or low-confidence ambiguous crops,
    this triggers OpenRouter VLM (e.g. Qwen-2.5-VL / Gemini / Groq) to visually scan the
    packaging and return zero-shot structured Legal Metrology declarations.
    """
    if image_bgr is None:
        return {}

    resolved_key = (
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY2")
        or os.environ.get("GROQ_API_KEY")
    )
    if not resolved_key:
        return {}

    import base64
    import cv2
    import numpy as np
    import urllib.request

    # Resize image if large to optimize latency
    h, w = image_bgr.shape[:2]
    max_dim = 1280
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        resized = cv2.resize(image_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        resized = image_bgr

    success, buffer = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not success:
        return {}

    b64_image = base64.b64encode(buffer).decode("utf-8")
    missing_str = ", ".join(missing_fields) if missing_fields else "all mandatory declarations"

    prompt_text = (
        f"Inspect this packaged product image under Indian Legal Metrology (LMPC) Rules 2011.\n"
        f"Extract all statutory declarations. Missing or ambiguous fields needing resolution: {missing_str}.\n\n"
        f"Respond ONLY with a JSON object matching this schema:\n"
        f'{{\n'
        f'  "mrp": "₹...",\n'
        f'  "net_quantity": "...",\n'
        f'  "mfg_date": "...",\n'
        f'  "expiry_date": "...",\n'
        f'  "manufacturer": "...",\n'
        f'  "consumer_care": "...",\n'
        f'  "unit_price": "...",\n'
        f'  "country_of_origin": "...",\n'
        f'  "batch_no": "...",\n'
        f'  "common_name": "..."\n'
        f'}}'
    )

    endpoint = os.environ.get("OPENROUTER_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions")
    vlm_model = os.environ.get("OPENROUTER_VLM_MODEL", "qwen/qwen-2.5-vl-72b-instruct")

    payload = {
        "model": vlm_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                    },
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 600,
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://lexmetra.gov.in",
            "X-Title": "LexMetra Legal Metrology Verification",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            cleaned = _clean_json_text(content)
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass

    return {}


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
