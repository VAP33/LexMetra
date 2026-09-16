"""Gazette OCR → structured rule diff (RULE-03).

Uses the existing OCR engine (Tesseract path until OCR-01 fusion is enabled).
Does not auto-transition amendments to ACTIVE. A failed OpenL redeploy must
leave the amendment SCHEDULED and record the error — never silently keep a
stale zip as if it were the new version.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any, Optional

from PIL import Image

from models import AmendmentDraft, ApprovalState
from openl.pipeline import record_deploy, resolve_zip_for_date

RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "rules.json"
OPENL_ZIP = Path(__file__).resolve().parent / "openl" / "dist" / "lmpc-exemption.zip"


def ocr_gazette_image(image: Image.Image) -> str:
    from ocr_extraction import run_ocr

    lines = run_ocr(image)
    return "\n".join(line.text for line in lines if line.text)


def extract_rule_mentions(text: str) -> list[str]:
    found = []
    for match in re.finditer(r"\bRule\s+(\d+[A-Za-z]?)\b", text, re.I):
        token = f"Rule {match.group(1)}"
        if token not in found:
            found.append(token)
    return found


def diff_against_rules_json(
    gazette_text: str,
    *,
    rules_path: Path = RULES_PATH,
) -> dict[str, Any]:
    data = json.loads(rules_path.read_text(encoding="utf-8"))
    mentions = extract_rule_mentions(gazette_text)
    diffs = []
    for rule in data.get("rules") or []:
        clause = str(rule.get("clause") or "")
        if mentions and not any(m.lower() in clause.lower() or clause.lower() in m.lower() for m in mentions):
            # Still attach a note when the gazette names a rule id substring.
            if not any(m.split()[-1] in clause for m in mentions):
                continue
        current = json.dumps(
            {
                "rule_id": rule.get("rule_id"),
                "clause": rule.get("clause"),
                "legal_note": rule.get("legal_note"),
                "threshold": rule.get("threshold"),
            },
            indent=2,
            sort_keys=True,
        )
        unified = list(
            difflib.unified_diff(
                current.splitlines(),
                gazette_text.splitlines()[:80],
                fromfile=f"rules.json:{rule.get('rule_id')}",
                tofile="gazette-ocr",
                lineterm="",
            )
        )
        diffs.append(
            {
                "rule_id": rule.get("rule_id"),
                "clause": clause,
                "verification_status": "needs_official_verification",
                "unified_diff": unified,
            }
        )
    return {
        "mentions": mentions,
        "diffs": diffs,
        "ocr_chars": len(gazette_text),
        "engine": "tesseract_interim",
        "note": (
            "OCR text is evidence, not an approved amendment. Human review is "
            "required. verification_status remains needs_official_verification."
        ),
    }


def redeploy_on_activation(
    draft: AmendmentDraft,
    *,
    zip_path: Path = OPENL_ZIP,
) -> dict[str, Any]:
    """Attempt RULE-02 versioned deploy when a human activates a SCHEDULED draft.

    On failure, return ok=False and do NOT claim a new rule version is live.
    The caller must refuse activate_amendment() in that case.
    """
    if draft.approval_state is not ApprovalState.SCHEDULED:
        return {
            "ok": False,
            "error": (
                f"Redeploy is only valid from SCHEDULED; got {draft.approval_state.value}."
            ),
        }
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        return {
            "ok": False,
            "error": f"OpenL zip missing at {zip_path}; refusing to activate stale rules.",
        }
    try:
        record = record_deploy(
            rule_family=f"amendment:{draft.id}",
            rule_ids=[c.rule_id for c in draft.changes] or ["unknown"],
            zip_path=zip_path,
            effective_from=(
                str(draft.changes[0].effective_from)
                if draft.changes and draft.changes[0].effective_from
                else "2011-04-01"
            ),
            module=draft.module,
            notes=f"amendment {draft.id} SCHEDULED→ACTIVE hook; zip immutable.",
        )
        return {"ok": True, "record": record.__dict__, "error": None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def activate_if_redeploy_succeeded(
    draft: AmendmentDraft,
    *,
    authorized_by: str,
    zip_path: Path = OPENL_ZIP,
):
    """Activate only after RULE-02 records a new immutable zip version."""
    from amendments import activate_amendment

    result = redeploy_on_activation(draft, zip_path=zip_path)
    if not result.get("ok"):
        raise RuntimeError(
            "Refusing ACTIVE transition because OpenL redeploy failed: "
            f"{result.get('error')}. Amendment stays SCHEDULED."
        )
    return activate_amendment(draft, authorized_by=authorized_by), result
