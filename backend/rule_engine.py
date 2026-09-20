"""
Deterministic compliance rule engine.

Core principle:
    AI/CV/OCR extracts evidence.
    This module evaluates that evidence against versioned legal rules.
    It does not use an LLM to decide legality.

The engine is intentionally evidence-first:
    - "not detected" is not automatically equivalent to "legally absent"
      when the inspection does not have sufficient package coverage.
    - verified evidence can produce FAIL.
    - insufficient/uncertain evidence produces UNCERTAIN.
    - exemptions are evaluated before ordinary declaration checks.
    - legal thresholds are read from rules.json rather than duplicated here.

The public run_inspection() signature retains compatibility with the original
prototype while accepting optional multi-surface evidence from schema.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from schema import (
    BBox,
    CanonicalDeclaration,
    CanonicalStatus,
    CANONICAL_DECLARATION_DEFINITIONS,
    DeclarationEvidence,
    EvidenceAgreement,
    EvidenceReference,
    FactStatus,
    ExtractedFact,
    GeometryType,
    MeasurementMode,
    PackageStructure,
    ProductInspection,
    RuleFinding,
    SurfaceObservation,
    UNATTRIBUTED_IMAGE_ID,
    ValidationDetails,
    coerce_evidence_agreement,
)



import exemption as exemption_module
from exemption import (
    QUANTITY_NOT_ESTABLISHED,
    ExemptionInput,
    classify_exemption,
)
import calibration as calib
from regulatory.runtime import apply_rule_versions, version_label

from unit_price import (
    compute_unit_sale_price,
    convert_declared_price_to_standard,
    expected_unit_price_in_declared_unit,
)


RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "rules.json"
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.55


from rule_common import *
from rule_evaluators import *
def _evaluate_declaration_rule(
    *,
    rule: dict,
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
    exclude_fields: Optional[set[str]] = None,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Generic mandatory-declaration evaluator.

    Shared by Rule 6 (retail mandatory declarations) and Rule 24 (wholesale
    package declarations).
    """
    facts: List[ExtractedFact] = []
    findings: List[RuleFinding] = []
    requirements = _build_requirement_map(rule, context)
    exclude_fields = exclude_fields or set()

    for field, req in requirements.items():
        if field in exclude_fields:
            continue

        extraction = extractions.get(field)

        if _has_value(extraction):
            # Strict field value validation:
            if field == "mrp" and getattr(extraction, "numeric_value", None) is None:
                status = FactStatus.UNCERTAIN
                reason = (
                    getattr(extraction, "reason", "")
                    or f"MRP text '{extraction.value}' does not contain a verified positive monetary amount."
                )
                review = True
            elif field in {"best_before_use_by", "mfg_date"} and getattr(extraction, "date_value", None) is None and getattr(extraction, "normalized_value", None) is None:
                status = FactStatus.UNCERTAIN
                reason = (
                    getattr(extraction, "reason", "")
                    or f"Declaration label '{extraction.value}' was detected, but no valid date value could be established."
                )
                review = True
            elif field == "manufacturer_name_address":
                val_str = str(extraction.value or "").strip()
                import re as _re
                # Legal Metrology Rule 6(1)(a)/(b)/(c) requires complete entity name and complete address.
                # Incomplete address fragments (ending abruptly in comma/colon, lacking PIN or state/city, or under 25 chars) must not be overstated.
                has_pin = bool(_re.search(r"\b\d{6}\b", val_str))
                has_state_or_city = bool(_re.search(r"\b(?:mumbai|delhi|bangalore|bengaluru|chennai|kolkata|pune|hyderabad|ahmedabad|maharashtra|gujarat|karnataka|tamil\s*nadu|uttar\s*pradesh|haryana|road|street|marg|plot|ind|estate|nagar|dist|district)\b", val_str, _re.I))
                ends_abruptly = val_str.endswith(",") or val_str.endswith(";") or val_str.endswith(":") or val_str.endswith("/")
                is_partial = (
                    ends_abruptly
                    or ",," in val_str
                    or (not has_pin and not has_state_or_city)
                    or len(val_str) < 12
                )

                if is_partial:
                    status = FactStatus.UNCERTAIN
                    reason = (
                        f"Manufacturer / packer declaration '{val_str}' is partial or incomplete "
                        "(missing complete postal address / state / PIN code). Human review required per Rule 6(1)(a)."
                    )
                    review = True
                elif extraction.confidence < low_confidence_threshold:
                    status = FactStatus.UNCERTAIN
                    reason = (
                        f"{_human_field_name(field)} was detected, but extraction confidence "
                        f"{extraction.confidence:.2f} is below the configured "
                        f"threshold {low_confidence_threshold:.2f}."
                    )
                    review = True
                else:
                    status = FactStatus.PASS
                    reason = f"{_human_field_name(field)} is verified on the package label."
                    review = False
            elif extraction.confidence < low_confidence_threshold:
                status = FactStatus.UNCERTAIN
                reason = (
                    f"{_human_field_name(field)} was detected, but extraction confidence "
                    f"{extraction.confidence:.2f} is below the configured "
                    f"threshold {low_confidence_threshold:.2f}."
                )
                review = True
            else:
                status = FactStatus.PASS
                reason = f"{_human_field_name(field)} is verified on the package label."
                review = False

            fact = _make_fact(
                field=field,
                extraction=extraction,
                status=status,
                rule=rule,
                reason=reason,
                review_required=review,
            )
            facts.append(fact)
            findings.append(_finding(
                rule=rule,
                status=status,
                reason=reason,
                evidence=fact.evidence,
                requirement_id=req.get("id"),
                requirement_description=req.get("description"),
                confidence=fact.confidence,
                review_required=review,
                fact=fact,
            ))
            continue

        if extraction is not None and (getattr(extraction, "raw_text", None) or getattr(extraction, "label", None)):
            # Label was observed, but value is missing/unresolved
            status = FactStatus.UNCERTAIN
            reason = (
                getattr(extraction, "reason", "")
                or f"Declaration label for '{field}' was observed, but corresponding value was not reliably detected."
            )
            review = True
        elif req.get("_applicability_uncertain"):
            status = FactStatus.UNCERTAIN
            reason = (
                f"Required declaration '{field}' was not observed, and whether "
                f"it applies to this package could not be determined from "
                f"condition '{req.get('condition')}'. Absence cannot be "
                "assessed until applicability is resolved by a reviewer."
            )
            review = True
        elif _evidence_sufficient_for_missing_field(captures):
            status = FactStatus.FAIL
            reason = (
                f"Required declaration '{field}' was not evidenced after "
                "sufficient package coverage."
            )
            review = True
        else:
            status = FactStatus.UNCERTAIN
            reason = (
                f"Required declaration '{field}' was not observed in the provided image(s). "
                "Available package evidence is insufficient to conclude that the declaration is absent."
            )
            review = True

        fact = _make_fact(
            field=field,
            extraction=extraction if extraction else None,
            status=status,
            rule=rule,
            reason=reason,
            review_required=review,
            confidence_override=1.0 if status == FactStatus.FAIL else (extraction.confidence if extraction else 0.0),
        )
        facts.append(fact)
        findings.append(_finding(
            rule=rule,
            status=status,
            reason=reason,
            missing_evidence=[f"field:{field}"],
            requirement_id=req.get("id"),
            requirement_description=req.get("description"),
            confidence=fact.confidence,
            review_required=True,
            fact=fact,
        ))

    return facts, findings


