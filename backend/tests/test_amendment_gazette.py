from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from amendment_gazette import (
    activate_if_redeploy_succeeded,
    diff_against_rules_json,
    extract_rule_mentions,
    ocr_gazette_image,
    redeploy_on_activation,
)
from amendments import transition_amendment
from models import AmendmentChange, AmendmentDraft, ApprovalState
import pytest


def test_rule_mentions_and_diff_do_not_claim_verification():
    text = "G.S.R. amendment of Rule 6 and Rule 26 of the Packaged Commodities Rules."
    mentions = extract_rule_mentions(text)
    assert "Rule 6" in mentions
    result = diff_against_rules_json(text)
    assert result["engine"] == "tesseract_interim"
    assert "needs_official_verification" in result["note"]


def test_failed_redeploy_refuses_active(tmp_path):
    draft = AmendmentDraft(
        id="amd-1",
        module="lmpc",
        source_document_id="gazette-1",
        approval_state=ApprovalState.SCHEDULED,
        extracted_at=datetime.utcnow(),
        changes=[AmendmentChange(rule_id="LMPC-2011-R3-SCOPE", change_type="threshold")],
    )
    missing = tmp_path / "nope.zip"
    result = redeploy_on_activation(draft, zip_path=missing)
    assert result["ok"] is False
    with pytest.raises(RuntimeError, match="Refusing ACTIVE"):
        activate_if_redeploy_succeeded(draft, authorized_by="reviewer", zip_path=missing)
    assert draft.approval_state is ApprovalState.SCHEDULED
    with pytest.raises(ValueError):
        transition_amendment(draft, ApprovalState.ACTIVE)


def test_ocr_gazette_image_does_not_crash():
    img = Image.new("RGB", (200, 80), "white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), "Rule 6", fill="black")
    text = ocr_gazette_image(img)
    assert isinstance(text, str)
