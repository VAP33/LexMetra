"""
Pipeline orchestration.

Two entry points:
  - ``run_pipeline_from_pages`` — operates on already-extracted PageText
    objects. This is what almost every unit test uses: it needs no PDF, no
    Tesseract, and lets tests target detection/segmentation/classification/
    extraction directly with synthetic text.
  - ``run_pipeline`` — the real entry point for a PDF file. Builds PageText
    objects via ``text_pipeline.build_pages`` (native text with OCR
    fallback, one page at a time) and then delegates to
    ``run_pipeline_from_pages``.

Semantic extraction v2
-----------------------
Rule-level text is no longer scanned as one undifferentiated block. Each
rule is first broken into clauses (``clause_segmentation.segment_clauses``),
each clause is given a semantic role (``semantic_roles.classify_clause`` +
``refine_roles_with_parent_context``), and only THEN is condition/
requirement/threshold/exception/effective-date extraction run — scoped to
that single clause's own text (``clause_extraction.py``). A deterministic
validation pass (``validation.py``) runs after extraction and directly
drives confidence and review_status.

The legacy flat fields on ``ExtractedRule`` (``conditions``, ``requirements``,
``thresholds``, ``exemptions``, ``effective_dates``) are retained for
backward compatibility with existing consumers (CLI output, UI, adapters)
but are now DERIVED from the clause-level structures below, filtered to
only the clauses whose semantic role makes that field meaningful — this is
what actually fixes the "Rule 2 / 4 litre" class of problem: a number
inside a DEFINITION clause never reaches the legacy ``thresholds`` list.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import classification, ocr_quality, rule_detection, segmentation, text_pipeline, validation
from . import llm_assist
from .clause_extraction import (
    extract_applies_to,
    extract_bound_thresholds,
    extract_clause_effective_date,
    extract_condition_info,
    extract_exception_info,
    extract_requirement_info,
)
from .clause_segmentation import ClauseSpan, segment_clauses
from .config import OcrConfig, resolve_ocr_config
from .extraction import derive_evidence_required
from .extraction.requirements import _guess_field as guess_canonical_field
from .models import (
    Clause,
    EffectiveDates,
    ExtractedRule,
    ExtractionCondition,
    ExtractionExemption,
    ExtractionRequirement,
    ExtractionThreshold,
    PageText,
    PipelineResult,
    ProvisionType,
    ReviewStatus,
    SemanticRole,
    SourceLocation,
)
from .provision_classification import (
    NON_SUBSTANTIVE_PROVISION_TYPES,
    classify_provision,
    is_substantive_provision,
    is_executable_provision,
    extract_amendment_target,
)
from .segmentation import RuleSpan

from .semantic_roles import classify_clause, refine_roles_with_parent_context

# The standard Indian legal-drafting convention is "Title.\u2014Text..."
# (period immediately followed by an em-dash, no space) — e.g. "Short
# title and commencement.\u2014These rules...". Checked first since it's
# the most reliable signal when present.
_DASH_TITLE_RE = re.compile(r"^(?P<title>[^\n]{3,150}?)\.\s*[\u2014\u2013]\s*")
# Fallback: an ordinary sentence-ending period followed by whitespace.
_PERIOD_TITLE_RE = re.compile(r"^(?P<title>[^.\n]{3,120}?)\.\s")

#: Roles whose `condition` sub-object is promoted into the rule's legacy
#: `conditions` list. A condition sentence physically inside a DEFINITION
#: or EXPLANATION clause is still visible under `clauses`, but is not
#: promoted — matching the same non-operative-clause discipline used for
#: thresholds.
_CONDITION_LEGACY_ROLES = {
    SemanticRole.CONDITION, SemanticRole.OBLIGATION, SemanticRole.PROHIBITION,
    SemanticRole.EXEMPTION, SemanticRole.EXCEPTION,
}
_REQUIREMENT_ROLES = {SemanticRole.OBLIGATION, SemanticRole.PROHIBITION}
_EXCEPTION_ROLES = {SemanticRole.EXCEPTION, SemanticRole.EXEMPTION}
_OPERATIVE_FOR_LAST_CLAUSE = {SemanticRole.OBLIGATION, SemanticRole.PROHIBITION}


def _guess_title(span: RuleSpan) -> Optional[str]:
    """
    Best-effort short title from the first line(s) of the rule body (the
    text immediately after "NUMBER. "). Never fabricated beyond what's in
    the text; None if nothing plausible is found.
    """
    lines = span.text.splitlines()
    lookahead = " ".join(lines[:3]) if lines else ""
    after_number = re.sub(r"^\s*\d{1,3}[A-Za-z]?\.\s+", "", lookahead)

    for pattern in (_DASH_TITLE_RE, _PERIOD_TITLE_RE):
        match = pattern.match(after_number)
        if match:
            title = match.group("title").strip(" .\u2014\u2013-")
            if len(title) >= 3:
                return title

    trimmed = after_number.strip()
    if len(trimmed) >= 3:
        return trimmed[:80].rsplit(" ", 1)[0] if len(trimmed) > 80 else trimmed
    return None


def _pages_for_clause(cspan: ClauseSpan, pages_by_no: Dict[int, PageText]) -> List[PageText]:
    return [
        pages_by_no[p] for p in range(cspan.page_start, cspan.page_end + 1)
        if p in pages_by_no
    ]


def _clause_ocr_quality(cspan: ClauseSpan, clause_pages: List[PageText]) -> Tuple[bool, float]:
    """
    Only penalizes text that actually came from OCR — a native PDF text
    layer using unusual (but correct) legal vocabulary should not be
    dragged down by a general-purpose dictionary check.
    """
    if not clause_pages or all(p.source.value == "native" for p in clause_pages):
        return False, 1.0
    word_score, _flagged = ocr_quality.assess_text_quality(cspan.text)
    page_confidence = sum(p.confidence for p in clause_pages) / len(clause_pages)
    combined = min(word_score, page_confidence)
    return combined < 0.85, round(combined, 3)


def _build_clause(
    cspan: ClauseSpan,
    role: SemanticRole,
    role_confidence: float,
    role_signals: List[str],
    *,
    rule_id: str,
    pages_by_no: Dict[int, PageText],
    built_by_id: Dict[str, Clause],
    inherited_note: bool,
    last_operative_clause_id: Optional[str],
    use_llm_assist: bool = False,
    ollama_base_url: str = llm_assist.DEFAULT_OLLAMA_URL,
    ollama_model: str = llm_assist.DEFAULT_OLLAMA_MODEL,
) -> Clause:
    clause_pages = _pages_for_clause(cspan, pages_by_no)
    ocr_flag, ocr_score = _clause_ocr_quality(cspan, clause_pages)

    condition = extract_condition_info(cspan) if role in _CONDITION_LEGACY_ROLES else None

    inherited_subject = None
    if inherited_note and cspan.parent_clause_id and cspan.parent_clause_id in built_by_id:
        parent = built_by_id[cspan.parent_clause_id]
        if parent.requirement:
            inherited_subject = parent.requirement.subject

    requirement = (
        extract_requirement_info(cspan, inherited_subject=inherited_subject)
        if role in _REQUIREMENT_ROLES else None
    )

    bound_thresholds, threshold_notes = extract_bound_thresholds(cspan, role)

    exception = (
        extract_exception_info(cspan, role, modifies_clause_id=last_operative_clause_id)
        if role in _EXCEPTION_ROLES else None
    )

    effective_date = extract_clause_effective_date(cspan, role)
    applies_to = extract_applies_to(cspan)

    clause = Clause(
        clause_id=cspan.clause_id,
        rule_id=rule_id,
        parent_clause_id=cspan.parent_clause_id,
        clause_type=cspan.clause_type,
        page_start=cspan.page_start,
        page_end=cspan.page_end,
        source_text=cspan.text,
        semantic_role=role,
        role_confidence=role_confidence,
        role_signals=role_signals,
        condition=condition,
        requirement=requirement,
        thresholds=bound_thresholds,
        exception=exception,
        effective_date=effective_date,
        applies_to=applies_to,
        ocr_quality_flag=ocr_flag,
        ocr_quality_score=ocr_score,
        validation_errors=[],
        validation_warnings=list(threshold_notes),
        confidence=0.0,
        review_status=ReviewStatus.NEEDS_REVIEW,
    )

    errors, warnings = validation.validate_clause(clause)
    clause.validation_errors = errors
    clause.validation_warnings = clause.validation_warnings + warnings

    error_penalty = min(0.7, 0.25 * len(errors) + 0.05 * len(clause.validation_warnings))
    base_confidence = 0.6 * role_confidence + 0.4 * ocr_score
    confidence = round(max(0.0, min(1.0, base_confidence - error_penalty)), 3)

    if errors:
        review_status = ReviewStatus.UNCERTAIN if confidence < 0.35 else ReviewStatus.NEEDS_REVIEW
    elif confidence >= 0.75 and role_confidence >= 0.7:
        review_status = ReviewStatus.AUTO_ACCEPTED
    elif confidence < 0.35:
        review_status = ReviewStatus.UNCERTAIN
    else:
        review_status = ReviewStatus.NEEDS_REVIEW

    clause.confidence = confidence
    clause.review_status = review_status

    # Optional advisory-only LLM layer: only consulted for a clause the
    # deterministic pipeline is already unsure about, and only ever
    # ATTACHED as metadata — it never changes semantic_role, confidence,
    # or review_status directly. See llm_assist.py for the grounding
    # validation that keeps this from inventing information.
    if use_llm_assist and role_confidence < 0.6:
        try:
            llm_result = llm_assist.query_clause(
                cspan.text, base_url=ollama_base_url, model=ollama_model
            )
        except Exception:
            llm_result = None
        if llm_result is not None:
            clause.llm_assist = {
                "suggested_semantic_role": llm_result.semantic_role,
                "suggested_requirement_subject": llm_result.requirement_subject,
                "suggested_requirement_action": llm_result.requirement_action,
                "suggested_applies_to": llm_result.applies_to,
                "llm_confidence": llm_result.confidence,
                "discarded_fields": llm_result.discarded_fields,
                "note": "advisory only — does not override deterministic extraction",
            }

    return clause


def _build_clauses_for_rule(
    span: RuleSpan,
    rule_id: str,
    pages_by_no: Dict[int, PageText],
    *,
    use_llm_assist: bool = False,
    ollama_base_url: str = llm_assist.DEFAULT_OLLAMA_URL,
    ollama_model: str = llm_assist.DEFAULT_OLLAMA_MODEL,
) -> List[Clause]:
    cspans = segment_clauses(span)
    if not cspans:
        return []

    raw_entries = [(cspan,) + classify_clause(cspan) for cspan in cspans]
    refined_entries = refine_roles_with_parent_context(raw_entries)

    built: List[Clause] = []
    built_by_id: Dict[str, Clause] = {}
    last_operative_clause_id: Optional[str] = None

    for cspan, role, role_confidence, role_signals in refined_entries:
        inherited_note = any(s.startswith("reclassified") for s in role_signals)
        clause = _build_clause(
            cspan, role, role_confidence, role_signals,
            rule_id=rule_id,
            pages_by_no=pages_by_no,
            built_by_id=built_by_id,
            inherited_note=inherited_note,
            last_operative_clause_id=last_operative_clause_id,
            use_llm_assist=use_llm_assist,
            ollama_base_url=ollama_base_url,
            ollama_model=ollama_model,
        )
        built.append(clause)
        built_by_id[clause.clause_id] = clause
        if role in _OPERATIVE_FOR_LAST_CLAUSE:
            last_operative_clause_id = clause.clause_id

    return built


def _aggregate_legacy_fields(clauses: List[Clause]) -> dict:
    """
    Derive the backward-compatible flat fields from the clause-level
    structures, applying the same non-operative-clause filtering already
    enforced at threshold-extraction time (see clause_extraction.py).
    """
    conditions: List[ExtractionCondition] = []
    requirements: List[ExtractionRequirement] = []
    thresholds: List[ExtractionThreshold] = []
    exemptions: List[ExtractionExemption] = []
    effective_dates = EffectiveDates()

    for clause in clauses:
        if clause.condition is not None:
            conditions.append(
                ExtractionCondition(
                    condition_text=clause.condition.condition_text,
                    condition_type=clause.condition.condition_type,
                    source_text=clause.condition.condition_text,
                )
            )
        if clause.requirement is not None:
            requirements.append(
                ExtractionRequirement(
                    id=clause.clause_id,
                    description=clause.requirement.requirement_text,
                    suggested_field=guess_canonical_field(clause.requirement.requirement_text),
                    condition_ref=None,
                    source_text=clause.requirement.requirement_text,
                )
            )
        for t in clause.thresholds:
            thresholds.append(
                ExtractionThreshold(
                    value=t.value,
                    unit=t.unit,
                    operator=t.operator,
                    label=t.applies_to,  # repurposed: what the threshold applies to
                    source_text=t.source_text,
                )
            )
        if clause.exception is not None:
            exemptions.append(
                ExtractionExemption(
                    description=clause.exception.description,
                    condition_text=clause.exception.condition_text,
                    effective_from=None,
                    source_text=clause.exception.description,
                )
            )
        if (
            clause.effective_date is not None
            and effective_dates.effective_from is None
            and effective_dates.effective_to is None
        ):
            effective_dates = clause.effective_date

    return {
        "conditions": conditions,
        "requirements": requirements,
        "thresholds": thresholds,
        "exemptions": exemptions,
        "effective_dates": effective_dates,
    }


def _build_rule(
    span: RuleSpan,
    *,
    document_id: str,
    source: str,
    version: Optional[str],
    pages_by_no: Dict[int, PageText],
    document_metadata: Optional[Any] = None,
    secondary_hindi_text: Optional[str] = None,
    use_llm_assist: bool = False,
    ollama_base_url: str = llm_assist.DEFAULT_OLLAMA_URL,
    ollama_model: str = llm_assist.DEFAULT_OLLAMA_MODEL,
    prebuilt_clauses: Optional[List[Clause]] = None,
) -> ExtractedRule:
    classification_result = classification.classify(span.text)
    title = _guess_title(span)
    source_location = segmentation.to_source_location(document_id, span)

    clauses = prebuilt_clauses if prebuilt_clauses is not None else _build_clauses_for_rule(
        span, span.raw_number, pages_by_no,
        use_llm_assist=use_llm_assist, ollama_base_url=ollama_base_url, ollama_model=ollama_model,
    )
    legacy = _aggregate_legacy_fields(clauses)
    evidence_required = derive_evidence_required(legacy["requirements"], legacy["conditions"])

    span_pages = [
        pages_by_no[p] for p in range(span.page_start, span.page_end + 1)
        if p in pages_by_no
    ]
    text_confidence = (
        sum(p.confidence for p in span_pages) / len(span_pages) if span_pages else 0.5
    )

    rule_validation_errors: List[str] = []
    rule_validation_warnings: List[str] = []
    for clause in clauses:
        rule_validation_errors.extend(clause.validation_errors)
        rule_validation_warnings.extend(clause.validation_warnings)
    if not clauses:
        rule_validation_warnings.append("no clauses could be segmented from this rule's text")

    mean_clause_confidence = (
        sum(c.confidence for c in clauses) / len(clauses) if clauses else 0.3
    )

    base_confidence = (
        0.35 * mean_clause_confidence
        + 0.30 * classification_result.confidence
        + 0.35 * text_confidence
    )
    error_penalty = min(0.6, 0.12 * len(rule_validation_errors) + 0.03 * len(rule_validation_warnings))
    extraction_confidence = round(max(0.0, min(1.0, base_confidence - error_penalty)), 3)

    review_reasons: List[str] = []
    if classification_result.review_status != ReviewStatus.AUTO_ACCEPTED:
        review_reasons.append("category classification is not auto-accepted")
    if text_confidence < 0.75:
        review_reasons.append(
            f"underlying page text confidence is low ({text_confidence:.2f}); "
            "likely OCR on a degraded scan"
        )
    if not legacy["requirements"] and not legacy["conditions"] and not legacy["exemptions"]:
        review_reasons.append("no requirements, conditions, or exemptions were extracted")
    if rule_validation_errors:
        review_reasons.append(f"{len(rule_validation_errors)} validation error(s) found — see validation_errors")
    if rule_validation_warnings:
        review_reasons.append(f"{len(rule_validation_warnings)} validation warning(s) found — see validation_warnings")

    if rule_validation_errors:
        review_status = ReviewStatus.UNCERTAIN if extraction_confidence < 0.35 else ReviewStatus.NEEDS_REVIEW
    elif extraction_confidence >= 0.75 and not review_reasons:
        review_status = ReviewStatus.AUTO_ACCEPTED
    elif extraction_confidence < 0.35:
        review_status = ReviewStatus.UNCERTAIN
    else:
        review_status = ReviewStatus.NEEDS_REVIEW

    if secondary_hindi_text:
        raw_ocr_text = f"[HINDI TEXT]\n{secondary_hindi_text}\n\n[ENGLISH TEXT]\n{span.text}"
    else:
        raw_ocr_text = "\n".join(p.text for p in span_pages if p.source.value == "ocr") or None

    eff_dates = legacy["effective_dates"]
    if eff_dates.effective_from is None and document_metadata and document_metadata.effective_date:
        eff_dates = EffectiveDates(
            effective_from=document_metadata.effective_date.isoformat(),
            effective_from_raw="date of publication in Official Gazette",
            effective_from_source_text="date of publication in Official Gazette",
        )

    # Classify whole rule provision type
    top_ptype, _ = classify_provision(span.text, reference=span.raw_number)
    top_is_substantive = is_substantive_provision(
        top_ptype,
        text=span.text,
        reference=span.raw_number,
        amendment=False,
    )

    return ExtractedRule(
        rule_id=span.raw_number,
        rule_id_confidence=1.0,  # segmentation only runs on already-accepted candidates
        title=title,
        source=source,
        document_id=document_id,
        version=version,
        classification=classification_result,
        scope=None,
        conditions=legacy["conditions"],
        requirements=legacy["requirements"],
        thresholds=legacy["thresholds"],
        exemptions=legacy["exemptions"],
        effective_dates=eff_dates,
        evidence_required=evidence_required,
        clauses=clauses,
        validation_errors=rule_validation_errors,
        validation_warnings=rule_validation_warnings,
        text=span.text,
        source_location=source_location,
        raw_ocr_text=raw_ocr_text,
        extraction_confidence=extraction_confidence,
        review_status=review_status,
        review_reasons=review_reasons,
        provision_type=top_ptype,
        is_substantive=top_is_substantive,
        source_provision=f"Rule {span.raw_number}" if not str(span.raw_number).startswith("Rule ") else span.raw_number,
        metadata_sources={
            "effective_from": {
                "value": document_metadata.effective_date.isoformat() if document_metadata and document_metadata.effective_date else None,
                "source_provision": getattr(document_metadata, "commencement_source_provision", "Rule 1(2)") or "Rule 1(2)",
            }
        } if document_metadata and document_metadata.effective_date else {},
    )


def _build_rules_from_span(
    span: RuleSpan,
    *,
    document_id: str,
    source: str,
    version: Optional[str],
    pages_by_no: Dict[int, PageText],
    document_metadata: Optional[Any] = None,
    secondary_hindi_text: Optional[str] = None,
    use_llm_assist: bool = False,
    ollama_base_url: str = llm_assist.DEFAULT_OLLAMA_URL,
    ollama_model: str = llm_assist.DEFAULT_OLLAMA_MODEL,
    is_amendment_doc: bool = False,
) -> List[ExtractedRule]:
    """
    Build one or more canonical ExtractedRule objects from a RuleSpan.
    For amendment documents, non-substantive provisions (SHORT_TITLE, COMMENCEMENT)
    are filtered out (yielding 0 rules), while nested substantive provisions
    (e.g. Rule 2(a)(i), 2(a)(ii), 2(a)(iii), 2(b)) are extracted at granular legal unit level.
    """
    clauses = _build_clauses_for_rule(
        span, span.raw_number, pages_by_no,
        use_llm_assist=use_llm_assist, ollama_base_url=ollama_base_url, ollama_model=ollama_model,
    )

    # Classify each clause's functional provision type
    for clause in clauses:
        ptype, pconf = classify_provision(
            clause.source_text,
            reference=clause.clause_id,
        )
        clause.provision_type = ptype
        clause.is_substantive = is_substantive_provision(
            ptype,
            text=clause.source_text,
            reference=clause.clause_id,
            amendment=is_amendment_doc,
        )

        # Structural metadata is never an executable amendment rule, even
        # when the classifier/semantic-role layer marks it OTHER.
        if clause.clause_type.value in {"table", "explanation"}:
            clause.is_substantive = False

    # In amendment documents:
    # If all clauses in this span are non-substantive (e.g. Rule 1 with 1(1) SHORT_TITLE and 1(2) COMMENCEMENT):
    if is_amendment_doc and clauses and all(not c.is_substantive for c in clauses):
        return []

    # Check for nested substantive leaf clauses
    container_ids = {c.parent_clause_id for c in clauses if c.parent_clause_id}
    leaf_clauses = [c for c in clauses if c.clause_id not in container_ids]
    substantive_leaves = [c for c in leaf_clauses if c.is_substantive]

    if is_amendment_doc and len(substantive_leaves) > 1:
        results: List[ExtractedRule] = []
        span_pages = [
            pages_by_no[p] for p in range(span.page_start, span.page_end + 1)
            if p in pages_by_no
        ]
        text_confidence = (
            sum(p.confidence for p in span_pages) / len(span_pages) if span_pages else 0.5
        )

        eff_date_val = None
        if document_metadata and document_metadata.effective_date:
            eff_date_val = document_metadata.effective_date.isoformat()

        commencement_src = (
            getattr(document_metadata, "commencement_source_provision", "Rule 1(2)")
            if document_metadata else "Rule 1(2)"
        ) or "Rule 1(2)"

        for leaf in substantive_leaves:
            prov_ref = f"Rule {leaf.clause_id}" if not leaf.clause_id.startswith("Rule ") else leaf.clause_id

            conditions: List[ExtractionCondition] = []
            if leaf.condition:
                conditions.append(
                    ExtractionCondition(
                        condition_text=leaf.condition.condition_text,
                        condition_type=leaf.condition.condition_type,
                        source_text=leaf.condition.condition_text,
                    )
                )

            requirements: List[ExtractionRequirement] = []
            if leaf.requirement:
                requirements.append(
                    ExtractionRequirement(
                        id=leaf.clause_id,
                        description=leaf.requirement.requirement_text,
                        suggested_field=guess_canonical_field(leaf.requirement.requirement_text),
                        source_text=leaf.requirement.requirement_text,
                    )
                )
            elif leaf.source_text:
                requirements.append(
                    ExtractionRequirement(
                        id=leaf.clause_id,
                        description=leaf.source_text.strip(),
                        suggested_field=guess_canonical_field(leaf.source_text),
                        source_text=leaf.source_text.strip(),
                    )
                )

            thresholds: List[ExtractionThreshold] = [
                ExtractionThreshold(
                    value=t.value,
                    unit=t.unit,
                    operator=t.operator,
                    label=t.applies_to,
                    source_text=t.source_text,
                )
                for t in leaf.thresholds
            ]

            exemptions: List[ExtractionExemption] = []
            if leaf.exception:
                exemptions.append(
                    ExtractionExemption(
                        description=leaf.exception.description,
                        condition_text=leaf.exception.condition_text,
                        source_text=leaf.exception.description,
                    )
                )

            eff_dates = EffectiveDates(
                effective_from=eff_date_val,
                effective_from_raw="date of publication in Official Gazette",
                effective_from_source_text=commencement_src,
            ) if eff_date_val else leaf.effective_date or EffectiveDates()

            class_res = classification.classify(leaf.source_text)

            meta_sources = {
                "effective_from": {
                    "value": eff_date_val,
                    "source_provision": commencement_src,
                },
                "version": {
                    "value": version,
                    "source_provision": "Rule 1(1)",
                },
                "notification": {
                    "value": getattr(document_metadata, "notification_number", None),
                    "source_provision": "Gazette Notification Header",
                },
            }

            raw_ocr = None
            if secondary_hindi_text:
                raw_ocr = f"[HINDI TEXT]\n{secondary_hindi_text}\n\n[ENGLISH TEXT]\n{leaf.source_text}"
            else:
                raw_ocr = "\n".join(p.text for p in span_pages if p.source.value == "ocr") or None

            # Derive amendment target (e.g. "Rule 6(1)(a)") from the clause
            # text itself, and keep the amending document's own positional
            # marker (e.g. "(i)") separately as amendment_item.
            _tgt = extract_amendment_target(leaf.source_text)
            # amendment_item: last parenthesised component of the clause_id
            _item_m = re.search(r"(\([^)]+\))$", leaf.clause_id)
            _item = _item_m.group(1) if _item_m else f"({leaf.clause_id})"

            rule_obj = ExtractedRule(
                rule_id=prov_ref,
                rule_id_confidence=1.0,
                title=prov_ref,
                source=source,
                document_id=document_id,
                version=version,
                classification=class_res,
                scope=None,
                conditions=conditions,
                requirements=requirements,
                thresholds=thresholds,
                exemptions=exemptions,
                effective_dates=eff_dates,
                evidence_required=derive_evidence_required(requirements, conditions),
                clauses=[leaf],
                validation_errors=leaf.validation_errors,
                validation_warnings=leaf.validation_warnings,
                text=leaf.source_text,
                source_location=SourceLocation(
                    document_id=document_id,
                    page_start=leaf.page_start,
                    page_end=leaf.page_end,
                    clause=leaf.clause_id,
                ),
                raw_ocr_text=raw_ocr,
                extraction_confidence=max(0.75, leaf.confidence),
                review_status=ReviewStatus.AUTO_ACCEPTED if not leaf.validation_errors else ReviewStatus.NEEDS_REVIEW,
                review_reasons=[],
                provision_type=leaf.provision_type or ProvisionType.SUBSTANTIVE_AMENDMENT,
                is_substantive=True,
                source_provision=prov_ref,
                metadata_sources=meta_sources,
                amendment_target=_tgt,
                amendment_item=_item,
            )
            results.append(rule_obj)
        return results

    # Standard fallback: build the whole-rule ExtractedRule (preserves non-amendment regulations)
    single_rule = _build_rule(
        span,
        document_id=document_id,
        source=source,
        version=version,
        pages_by_no=pages_by_no,
        document_metadata=document_metadata,
        secondary_hindi_text=secondary_hindi_text,
        use_llm_assist=use_llm_assist,
        ollama_base_url=ollama_base_url,
        ollama_model=ollama_model,
        prebuilt_clauses=clauses,
    )
    # In amendment documents, try to extract the target rule and amendment item
    # from the span text even in the single-leaf case.
    if is_amendment_doc and single_rule is not None:
        _tgt = extract_amendment_target(span.text)
        _item_m = re.search(r"(\([^)]+\))$", span.raw_number or "")
        _item = _item_m.group(1) if _item_m else span.raw_number or None
        single_rule = single_rule.model_copy(update={
            "amendment_target": _tgt,
            "amendment_item": _item,
        })

    return [single_rule]



def run_pipeline_from_pages(
    pages: List[PageText],
    *,
    document_id: str,
    source: str,
    version: Optional[str] = None,
    page_range: Optional[List[int]] = None,
    max_rule_number: int = rule_detection.DEFAULT_MAX_RULE_NUMBER,
    accept_threshold: float = rule_detection.ACCEPT_THRESHOLD,
    use_llm_assist: bool = False,
    ollama_base_url: str = llm_assist.DEFAULT_OLLAMA_URL,
    ollama_model: str = llm_assist.DEFAULT_OLLAMA_MODEL,
) -> PipelineResult:
    from .amendment_metadata import extract_amendment_metadata

    doc_text = "\n".join(p.text for p in pages)
    amendment_meta = extract_amendment_metadata(doc_text)

    is_amendment_doc = bool(
        amendment_meta.amendment_name
        or (amendment_meta.full_title and "amendment" in amendment_meta.full_title.lower())
        or ("further to amend" in doc_text.lower())
        or ("का और संशोधन करने के लिए" in doc_text)
    )

    effective_version = version or amendment_meta.version_label
    effective_source = source
    if (source == "IN-LMPC-2011" or not source) and amendment_meta.regulation:
        effective_source = amendment_meta.regulation

    candidates = rule_detection.detect_headings(
        pages, max_rule_number=max_rule_number, accept_threshold=accept_threshold
    )
    spans = segmentation.segment_rules(pages, candidates)
    pages_by_no = {p.page_no: p for p in pages}

    # Bilingual deduplication: group spans by raw_number
    def _is_devanagari(text: str) -> bool:
        return len(re.findall(r"[\u0900-\u097F]", text)) > 5

    spans_by_num: Dict[str, List[segmentation.RuleSpan]] = {}
    for s in spans:
        spans_by_num.setdefault(s.raw_number, []).append(s)

    merged_span_items: List[Tuple[segmentation.RuleSpan, Optional[str]]] = []
    for num, group in spans_by_num.items():
        if len(group) == 1:
            merged_span_items.append((group[0], None))
        else:
            hi_spans = [s for s in group if _is_devanagari(s.text)]
            en_spans = [s for s in group if not _is_devanagari(s.text)]
            if hi_spans and en_spans:
                # Deduplicate into single logical rule, keeping English as operative
                primary_en = en_spans[0]
                secondary_hi = "\n".join(s.text for s in hi_spans)
                merged_span_items.append((primary_en, secondary_hi))
            else:
                for s in group:
                    merged_span_items.append((s, None))

    rules: List[ExtractedRule] = []
    for span, hi_text in merged_span_items:
        span_rules = _build_rules_from_span(
            span,
            document_id=document_id,
            source=effective_source,
            version=effective_version,
            pages_by_no=pages_by_no,
            document_metadata=amendment_meta,
            secondary_hindi_text=hi_text,
            use_llm_assist=use_llm_assist,
            ollama_base_url=ollama_base_url,
            ollama_model=ollama_model,
            is_amendment_doc=is_amendment_doc,
        )
        rules.extend(span_rules)

    rejected_count = sum(1 for c in candidates if not c.accepted)

    warnings: List[str] = []
    for page in pages:
        warnings.extend(f"page {page.page_no}: {w}" for w in page.warnings)

    meta_dict = amendment_meta.to_dict()
    if is_amendment_doc:
        meta_dict["context_provisions"] = {
            "Rule 1(1)": {
                "provision_type": "SHORT_TITLE",
                "title": amendment_meta.full_title,
                "version": effective_version,
                "is_substantive": False,
            },
            "Rule 1(2)": {
                "provision_type": "COMMENCEMENT",
                "effective_from": amendment_meta.effective_date.isoformat() if amendment_meta.effective_date else None,
                "commencement_source": amendment_meta.commencement_source_provision or "Rule 1(2)",
                "is_substantive": False,
            },
        }

    return PipelineResult(
        document_id=document_id,
        source=effective_source,
        page_range=page_range,
        pages=pages,
        candidates=candidates,
        rules=rules,
        rejected_count=rejected_count,
        warnings=warnings,
        metadata=meta_dict,
    )



def run_pipeline(
    pdf_path: str | Path,
    *,
    document_id: str,
    source: str,
    version: Optional[str] = None,
    start: Optional[int] = None,
    end: Optional[int] = None,
    lang: str = "eng",
    dpi: int = 300,
    psm: int = 6,
    force_ocr: bool = False,
    explicit_tesseract_cmd: Optional[str] = None,
    max_rule_number: int = rule_detection.DEFAULT_MAX_RULE_NUMBER,
    accept_threshold: float = rule_detection.ACCEPT_THRESHOLD,
    preprocess_ocr: bool = True,
    use_llm_assist: bool = False,
    ollama_base_url: str = llm_assist.DEFAULT_OLLAMA_URL,
    ollama_model: str = llm_assist.DEFAULT_OLLAMA_MODEL,
) -> PipelineResult:
    ocr_config: OcrConfig = resolve_ocr_config(
        lang=lang, dpi=dpi, psm=psm, explicit_tesseract_cmd=explicit_tesseract_cmd,
    )
    pages = text_pipeline.build_pages(
        pdf_path, ocr_config, start=start, end=end, force_ocr=force_ocr, preprocess=preprocess_ocr,
    )
    page_range = [start, end] if (start is not None or end is not None) else None
    return run_pipeline_from_pages(
        pages,
        document_id=document_id,
        source=source,
        version=version,
        page_range=page_range,
        max_rule_number=max_rule_number,
        accept_threshold=accept_threshold,
        use_llm_assist=use_llm_assist,
        ollama_base_url=ollama_base_url,
        ollama_model=ollama_model,
    )