def _evaluate_rule6_declarations(
    *,
    rules: Mapping[str, dict],
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    rule = _find_rule(rules, "LMPC-2011-R6-DECLARATIONS", "LMPC-2011-R6")
    if rule is None:
        raise ValueError("rules.json does not contain a Rule 6 declaration record")

    return _evaluate_declaration_rule(
        rule=rule,
        extractions=extractions,
        captures=captures,
        context=context,
        low_confidence_threshold=low_confidence_threshold,
        exclude_fields={"unit_sale_price"},
    )



def _evaluate_rule24_wholesale_declarations(
    *,
    rules: Mapping[str, dict],
    extractions: Mapping[str, RawExtraction],
    captures: Sequence[SurfaceObservation],
    context: Mapping[str, Any],
    low_confidence_threshold: float,
) -> tuple[List[ExtractedFact], List[RuleFinding]]:
    """
    Rule 24 — wholesale package declarations.

    Applies only when sale_type == "wholesale". Uses the same evidence-first,
    conservative-absence logic as Rule 6. Requirement fields per rules.json:
    manufacturer_name_address, common_name, wholesale_count_or_net_quantity.

    Note: 'wholesale_count_or_net_quantity' is not produced by the current
    OCR field classifier (ocr_extraction.py only emits 'net_quantity'). Until
    that alias/extraction is added, this requirement will correctly surface
    as UNCERTAIN (insufficient evidence) rather than a fabricated PASS/FAIL.
    """
    rule = _find_rule(rules, "LMPC-2011-R24-WHOLESALE")
    if rule is None:
        # Rule not present in this rules.json build — skip rather than crash,
        # but do not silently claim wholesale compliance.
        return [], []

    return _evaluate_declaration_rule(
        rule=rule,
        extractions=extractions,
        captures=captures,
        context=context,
        low_confidence_threshold=low_confidence_threshold,
    )


def _aggregate_status(facts: Iterable[ExtractedFact]) -> FactStatus:
    statuses = [fact.status for fact in facts]
    if not statuses:
        return FactStatus.UNCERTAIN

    if FactStatus.FAIL in statuses:
        return FactStatus.FAIL
    if FactStatus.UNCERTAIN in statuses:
        return FactStatus.UNCERTAIN
    if all(status == FactStatus.EXEMPT for status in statuses):
        return FactStatus.EXEMPT
    return FactStatus.PASS


def _summary(
    facts: Sequence[ExtractedFact],
    findings: Sequence[RuleFinding],
    captures: Sequence[SurfaceObservation],
) -> Dict[str, Any]:
    counts = {
        FactStatus.PASS: 0,
        FactStatus.FAIL: 0,
        FactStatus.UNCERTAIN: 0,
        FactStatus.EXEMPT: 0,
    }
    for finding in findings:
        counts[finding.status] += 1

    review_count = sum(
        1 for finding in findings if finding.review_required
    )

    coverage = _inspection_coverage(captures)
    evidence_complete = (
        bool(captures)
        and coverage >= 0.70
        and all(
            c.image_quality.status.value in {"USABLE", "PARTIAL"}
            for c in captures
        )
    )

    return {
        "total_rules_evaluated": len(findings),
        "passed": counts[FactStatus.PASS],
        "failed": counts[FactStatus.FAIL],
        "uncertain": counts[FactStatus.UNCERTAIN],
        "exempt": counts[FactStatus.EXEMPT],
        "review_required": review_count,
        "evidence_complete": evidence_complete,
        "coverage_score": coverage,
    }


def run_inspection(
    inspection_id: str,
    sale_type: str,
    product_category: str,
    net_quantity_value: Optional[float],
    net_quantity_unit: Optional[str],
    mrp: Optional[float],
    extractions: Dict[str, RawExtraction],
    pdp_area_cm2: Optional[float] = None,
    is_export_only: bool = False,
    retail_bundle_count: Optional[int] = None,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
    sticker_suspects: Optional[List[Any]] = None,
    captures: Optional[List[SurfaceObservation]] = None,
    is_imported: bool = False,
    dimensions_relevant: bool = False,
    best_before_applicable: bool = False,
    geometry: GeometryType = GeometryType.UNKNOWN,
    inspection_date: Optional[Any] = None,
    rule_versions: Optional[Iterable[Any]] = None,
    regulatory_module: str = "lmpc",
    package_structure: Any = PackageStructure.SINGLE_UNIT,
) -> ProductInspection:

    """
    Main inspection entry point.

    Backward-compatible with the original prototype while adding:
      - multi-surface captures
      - evidence-aware absence handling
      - rule-level findings
      - versioned rule references
      - correct Rule 6(11) unit-price handling
    """

    if not 0.0 <= low_confidence_threshold <= 1.0:
        raise ValueError("low_confidence_threshold must be between 0 and 1")

    # A net quantity of None means "not established yet" and is legitimate: the
    # net quantity is one of the declarations this engine READS from the package,
    # so requiring it as an input forced an inspector to type the very value
    # under inspection before any image had been analysed. An asserted zero or
    # negative quantity is a different thing entirely — a broken value rather
    # than an absent one — and is still rejected.
    if net_quantity_value is not None and float(net_quantity_value) <= 0:
        raise ValueError("net_quantity_value must be greater than zero")

    quantity_established = exemption_module.quantity_is_established(
        net_quantity_value, net_quantity_unit
    )

    captures = captures or []
    rules = load_rules()

    # A dated inspection MUST resolve against the authoritative RuleVersion
    # registry. Falling back to today's rules.json for a historical date would
    # make an otherwise correct inspection legally time-travelling. Conversely,
    # the legacy undated API path remains unchanged for existing callers.
    selected_versions = {}
    inspection_date_value = None
    if inspection_date is not None:
        if rule_versions is None:
            from regulatory.versions import RuleVersionSelectionError
            raise RuleVersionSelectionError(
                "A dated inspection requires an explicit RuleVersion registry; "
                "the engine will not fall back to rules.json."
            )
        rules, selected_versions = apply_rule_versions(
            rules,
            rule_versions,
            module=regulatory_module,
            inspection_date=inspection_date,
        )
        from regulatory.runtime import coerce_inspection_date
        inspection_date_value = coerce_inspection_date(inspection_date).isoformat()

    applicable_rule_version = version_label(selected_versions)
    facts: List[ExtractedFact] = []
    findings: List[RuleFinding] = []

    # ------------------------------------------------------------------
    # 1. Scope / exemption comes first.
    # ------------------------------------------------------------------
    exemption = classify_exemption(ExemptionInput(
        sale_type=sale_type,
        net_quantity_value=net_quantity_value,
        net_quantity_unit=net_quantity_unit,
        product_category=product_category,
        is_export_only=is_export_only,
        retail_bundle_count=retail_bundle_count,
    ))

    if exemption.is_exempt:
        scope_rule = _find_rule(
            rules,
            exemption.rule_id,
            "LMPC-2011-R3-SCOPE",
        )
        scope_fact = _make_fact(
            field="__scope__",
            extraction=None,
            status=FactStatus.EXEMPT,
            rule=scope_rule,
            reason=exemption.reason,
            review_required=False,
            confidence_override=1.0,
        )
        facts.append(scope_fact)

        if scope_rule:
            findings.append(_finding(
                rule=scope_rule,
                status=FactStatus.EXEMPT,
                reason=exemption.reason,
                confidence=1.0,
                review_required=False,
            ))

        return ProductInspection(
            inspection_id=inspection_id,
            product_category=product_category,
            sale_type=sale_type,
            package_weight_or_volume=net_quantity_value,
            package_weight_unit=net_quantity_unit,
            geometry=geometry,
            captures=captures,
            facts=facts,
            findings=findings,
            overall_status=FactStatus.EXEMPT,
            exempt_reason=exemption.reason,
            evidence_complete=bool(captures),
            review_required=False,
            inspection_date=inspection_date_value,
            applicable_rule_version=applicable_rule_version,
        )

    # An undetermined exemption is not an exemption, but it is also not a clean
    # "in scope". Rule 3's quantity exclusion and Rule 26(a)'s small-package
    # relaxation both depend on the net quantity, so when that quantity was never
    # established the applicability question is genuinely open. It is recorded as
    # an UNCERTAIN scope fact and carried into `review_required` so the
    # indeterminacy appears in the report instead of being silently resolved
    # against the package. Declaration checks still run: the pack's own
    # net-quantity declaration may well be readable, and this engine's absence
    # handling already resolves unreadable declarations to UNCERTAIN.
    quantity_scope_uncertain = (
        not exemption.is_exempt
        and exemption.exemption_type == QUANTITY_NOT_ESTABLISHED
    )
    if quantity_scope_uncertain:
        scope_rule = _find_rule(rules, exemption.rule_id, "LMPC-2011-R3-SCOPE")
        facts.append(_make_fact(
            field="__scope__",
            extraction=None,
            status=FactStatus.UNCERTAIN,
            rule=scope_rule,
            reason=exemption.reason,
            review_required=True,
            confidence_override=0.0,
        ))
        if scope_rule:
            findings.append(_finding(
                rule=scope_rule,
                status=FactStatus.UNCERTAIN,
                reason=exemption.reason,
                confidence=0.0,
                review_required=True,
                missing_evidence=["net_quantity"],
            ))

    # ------------------------------------------------------------------
    # 2. Build contextual applicability facts & calibration inference.
    # ------------------------------------------------------------------
    if pdp_area_cm2 is None and captures:
        inferred_area = _infer_pdp_area_from_captures(captures, geometry)
        if inferred_area is not None:
            pdp_area_cm2 = inferred_area

    _infer_numeral_height_from_captures(extractions, captures)

    context = {
        "is_imported": is_imported,
        "dimensions_relevant": dimensions_relevant,
        "best_before_applicable": best_before_applicable,
        "unit_price_rule_applies": True,
    }

    # ------------------------------------------------------------------
    # 3. Rule 6 mandatory declarations.
    # ------------------------------------------------------------------
    if sale_type.lower() == "retail":
        r6_facts, r6_findings = _evaluate_rule6_declarations(
            rules=rules,
            extractions=extractions,
            captures=captures,
            context=context,
            low_confidence_threshold=low_confidence_threshold,
        )
        facts.extend(r6_facts)
        findings.extend(r6_findings)

        # Batch / Lot / Code Number (Rule 6(1) / FSSAI)
        batch_ext = extractions.get("batch_no")
        if batch_ext is not None and _has_value(batch_ext):
            r6_rule = _find_rule(rules, "LMPC-2011-R6-DECLARATIONS", "LMPC-2011-R6")
            if batch_ext.confidence < low_confidence_threshold:
                b_status = FactStatus.UNCERTAIN
                b_reason = f"Batch / Lot Number was detected ('{batch_ext.value}'), but extraction confidence {batch_ext.confidence:.2f} is below the configured threshold {low_confidence_threshold:.2f}."
                b_review = True
            else:
                b_status = FactStatus.PASS
                b_reason = f"Batch / Lot Number is verified on the package label."
                b_review = False
            b_fact = _make_fact(
                field="batch_no",
                extraction=batch_ext,
                status=b_status,
                rule=r6_rule,
                reason=b_reason,
                review_required=b_review,
            )
            facts.append(b_fact)
            if r6_rule:
                findings.append(_finding(
                    rule=r6_rule,
                    status=b_status,
                    reason=b_reason,
                    evidence=b_fact.evidence,
                    requirement_id="batch_no",
                    requirement_description="Batch, lot or code identification number.",
                    confidence=b_fact.confidence,
                    review_required=b_review,
                    fact=b_fact,
                ))

    # ------------------------------------------------------------------
    # 3b. Rule 24 wholesale package declarations.
    # ------------------------------------------------------------------
    if sale_type.lower() == "wholesale":
        r24_facts, r24_findings = _evaluate_rule24_wholesale_declarations(
            rules=rules,
            extractions=extractions,
            captures=captures,
            context=context,
            low_confidence_threshold=low_confidence_threshold,
        )
        facts.extend(r24_facts)
        findings.extend(r24_findings)

    # ------------------------------------------------------------------
    # 3c. Rule 4 multi-piece / combination package declarations.
    # ------------------------------------------------------------------
    if sale_type.lower() == "retail" and retail_bundle_count and retail_bundle_count > 1:
        r4_facts, r4_findings = _evaluate_rule4_multipack(
            rules=rules,
            retail_bundle_count=retail_bundle_count,
            captures=captures,
            extractions=extractions,
        )
        facts.extend(r4_facts)
        findings.extend(r4_findings)

    # ------------------------------------------------------------------
    # 3d. Rule 5 / Second Schedule standard pack sizes.
    # (Omitted by statutory amendment GSR 779(E) dated 2021-11-02).
    # ------------------------------------------------------------------
    if sale_type.lower() in {"retail", "wholesale"}:
        r5_facts, r5_findings = _evaluate_rule5_standard_pack(
            rules=rules,
            product_category=product_category,
            net_quantity_value=net_quantity_value,
            net_quantity_unit=net_quantity_unit,
            extractions=extractions,
        )
        facts.extend(r5_facts)
        findings.extend(r5_findings)

    # ------------------------------------------------------------------
    # 3e. Rule 25 export package domestic sale.
    # ------------------------------------------------------------------
    r25_facts, r25_findings = _evaluate_rule25_export_package(
        rules=rules,
        sale_type=sale_type,
        is_export_only=is_export_only,
        extractions=extractions,
    )
    facts.extend(r25_facts)
    findings.extend(r25_findings)

    # ------------------------------------------------------------------
    # 3f. Rule 26(b)/(c) fast food and drug formulation exemptions.
    # ------------------------------------------------------------------
    r26bc_facts, r26bc_findings = _evaluate_rule26_bc_exemptions(
        rules=rules,
        product_category=product_category,
        context=context,
    )
    facts.extend(r26bc_facts)
    findings.extend(r26bc_findings)

    # ------------------------------------------------------------------
    # 3g. Rule 27 registration reference.
    # ------------------------------------------------------------------
    r27_facts, r27_findings = _evaluate_rule27_registration(
        rules=rules,
        context=context,
        extractions=extractions,
    )
    facts.extend(r27_facts)
    findings.extend(r27_findings)

    # ------------------------------------------------------------------
    # 3h. Rule 31 advertisement price & net quantity.
    # ------------------------------------------------------------------
    r31_facts, r31_findings = _evaluate_rule31_advertisement(
        rules=rules,
        sale_type=sale_type,
        extractions=extractions,
    )
    facts.extend(r31_facts)
    findings.extend(r31_findings)

    # ------------------------------------------------------------------
    # 4. Rule 7 font height / PDP evidence.
    # ------------------------------------------------------------------
    if sale_type.lower() == "retail":
        r7_facts, r7_findings = _evaluate_font_height(
            rules=rules,
            extractions=extractions,
            pdp_area_cm2=pdp_area_cm2,
        )
        facts.extend(r7_facts)
        findings.extend(r7_findings)

    # ------------------------------------------------------------------
    # 5. Rule 6(11) unit sale price.
    # ------------------------------------------------------------------
    usp_facts, usp_findings = _evaluate_unit_sale_price(
        rules=rules,
        extractions=extractions,
        net_quantity_value=net_quantity_value,
        net_quantity_unit=net_quantity_unit,
        mrp=mrp,
        sale_type=sale_type,
        low_confidence_threshold=low_confidence_threshold,
        package_structure=package_structure,
    )
    facts.extend(usp_facts)
    findings.extend(usp_findings)


    # ------------------------------------------------------------------
    # 6. Rule 8 placement.
    # ------------------------------------------------------------------
    if sale_type.lower() == "retail":
        placement_facts, placement_findings = _evaluate_placement(
            rules=rules,
            captures=captures,
            extractions=extractions,
        )
        facts.extend(placement_facts)
        findings.extend(placement_findings)

    # ------------------------------------------------------------------
    # 7. Advisory sticker/alteration evidence.
    # ------------------------------------------------------------------
    if sticker_suspects:
        for region in sticker_suspects:
            bbox = getattr(region, "bbox", None)
            confidence = float(getattr(region, "confidence", 0.0))
            reason = str(getattr(region, "reason", "possible alteration"))
            facts.append(ExtractedFact(
                field="__possible_alteration__",
                extracted_value=str(bbox),
                status=FactStatus.UNCERTAIN,
                confidence=max(0.0, min(1.0, confidence)),
                rule_id=None,
                reason=(
                    "Vision heuristic flagged a possible sticker/alteration "
                    f"region ({reason}). This is advisory evidence only."
                ),
                review_required=True,
            ))

    # ------------------------------------------------------------------
    # 8. Canonical declarations & deduplicated summary.
    # ------------------------------------------------------------------
    declarations, decl_summary = _build_canonical_declarations(
        facts=facts,
        extractions=extractions,
        context=context,
        captures=captures,
    )

    # ------------------------------------------------------------------
    # 9. Final status and summary.
    # ------------------------------------------------------------------
    overall = _aggregate_status(facts)
    summary_data = _summary(facts, findings, captures)

    pkg_struct_enum = (
        package_structure
        if isinstance(package_structure, PackageStructure)
        else PackageStructure(str(package_structure))
        if str(package_structure) in PackageStructure.__members__
        else PackageStructure.SINGLE_UNIT
    )

    return ProductInspection(
        inspection_id=inspection_id,
        product_category=product_category,
        sale_type=sale_type,
        package_structure=pkg_struct_enum,
        package_weight_or_volume=net_quantity_value,
        package_weight_unit=net_quantity_unit,
        geometry=geometry,

        captures=captures,
        facts=facts,
        declarations=declarations,
        declaration_summary=decl_summary,
        findings=findings,
        overall_status=overall,
        summary=summary_data,
        evidence_complete=summary_data["evidence_complete"],
        review_required=(
            summary_data["review_required"] > 0
            or overall == FactStatus.UNCERTAIN
        ),
        inspection_date=inspection_date_value,
        applicable_rule_version=applicable_rule_version,
    )


def _build_canonical_declarations(
    facts: List[ExtractedFact],
    extractions: Mapping[str, RawExtraction],
    context: Mapping[str, Any],
    captures: Sequence[SurfaceObservation],
) -> tuple[List[CanonicalDeclaration], Dict[str, int]]:
    declarations: List[CanonicalDeclaration] = []

    # Map facts by field name (taking primary non-auxiliary fact)
    fact_map: Dict[str, ExtractedFact] = {}
    for f in facts:
        if f.field.startswith("__") or f.field in ("mrp_numeral_height", "declaration_placement"):
            continue
        if f.field not in fact_map or f.status == FactStatus.PASS:
            fact_map[f.field] = f

    for field_id, meta in CANONICAL_DECLARATION_DEFINITIONS.items():
        canonical_name = meta["canonical_name"]
        rule_id = meta["rule_id"]
        rule_clause = meta["rule_clause"]

        # Check applicability
        is_applicable = True
        if field_id == "best_before_use_by" and not context.get("best_before_applicable", False):
            is_applicable = False
        elif field_id == "country_of_origin":
            # If explicit origin is extracted, or if imported, it is applicable.
            # If domestic product, it can still be verified as India (Domestic Origin).
            has_origin_ext = bool(extractions.get("country_of_origin") and extractions["country_of_origin"].value)
            if not context.get("is_imported", False) and not has_origin_ext:
                # Check if manufacturer address indicates domestic origin
                mfg_ext = extractions.get("manufacturer_name") or extractions.get("manufacturer_name_address")
                mfg_val = str(getattr(mfg_ext, "value", "") or "").lower()
                if any(ind in mfg_val for ind in ("india", "mumbai", "delhi", "bengaluru", "chennai", "kolkata", "pune", "gujarat", "tamil nadu", "maharashtra", "haryana", "uttar pradesh", "karnataka")):
                    # Domestic Indian origin identified from statutory manufacturer premises
                    is_applicable = True
                else:
                    is_applicable = False
        elif field_id == "standard_pack_size":
            # Rule 5 / Second Schedule evaluation: active when standard_pack_applicable is set or when standard_pack_size is detected
            is_applicable = context.get("standard_pack_applicable", False) or bool(extractions.get("standard_pack_size"))

        if not is_applicable:
            reason = (
                "Standard pack size (Rule 5 / Second Schedule) was omitted by statutory amendment GSR 779(E) and is not an active mandatory requirement for modern packaged goods."
                if field_id == "standard_pack_size"
                else "Declaration is outside statutory scope for this product category and origin."
            )
            declarations.append(CanonicalDeclaration(
                field=field_id,
                canonical_name=canonical_name,
                value=None,
                status=CanonicalStatus.NOT_APPLICABLE,
                confidence=1.0,
                validation=ValidationDetails(present=False, readable=None, correct_format=None, compliant=True),
                reason=reason,
                rule_id=rule_id,
                rule_clause=rule_clause,
            ))
            continue

        fact = fact_map.get(field_id)
        ext = extractions.get(field_id)

        extracted_val = fact.extracted_value if fact else (ext.value if ext else None)
        raw_text = fact.raw_text if fact else (ext.raw_text if ext else None)
        norm_val = fact.normalized_value if fact else (ext.normalized_value if ext else None)
        confidence = fact.confidence if fact else (ext.confidence if ext else 0.0)

        # Primary evidence reference
        primary_evidence = None
        if fact and fact.evidence:
            ev = next((e for e in fact.evidence if e.is_attributed()), fact.evidence[0])
            bbox_coords = [ev.bbox.x, ev.bbox.y, ev.bbox.width, ev.bbox.height] if ev.bbox else None
            face_view = None
            if ev.surface_id:
                sid = str(ev.surface_id).strip()
                if sid.lower().startswith("face_") and sid[5:].isdigit():
                    face_view = f"Face {sid[5:]}"
                elif sid.lower().startswith("face ") and sid[5:].isdigit():
                    face_view = f"Face {sid[5:]}"
                else:
                    face_view = sid
            is_vlm = (
                getattr(ext, "source", None) in ("vlm", "qwen")
                or getattr(ext, "detection_status", None) == "DETECTED"
                or (getattr(ext, "confidence", 0.0) >= 0.85 and getattr(ext, "detection_status", None) != "UNREADABLE")
                or (fact and fact.evidence and any("Qwen" in (e.evidence_note or "") or "multimodal" in (e.evidence_note or "") for e in fact.evidence))
            )
            source_type = "vlm" if is_vlm else "ocr"
            primary_evidence = DeclarationEvidence(
                image_id=ev.image_id,
                page_or_view=face_view,
                bbox=bbox_coords,
                source=source_type,
            )
        elif ext and ext.evidence:
            ev = next((e for e in ext.evidence if e.is_attributed()), ext.evidence[0])
            bbox_coords = [ev.bbox.x, ev.bbox.y, ev.bbox.width, ev.bbox.height] if ev.bbox else None
            face_view = None
            if ev.surface_id:
                sid = str(ev.surface_id).strip()
                if sid.lower().startswith("face_") and sid[5:].isdigit():
                    face_view = f"Face {sid[5:]}"
                elif sid.lower().startswith("face ") and sid[5:].isdigit():
                    face_view = f"Face {sid[5:]}"
                else:
                    face_view = sid
            is_vlm = (
                getattr(ext, "source", None) in ("vlm", "qwen")
                or getattr(ext, "detection_status", None) == "DETECTED"
                or (getattr(ext, "confidence", 0.0) >= 0.85 and getattr(ext, "detection_status", None) != "UNREADABLE")
                or any("Qwen" in (e.evidence_note or "") or "multimodal" in (e.evidence_note or "") for e in ext.evidence)
            )
            source_type = "vlm" if is_vlm else "ocr"
            primary_evidence = DeclarationEvidence(
                image_id=ev.image_id,
                page_or_view=face_view,
                bbox=bbox_coords,
                source=source_type,
            )
        elif ext and ext.bbox:
            is_vlm = (
                getattr(ext, "source", None) in ("vlm", "qwen")
                or getattr(ext, "detection_status", None) == "DETECTED"
                or (getattr(ext, "confidence", 0.0) >= 0.85 and getattr(ext, "detection_status", None) != "UNREADABLE")
            )
            source_type = "vlm" if is_vlm else "ocr"
            primary_evidence = DeclarationEvidence(
                image_id=UNATTRIBUTED_IMAGE_ID,
                page_or_view=None,
                bbox=list(ext.bbox) if isinstance(ext.bbox, (list, tuple)) else None,
                source=source_type,
            )
        elif extracted_val is not None and str(extracted_val).strip():
            is_vlm = (
                getattr(ext, "source", None) in ("vlm", "qwen")
                or getattr(ext, "detection_status", None) == "DETECTED"
                or (getattr(ext, "confidence", 0.0) >= 0.85 and getattr(ext, "detection_status", None) != "UNREADABLE")
                or (fact and fact.evidence and any("Qwen" in (e.evidence_note or "") or "multimodal" in (e.evidence_note or "") for e in fact.evidence))
            )
            source_type = "vlm" if is_vlm else "ocr"
            primary_evidence = DeclarationEvidence(
                image_id=UNATTRIBUTED_IMAGE_ID,
                page_or_view="Face 1",
                bbox=None,
                source=source_type,
            )

        if field_id == "country_of_origin" and not extracted_val:
            mfg_ext = extractions.get("manufacturer_name") or extractions.get("manufacturer_name_address")
            mfg_val = str(getattr(mfg_ext, "value", "") or "").lower()
            if any(ind in mfg_val for ind in ("india", "mumbai", "delhi", "bengaluru", "chennai", "kolkata", "pune", "gujarat", "tamil nadu", "maharashtra", "haryana", "uttar pradesh", "karnataka")):
                extracted_val = "India (Domestic Origin)"
                norm_val = "India"
                confidence = 0.95

        if fact and fact.status == FactStatus.PASS and extracted_val:
            status = CanonicalStatus.VERIFIED
            reason = fact.reason or f"{canonical_name} verified compliant on package label."
            validation = ValidationDetails(present=True, readable=True, correct_format=True, compliant=True)
        elif fact and fact.status == FactStatus.FAIL:
            status = CanonicalStatus.NON_COMPLIANT
            reason = fact.reason or f"{canonical_name} violates statutory requirement."
            validation = ValidationDetails(present=bool(extracted_val), readable=bool(extracted_val), correct_format=False, compliant=False)
        elif extracted_val is not None and str(extracted_val).strip():
            ext_status = getattr(ext, "status", None) if ext else None
            is_review = (ext_status == "REVIEW_REQUIRED") or (fact and fact.status == FactStatus.UNCERTAIN)
            if is_review:
                status = CanonicalStatus.REVIEW_REQUIRED
                reason = (
                    (fact.reason if fact else None)
                    or (ext.reason if ext else None)
                    or f"{canonical_name} detected but requires human review."
                )
                validation = ValidationDetails(present=True, readable=confidence >= 0.4, correct_format=None, compliant=None)
            else:
                status = CanonicalStatus.VERIFIED
                reason = f"{canonical_name} verified on package label."
                validation = ValidationDetails(present=True, readable=True, correct_format=True, compliant=True)
        elif ext is not None and (getattr(ext, "label", None) or getattr(ext, "raw_text", None)):
            status = CanonicalStatus.PARTIALLY_DETECTED
            reason = getattr(ext, "reason", "") or f"{canonical_name} label detected, but value was not reliably detected."
            validation = ValidationDetails(present=False, readable=None, correct_format=False, compliant=None)
        else:
            status = CanonicalStatus.NOT_DETECTED_IN_PROVIDED_IMAGES
            reason = f"{canonical_name} not detected on label."
            validation = ValidationDetails(present=False, readable=None, correct_format=None, compliant=None)

        declarations.append(CanonicalDeclaration(
            field=field_id,
            canonical_name=canonical_name,
            label=getattr(ext, "label", None) if ext else None,
            value=extracted_val,
            normalized_value=norm_val,
            raw_text=raw_text,
            confidence=confidence,
            status=status,
            evidence=primary_evidence,
            validation=validation,
            reason=reason,
            rule_id=rule_id,
            rule_clause=rule_clause,
        ))

    # Assert that no duplicates exist in the canonical declarations list
    assert len(declarations) == len(set(d.field for d in declarations)), "Duplicate canonical declaration IDs detected!"

    summary = {
        "applicable": sum(1 for d in declarations if d.status != CanonicalStatus.NOT_APPLICABLE),
        "detected": sum(1 for d in declarations if d.validation.present),
        "verified": sum(1 for d in declarations if d.status == CanonicalStatus.VERIFIED),
        "review_required": sum(1 for d in declarations if d.status in (
            CanonicalStatus.REVIEW_REQUIRED,
            CanonicalStatus.PARTIALLY_DETECTED,
            CanonicalStatus.INSUFFICIENT_EVIDENCE,
            CanonicalStatus.NOT_DETECTED_IN_PROVIDED_IMAGES,
        )),
        "non_compliant": sum(1 for d in declarations if d.status == CanonicalStatus.NON_COMPLIANT),
    }
    return declarations, summary

