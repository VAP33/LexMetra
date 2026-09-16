"""
backend/regulatory_service.py
Regulatory service coordinating legacy, shadow, and generic modes.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import config
from rule_engine import run_inspection as run_legacy_inspection
from schema import ProductInspection
from regulatory_adapter import evaluate_regulatory_compliance
from localization.models import LocalizedEvidence

logger = logging.getLogger(__name__)


class RegulatoryService:
    """
    Central service for evaluating regulatory compliance across execution modes:
    - 'legacy': Executes the existing deterministic rule engine only.
    - 'shadow': Executes legacy (authoritative) and generic in-memory; logs differences.
    - 'generic': Executes Arya's generic engine as the authority.
    """

    def __init__(self, mode: Optional[str] = None):
        self.mode = (mode or getattr(config, "REGULATORY_ENGINE_MODE", "legacy")).strip().lower()

    def evaluate(
        self,
        inspection_id: str,
        sale_type: str,
        product_category: str,
        net_quantity_value: Optional[float],
        net_quantity_unit: Optional[str],
        mrp: Optional[float],
        extractions: Dict[str, Any],
        captures: Optional[List[Any]] = None,
        pdp_area_cm2: Optional[float] = None,
        is_export_only: bool = False,
        is_imported: bool = False,
        retail_bundle_count: Optional[int] = None,
        best_before_applicable: bool = True,
        inspection_date: Optional[date] = None,
        grounded_rule_versions: Optional[Any] = None,
        regulatory_module: str = "lmpc",
        package_structure: Optional[Any] = None,
        localized_evidence: Optional[List[LocalizedEvidence]] = None,
    ) -> ProductInspection:
        """
        Evaluate compliance in accordance with configured REGULATORY_ENGINE_MODE.
        """
        inspection_date = inspection_date or date.today()

        if grounded_rule_versions is None and inspection_date is not None:
            try:
                from models import RegulatoryContext
                from rag_grounding import ground_inspection_context, get_canonical_rule_versions
                c_type = (extractions.get("common_name") and (extractions["common_name"].get("value") if isinstance(extractions["common_name"], dict) else getattr(extractions["common_name"], "value", None))) or product_category
                reg_context = RegulatoryContext(
                    product_category=product_category,
                    commodity_type=str(c_type),
                    sale_type=sale_type,
                    net_quantity=net_quantity_value,
                    quantity_unit=net_quantity_unit,
                    is_imported=is_imported,
                    inspection_date=inspection_date,
                )
                grounded_knowledge = ground_inspection_context(reg_context)
                grounded_rule_versions = get_canonical_rule_versions(grounded_knowledge)
            except Exception:
                pass

        if self.mode == "generic":

            # Arya generic engine is authoritative
            generic_result, _ = evaluate_regulatory_compliance(
                inspection_id=inspection_id,
                sale_type=sale_type,
                product_category=product_category,
                net_quantity_value=net_quantity_value,
                net_quantity_unit=net_quantity_unit,
                mrp=mrp,
                extractions=extractions,
                localized_evidence=localized_evidence,
                captures=captures,
                is_export_only=is_export_only,
                is_imported=is_imported,
                retail_bundle_count=retail_bundle_count,
                best_before_applicable=best_before_applicable,
                inspection_date=inspection_date,
            )
            return generic_result

        # Prepare extractions for legacy engine if dicts were supplied
        legacy_extractions = {}
        for fld, val in extractions.items():
            if isinstance(val, dict):
                from rule_engine import RawExtraction
                v_raw = val.get("value")
                legacy_extractions[fld] = RawExtraction(
                    field=fld,
                    raw_text=val.get("raw_text") or str(v_raw or ""),
                    value=str(v_raw) if v_raw is not None else None,
                    normalized_value=val.get("normalized_value"),
                    confidence=float(val.get("confidence", 0.0) or 0.0),
                )
            else:
                legacy_extractions[fld] = val


        # Legacy inspection execution (authoritative for legacy and shadow modes)
        legacy_result = run_legacy_inspection(
            inspection_id=inspection_id,
            sale_type=sale_type,
            product_category=product_category,
            net_quantity_value=net_quantity_value,
            net_quantity_unit=net_quantity_unit,
            mrp=mrp,
            extractions=legacy_extractions,

            pdp_area_cm2=pdp_area_cm2,
            is_export_only=is_export_only,
            retail_bundle_count=retail_bundle_count,
            captures=captures or [],
            best_before_applicable=best_before_applicable,
            is_imported=is_imported,
            inspection_date=inspection_date,
            rule_versions=grounded_rule_versions,
            regulatory_module=regulatory_module,
            package_structure=package_structure,
        )

        if self.mode == "shadow":
            # Run generic engine in memory and log comparisons
            try:
                shadow_result, shadow_report = evaluate_regulatory_compliance(
                    inspection_id=inspection_id,
                    sale_type=sale_type,
                    product_category=product_category,
                    net_quantity_value=net_quantity_value,
                    net_quantity_unit=net_quantity_unit,
                    mrp=mrp,
                    extractions=extractions,
                    localized_evidence=localized_evidence,
                    captures=captures,
                    is_export_only=is_export_only,
                    is_imported=is_imported,
                    retail_bundle_count=retail_bundle_count,
                    best_before_applicable=best_before_applicable,
                    inspection_date=inspection_date,
                )

                legacy_stat = getattr(legacy_result, "overall_status", None)
                generic_stat = getattr(shadow_result, "overall_status", None)

                diff = {
                    "inspection_id": inspection_id,
                    "legacy_status": legacy_stat.value if hasattr(legacy_stat, "value") else str(legacy_stat),
                    "generic_status": generic_stat.value if hasattr(generic_stat, "value") else str(generic_stat),
                    "legacy_findings_count": len(legacy_result.findings),
                    "generic_findings_count": len(shadow_result.findings),
                    "ruleset_id": shadow_report.ruleset_id,
                    "ruleset_version": shadow_report.ruleset_version,
                }
                logger.info("[SHADOW REGULATORY COMPARISON] %s", diff)
                print(f"[SHADOW REGULATORY COMPARISON] legacy={diff['legacy_status']} vs generic={diff['generic_status']}", flush=True)
            except Exception as ex:
                logger.warning("[SHADOW REGULATORY EVALUATION ERROR] %s", ex, exc_info=True)

        return legacy_result
