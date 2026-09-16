"""
Optional local Ollama semantic-assist layer.

Off by default. The deterministic pipeline (clause_segmentation.py,
semantic_roles.py, clause_extraction.py, validation.py) is fully
functional without this module — nothing here is required, and every
function degrades to a no-op if Ollama is unreachable.

Design constraints (from the brief, enforced in code, not just by
convention):
  - The full document is NEVER sent to the LLM. Only ONE already-
    deterministically-segmented clause's text is sent per call.
  - The LLM's response is validated for GROUNDING: any span-like field it
    returns must actually appear (case-insensitively, allowing minor
    whitespace differences) in the clause text it was given. A field that
    fails this check is discarded, not trusted.
  - The LLM is asked to return null/"UNCERTAIN" rather than guess, and a
    null/"UNCERTAIN" response is treated as "no information", never as
    a confident negative.
  - Any exception (connection refused, timeout, malformed JSON, model not
    pulled) results in the LLM assist being skipped for that clause —
    never a pipeline failure.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

DEFAULT_OLLAMA_URL = os.environ.get("LEXMETRA_OLLAMA_URL", "http://localhost:11434")
DEFAULT_OLLAMA_MODEL = os.environ.get("LEXMETRA_OLLAMA_MODEL", "llama3")
_REACHABILITY_TIMEOUT_SECONDS = 1.5
_GENERATE_TIMEOUT_SECONDS = 20

_ALLOWED_ROLES = {
    "DEFINITION", "OBLIGATION", "PROHIBITION", "PERMISSION", "CONDITION",
    "EXCEPTION", "EXEMPTION", "SCOPE", "APPLICABILITY", "THRESHOLD",
    "PROCEDURE", "EFFECTIVE_DATE", "PENALTY", "EXPLANATION", "OTHER",
    "UNCERTAIN",
}

_PROMPT_TEMPLATE = """You are assisting with structured legal analysis of ONE short excerpt \
from a packaging/labelling regulation. You are given ONLY this excerpt — you have no other \
context and must not assume any.

Excerpt:
\"\"\"
{clause_text}
\"\"\"

Return ONLY a JSON object (no prose, no markdown fences) with exactly these keys:
{{
  "semantic_role": one of {roles},
  "requirement_subject": a short phrase copied verbatim from the excerpt, or null,
  "requirement_action": a short phrase copied verbatim from the excerpt, or null,
  "applies_to": a short phrase copied verbatim from the excerpt, or null,
  "confidence": "certain" or "uncertain"
}}

Rules:
- Every non-null value MUST be an exact substring of the excerpt above. Do not paraphrase.
- If you are not confident, use "confidence": "uncertain" and prefer null over guessing.
- Do not invent any fact not present in the excerpt.
"""


@dataclass
class LlmAssistResult:
    semantic_role: Optional[str]
    requirement_subject: Optional[str]
    requirement_action: Optional[str]
    applies_to: Optional[str]
    confidence: str
    raw_response: Dict[str, Any]
    discarded_fields: List[str]


def is_ollama_available(base_url: str = DEFAULT_OLLAMA_URL) -> bool:
    if requests is None:
        return False
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=_REACHABILITY_TIMEOUT_SECONDS)
        return resp.status_code == 200
    except Exception:
        return False


def _grounded(value: Optional[str], clause_text: str) -> bool:
    if value is None:
        return True
    normalized_value = " ".join(value.split()).lower()
    normalized_source = " ".join(clause_text.split()).lower()
    return bool(normalized_value) and normalized_value in normalized_source


def query_clause(
    clause_text: str,
    *,
    base_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_OLLAMA_MODEL,
) -> Optional[LlmAssistResult]:
    """
    Send ONE clause's text to Ollama and return a grounding-validated
    result, or None if Ollama is unavailable, the call fails, or the
    response cannot be parsed at all. Ungrounded individual fields are
    dropped (set to None) rather than causing the whole call to fail.
    """
    if requests is None:
        return None

    prompt = _PROMPT_TEMPLATE.format(clause_text=clause_text, roles=sorted(_ALLOWED_ROLES))

    try:
        resp = requests.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
            timeout=_GENERATE_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
        raw_text = payload.get("response", "")
        parsed = json.loads(raw_text)
    except Exception:
        return None

    if not isinstance(parsed, dict):
        return None

    discarded: List[str] = []

    role = parsed.get("semantic_role")
    if role not in _ALLOWED_ROLES:
        discarded.append("semantic_role (not a recognized role)")
        role = None

    subject = parsed.get("requirement_subject")
    if not _grounded(subject, clause_text):
        discarded.append("requirement_subject (not found verbatim in clause text)")
        subject = None

    action = parsed.get("requirement_action")
    if not _grounded(action, clause_text):
        discarded.append("requirement_action (not found verbatim in clause text)")
        action = None

    applies_to = parsed.get("applies_to")
    if not _grounded(applies_to, clause_text):
        discarded.append("applies_to (not found verbatim in clause text)")
        applies_to = None

    confidence = parsed.get("confidence")
    if confidence not in ("certain", "uncertain"):
        confidence = "uncertain"

    return LlmAssistResult(
        semantic_role=role,
        requirement_subject=subject,
        requirement_action=action,
        applies_to=applies_to,
        confidence=confidence,
        raw_response=parsed,
        discarded_fields=discarded,
    )
