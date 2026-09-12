"""
Regulatory Scope & Grounded RAG Knowledge Integration Layer.

Connects the existing RAG subsystem (backend/rag/) into the canonical production pipeline.

Decision Boundaries:
- RegulatoryScopeEngine determines which modules (LMPC, FSSAI, CDSCO, etc.) apply.
- RAG retrieves grounded statutory provisions, clauses, versions, and evidence requirements.
- The deterministic Rule Engine remains the sole authority for PASS/FAIL decisions.
- RAG NEVER directly decides compliance verdicts.
- Fails safely: if RAG is unavailable, deterministic rule engine continues.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from models import (
    ApprovalState,
    KnowledgeChunk,
    RAGGroundingStatus,
    RAGResponse,
    RegulatoryContext,
    RuleVersion,
)
from rag.default_corpus import build_default_chunks
from rag.query import GroundedRAGService
from rag.retriever import HybridRetriever
from rag.store import InMemoryKnowledgeStore
from registry import RegulatoryModuleRegistry
from lmpc import LMPCModule
from placeholders import default_future_modules

logger = logging.getLogger("rag_grounding")


class LegalKnowledgeResult(BaseModel):
    """
    Structured legal knowledge grounded by RAG.
    Supplies the deterministic rule engine with applicable provisions, versions, and citations.
    """
    model_config = ConfigDict(extra="allow")

    module: str
    regulation: str
    rule_id: str
    rule_version: str
    effective_date: str
    applicability: str  # "APPLICABLE", "CONDITIONAL", "EXEMPT", "NOT_APPLICABLE"
    applicability_reason: str
    evidence_requirements: List[str] = Field(default_factory=list)
    exemptions: List[str] = Field(default_factory=list)
    source_reference: str
    retrieval_confidence: float = 1.0
    grounding_status: str = "GROUNDED"
    citations: List[str] = Field(default_factory=list)
    warning: Optional[str] = None


# Singleton knowledge store and service initialized from default corpus
_knowledge_store = InMemoryKnowledgeStore()
_default_chunks = build_default_chunks()
_knowledge_store.upsert_chunks(_default_chunks)
_rag_service = GroundedRAGService(HybridRetriever(_knowledge_store.list_chunks()))


class RegulatoryScopeEngine:
    """
    Resolves applicable regulatory framework modules (LMPC, FSSAI, CDSCO, etc.)
    based on product context, keeping framework boundaries clean.
    """
    def __init__(self) -> None:
        self.registry = RegulatoryModuleRegistry([LMPCModule(), *default_future_modules()])

    def resolve_scope(self, context: RegulatoryContext) -> Dict[str, Any]:
        p_cat = (context.product_category or "").lower()
        c_type = (context.commodity_type or "").lower()

        active_modules = ["lmpc"]
        boundary_notes = [
            "LMPC (Legal Metrology Packaged Commodities Rules, 2011) is the primary framework for packaging declarations, net quantities, MRP, and unit sale prices."
        ]

        is_food = (
            p_cat in ("food", "edible", "beverage", "grocery")
            or any(w in c_type for w in ("coffee", "chicory", "tea", "mix", "oil", "food", "juice", "biscuit"))
        )
        if is_food:
            active_modules.append("fssai")
            boundary_notes.append(
                "FSSAI (Food Safety and Standards Act) governs food identity, proprietary food licenses, and ingredient lists. Food declarations route through FSSAI boundary requirements."
            )

        if p_cat in ("drug", "medicine", "medical", "pharma"):
            active_modules.append("cdsco")
            boundary_notes.append("CDSCO governs drugs and cosmetics under the Drugs and Cosmetics Act.")
        elif p_cat in ("cosmetic", "beauty"):
            active_modules.append("cosmetics")
            boundary_notes.append("Cosmetics regulatory framework applies.")

        return {
            "primary_module": "lmpc",
            "active_modules": active_modules,
            "boundary_notes": boundary_notes,
            "is_food": is_food,
            "inspection_date": context.inspection_date.isoformat() if hasattr(context.inspection_date, "isoformat") else str(context.inspection_date),
        }


_scope_engine = RegulatoryScopeEngine()


def resolve_regulatory_scope(context: RegulatoryContext) -> Dict[str, Any]:
    """Public helper to resolve regulatory scope."""
    return _scope_engine.resolve_scope(context)


def ground_inspection_context(
    context: RegulatoryContext,
    *,
    service: Optional[GroundedRAGService] = None,
) -> List[LegalKnowledgeResult]:
    """
    Query RAG to retrieve and ground applicable statutory provisions for this inspection context.

    Preserves:
    - rule_id, rule_version, effective_date
    - applicability rationale
    - evidence requirements
    - source citations and grounding status

    Fails safely: returns empty or fallback review states if RAG retrieval fails.
    """
    rag = service or _rag_service
    results: List[LegalKnowledgeResult] = []

    try:
        scope = resolve_regulatory_scope(context)
        insp_date = context.inspection_date if isinstance(context.inspection_date, date) else date.fromisoformat(str(context.inspection_date)[:10])

        # Core queries matching applicable declaration topics
        queries = [
            ("LMPC-2011-R6", "mandatory declarations on pre-packaged commodity name address net quantity month year mfg price consumer care"),
            ("LMPC-2011-R6-11", "unit sale price retail sale price calculation per gram per kilogram per milliliter"),
            ("LMPC-2011-R3-SCOPE", "scope and exemption applicability retail package institutional consumer industrial consumer"),
            ("LMPC-2011-R26-EXEMPTION", "exemption from declarations package less than ten grams or ten milliliters"),
        ]

        if scope.get("is_food"):
            queries.append(("FSSAI-FOOD-SCOPE", "food safety proprietary food instant coffee chicory mixture ingredients"))

        for rule_prefix, q in queries:
            try:
                ans: RAGResponse = rag.answer(q, context, top_k=4)
                if ans.grounding_status == RAGGroundingStatus.GROUNDED and ans.sources:
                    for src in ans.sources:
                        # Check effective date bounds
                        if src.effective_from and src.effective_from > insp_date:
                            continue
                        if src.effective_to and src.effective_to < insp_date:
                            continue

                        rule_id = src.rule_id or rule_prefix
                        # Avoid duplicates
                        if any(r.rule_id == rule_id for r in results):
                            continue

                        results.append(
                            LegalKnowledgeResult(
                                module="lmpc" if not rule_prefix.startswith("FSSAI") else "fssai",
                                regulation=(
                                    "Legal Metrology (Packaged Commodities) Rules, 2011"
                                    if not rule_prefix.startswith("FSSAI")
                                    else "Food Safety and Standards Act / Regulations"
                                ),
                                rule_id=rule_id,
                                rule_version="2011 (amended)",
                                effective_date=src.effective_from.isoformat() if src.effective_from else "2011-04-01",
                                applicability="APPLICABLE" if not rule_prefix.endswith("EXEMPTION") else "CONDITIONAL",
                                applicability_reason=f"Grounded from statutory knowledge base ({src.source_reference or src.document_id}).",
                                evidence_requirements=[
                                    "manufacturer_name_address", "common_name", "net_quantity",
                                    "mrp", "mfg_date", "best_before_use_by", "consumer_care", "unit_sale_price"
                                ],
                                source_reference=src.source_reference or src.document_id,
                                retrieval_confidence=round(float(src.score), 3),
                                grounding_status=ans.grounding_status.value,
                                citations=ans.citation or [src.source_reference or src.document_id],
                                warning=ans.warning,
                            )
                        )
            except Exception as e:
                logger.warning(f"RAG query failed for {rule_prefix}: {e}")

    except Exception as exc:
        logger.error(f"Failed to ground inspection context: {exc}")
        # Failure-safe fallback: deterministic rule engine remains functional
        results.append(
            LegalKnowledgeResult(
                module="lmpc",
                regulation="Legal Metrology (Packaged Commodities) Rules, 2011",
                rule_id="LMPC-2011-R6-FALLBACK",
                rule_version="2011 (amended)",
                effective_date="2011-04-01",
                applicability="APPLICABLE",
                applicability_reason="Fallback grounding: RAG service was unavailable; standard statutory rules apply.",
                source_reference="Legal Metrology (Packaged Commodities) Rules, 2011",
                retrieval_confidence=0.5,
                grounding_status="REVIEW_REQUIRED",
                citations=["LMPC Rules, 2011"],
                warning="RAG retrieval unavailable; deterministic rule evaluation continues.",
            )
        )

    return results


def get_grounded_rule_versions(grounded: List[LegalKnowledgeResult]) -> List[RuleVersion]:
    """Convert LegalKnowledgeResults into RuleVersion models for rule engine consumption."""
    versions: List[RuleVersion] = []
    for g in grounded:
        try:
            eff_date = date.fromisoformat(g.effective_date)
        except Exception:
            eff_date = date(2011, 4, 1)

        versions.append(
            RuleVersion(
                id=f"{g.module}:{g.rule_id}:{g.rule_version}",
                module=g.module,
                regulation=g.regulation,
                rule_id=g.rule_id,
                version=g.rule_version,
                effective_from=eff_date,
                approval_state=ApprovalState.ACTIVE,
                source_document_id=g.source_reference,
            )
        )
    return versions


def get_canonical_rule_versions(
    grounded: Optional[List[LegalKnowledgeResult]] = None,
    rules_dict: Optional[Dict[str, dict]] = None,
) -> List[RuleVersion]:
    """
    Build a complete, authoritative RuleVersion list combining standard rules
    with RAG-grounded rule versions for dated inspections.
    """
    from rule_engine import load_rules
    if rules_dict is None:
        rules_dict = load_rules()

    grounded_by_id = {g.rule_id: g for g in (grounded or [])}
    versions: List[RuleVersion] = []

    for rule_id, rule in rules_dict.items():
        g = grounded_by_id.get(rule_id)
        version = g.rule_version if g else (rule.get("version") or "2011 as amended")
        eff_str = (g.effective_date if g else None) or rule.get("effective_from") or "2011-04-01"
        try:
            eff_date = date.fromisoformat(eff_str[:10])
        except Exception:
            eff_date = date(2011, 4, 1)

        eff_to_str = rule.get("effective_to")
        try:
            eff_to = date.fromisoformat(eff_to_str[:10]) if eff_to_str else None
        except Exception:
            eff_to = None

        versions.append(
            RuleVersion(
                id=f"lmpc:{rule_id}:{version}",
                module="lmpc",
                regulation=rule.get("source") or "Legal Metrology (Packaged Commodities) Rules, 2011",
                rule_id=rule_id,
                version=version,
                effective_from=eff_date,
                effective_to=eff_to,
                approval_state=ApprovalState.ACTIVE,
                source_document_id=g.source_reference if g else rule.get("source"),
            )
        )
    return versions

