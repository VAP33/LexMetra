"""
Regulation ingestion integration layer.

Connects the Module 1 regulation-ingestion pipeline (backend/lexmetra_rules)
to the pre-existing, previously-unwired amendment lifecycle
(backend/models.py's AmendmentDraft/RuleVersion + backend/amendments.py's
transition_amendment/activate_amendment + backend/db/persistence.py).

    PDF -> lexmetra_rules.pipeline.run_pipeline()          (OCR/extraction)
        -> lexmetra_rules.adapters.to_amendment_draft()    (shape adapter)
        -> _patch_for_backend_models()                     (THIS FILE: closes
                                                              the schema gap
                                                              between Module
                                                              1's output and
                                                              backend/models.py's
                                                              required fields)
        -> models.AmendmentDraft(**patched)                (validated)
        -> db.persistence.save_amendment_draft()           (persisted)

A draft created here starts in APPROVAL_STATE=EXTRACTED. It NEVER
participates in current compliance evaluation until a human reviewer moves
it through pending_review -> approved -> scheduled -> active (see
amendments.transition_amendment / activate_amendment) AND its resulting
rule versions are picked up by regulatory/runtime.apply_rule_versions. This
module only ever creates DRAFTS.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import db.persistence as persistence
from lexmetra_rules.adapters import to_amendment_draft
from lexmetra_rules.pipeline import run_pipeline
from models import AmendmentDraft


class RegulationIngestionError(Exception):
    """Raised when a PDF cannot be ingested at all (not found, unreadable,
    zero rules extracted). Never raised for 'the rules need review' --
    that is the normal, expected outcome and is not an error."""


@dataclass
class IngestionResult:
    draft: AmendmentDraft
    page_count: int
    rule_count: int
    rejected_count: int
    needs_review_count: int


def _patch_for_backend_models(
    raw_draft: Dict[str, Any],
    *,
    ingested_at: datetime,
) -> Dict[str, Any]:
    """
    Close the schema gap between Module 1's adapter output (which
    deliberately leaves ``id``/``extracted_at`` unset, per-rule-version
    ``effective_from`` unset when the source text had no discoverable date,
    and per-rule-version ``version`` unset when the source text had no
    discoverable version/amendment label) and backend/models.py's stricter
    requirements (``AmendmentDraft.id``, ``.extracted_at``, and every
    ``RuleVersion.id``/``.effective_from``/``.version`` are REQUIRED,
    non-optional, non-null fields).

    Nothing here invents a legal fact: where Module 1 could not determine an
    effective date, or a version/amendment label, from the document text,
    this assigns an explicit, clearly-provisional placeholder (never a
    guessed regulatory date or a guessed amendment label) and records that
    fact in the rule version's own ``text`` field so a human reviewer sees
    it plainly before ever approving the draft. A draft in this state
    cannot reach ACTIVE without a reviewer explicitly setting a real
    effective date/version (see amendments.py's review workflow) -- see
    'Remaining limitations' in the integration write-up.
    """
    patched = dict(raw_draft)
    patched["id"] = raw_draft.get("id") or str(uuid.uuid4())
    patched["extracted_at"] = raw_draft.get("extracted_at") or ingested_at

    provisional_date = ingested_at.date()
    UNVERIFIED_VERSION = "UNVERIFIED - no version/amendment label found in source text"
    patched_versions: List[Dict[str, Any]] = []
    for version in raw_draft.get("proposed_rule_versions", []):
        v = dict(version)
        v["id"] = v.get("id") or str(uuid.uuid4())
        notes = []
        if not v.get("effective_from"):
            v["effective_from"] = provisional_date
            notes.append(
                f"[PROVISIONAL: no effective date was found in the source text; "
                f"defaulted to the ingestion date {provisional_date.isoformat()}. "
                "A reviewer MUST confirm or correct this date before this rule "
                "version can be approved/activated.]"
            )
        elif isinstance(v["effective_from"], str):
            try:
                v["effective_from"] = date.fromisoformat(v["effective_from"])
            except ValueError:
                pass

        if not v.get("version"):
            v["version"] = UNVERIFIED_VERSION
            notes.append(
                "[PROVISIONAL: no version/amendment label was found in the "
                "source text; the placeholder '" + UNVERIFIED_VERSION + "' was "
                "used instead of inventing one. A reviewer MUST confirm or "
                "correct the version label before this rule version can be "
                "approved/activated.]"
            )
        if notes:
            v["text"] = " ".join(notes) + " " + (v.get("text") or "")
        patched_versions.append(v)
    patched["proposed_rule_versions"] = patched_versions

    return patched


def ingest_regulation_pdf(
    pdf_path: str | Path,
    *,
    source_document_id: Optional[str] = None,
    regulation: str = "IN-LMPC-2011",
    module: str = "lmpc",
    version: Optional[str] = None,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    force_ocr: bool = False,
    created_by: Optional[str] = None,
) -> IngestionResult:
    """
    Run the full Module 1 pipeline on ``pdf_path`` and persist the result as
    a new AmendmentDraft (approval_state=EXTRACTED). Never raises on "some
    rules need review" -- only on a genuine processing failure.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise RegulationIngestionError(f"PDF not found: {pdf_path}")

    document_id = source_document_id or pdf_path.stem

    try:
        result = run_pipeline(
            str(pdf_path),
            document_id=document_id,
            source=regulation,
            version=version,
            start=start_page,
            end=end_page,
            force_ocr=force_ocr,
        )
    except Exception as exc:  # pragma: no cover - defensive; pipeline has its own error types
        raise RegulationIngestionError(f"Regulation ingestion pipeline failed: {exc}") from exc

    raw_draft = to_amendment_draft(
        result.rules,
        source_document_id=document_id,
        module=module,
        metadata=getattr(result, "metadata", None),
    )
    ingested_at = datetime.now(timezone.utc)
    patched = _patch_for_backend_models(raw_draft, ingested_at=ingested_at)

    draft = AmendmentDraft(**patched)
    persistence.save_amendment_draft(draft, created_by=created_by)

    needs_review = sum(
        1 for r in result.rules if getattr(r.review_status, "value", r.review_status) != "auto_accepted"
    )
    return IngestionResult(
        draft=draft,
        page_count=len(result.pages),
        rule_count=len(result.rules),
        rejected_count=result.rejected_count,
        needs_review_count=needs_review,
    )