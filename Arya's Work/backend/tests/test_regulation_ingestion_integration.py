"""
Integration tests for backend/regulation_ingestion.py -- the glue between
Module 1 (backend/lexmetra_rules) and the pre-existing amendment lifecycle
(models.AmendmentDraft / amendments.py).

These do not touch a real database: db.persistence.save_amendment_draft is
monkeypatched so this file exercises the pipeline + adapter + schema-gap
patching + lifecycle transitions in isolation.
"""

from __future__ import annotations

from pathlib import Path

from models import ApprovalState
from amendments import activate_amendment, transition_amendment
import db.persistence as persistence
import regulation_ingestion as ri

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _synthetic_pdf(tmp_path: Path, monkeypatch) -> Path:
    from tests.fixtures.pdf_builder import build_native_text_pdf

    text = (
        "3. Applicability.--(1) The provisions of rule 6 shall not apply "
        "to any package if the net weight or measure of the commodity does "
        "not exceed 25 kg.\n"
    )
    path = tmp_path / "reg.pdf"
    build_native_text_pdf(path, [text])
    return path


def test_ingest_regulation_pdf_produces_extracted_draft(tmp_path, monkeypatch):
    saved = {}
    monkeypatch.setattr(
        persistence, "save_amendment_draft",
        lambda draft, created_by=None: saved.update(draft=draft, created_by=created_by),
    )

    pdf_path = _synthetic_pdf(tmp_path, monkeypatch)
    result = ri.ingest_regulation_pdf(pdf_path, source_document_id="doc-1", created_by="alice")

    assert result.rule_count >= 1
    assert result.draft.approval_state == ApprovalState.EXTRACTED
    assert saved["draft"] is result.draft
    assert saved["created_by"] == "alice"


def test_ingest_missing_pdf_raises_ingestion_error(monkeypatch):
    monkeypatch.setattr(persistence, "save_amendment_draft", lambda *a, **k: None)
    try:
        ri.ingest_regulation_pdf("/no/such/file.pdf")
        assert False, "expected RegulationIngestionError"
    except ri.RegulationIngestionError:
        pass


def test_rule_versions_missing_effective_date_get_a_flagged_provisional_date(tmp_path, monkeypatch):
    """
    backend/models.py's RuleVersion.effective_from is a REQUIRED field, but
    Module 1 leaves it unset when no date is discoverable in the source
    text. The integration layer must fill it with a clearly-flagged
    provisional value (the ingestion date) rather than fail, or invent an
    undisclosed legal date.
    """
    monkeypatch.setattr(persistence, "save_amendment_draft", lambda *a, **k: None)
    pdf_path = _synthetic_pdf(tmp_path, monkeypatch)
    result = ri.ingest_regulation_pdf(pdf_path, source_document_id="doc-2")

    for version in result.draft.proposed_rule_versions:
        assert version.effective_from is not None
        if "PROVISIONAL" in (version.text or ""):
            assert "reviewer" in version.text.lower()


def test_full_amendment_lifecycle_extracted_to_active(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "save_amendment_draft", lambda *a, **k: None)
    pdf_path = _synthetic_pdf(tmp_path, monkeypatch)
    draft = ri.ingest_regulation_pdf(pdf_path, source_document_id="doc-3").draft

    assert draft.approval_state == ApprovalState.EXTRACTED
    draft = transition_amendment(draft, ApprovalState.PENDING_REVIEW)
    draft = transition_amendment(draft, ApprovalState.APPROVED)
    draft = transition_amendment(draft, ApprovalState.SCHEDULED)
    draft = activate_amendment(draft, authorized_by="reviewer-1")
    assert draft.approval_state == ApprovalState.ACTIVE


def test_activation_is_rejected_before_scheduled(tmp_path, monkeypatch):
    """A draft may never jump straight to ACTIVE -- this is the exact
    invariant that keeps an ingested-but-unreviewed rule out of current
    compliance evaluation."""
    monkeypatch.setattr(persistence, "save_amendment_draft", lambda *a, **k: None)
    pdf_path = _synthetic_pdf(tmp_path, monkeypatch)
    draft = ri.ingest_regulation_pdf(pdf_path, source_document_id="doc-4").draft

    try:
        activate_amendment(draft, authorized_by="someone")
        assert False, "expected activation to be rejected before SCHEDULED"
    except ValueError:
        pass


def test_invalid_transition_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "save_amendment_draft", lambda *a, **k: None)
    pdf_path = _synthetic_pdf(tmp_path, monkeypatch)
    draft = ri.ingest_regulation_pdf(pdf_path, source_document_id="doc-5").draft

    try:
        transition_amendment(draft, ApprovalState.ACTIVE)
        assert False, "EXTRACTED -> ACTIVE must never be a direct transition"
    except ValueError:
        pass

