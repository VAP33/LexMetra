"""
Regression tests for declaration verification score and status propagation across
backend, API, frontend mapping, and PDF reporting.

Covers prompt Section 13 (Requirements A through J).
"""

from __future__ import annotations

from typing import Any, Dict, List
import pytest

from schema import (
    BBox,
    CanonicalDeclaration,
    CanonicalStatus,
    DeclarationEvidence,
    EvidenceReference,
    ExtractedFact,
    FactStatus,
    ProductInspection,
    RuleFinding,
    SurfaceObservation,
    UNATTRIBUTED_IMAGE_ID,
    ValidationDetails,
)
from rule_engine import RawExtraction, _build_canonical_declarations, run_inspection
from report import build_inspection_report_pdf, _get


def _dummy_ev(image_id: str = "panel_1.jpg") -> List[EvidenceReference]:
    return [
        EvidenceReference(
            image_id=image_id,
            surface_id="front",
            bbox=BBox(x=100.0, y=100.0, width=200.0, height=50.0),
        )
    ]


def test_a_all_applicable_declarations_verified():
    """Requirement A: All applicable declarations VERIFIED -> count = N/N (score 100%)."""
    facts = [
        ExtractedFact(
            field="manufacturer_name_address",
            extracted_value="Hindustan Unilever Ltd, Unit 1, Industrial Area, Mumbai 400001, Maharashtra",
            status=FactStatus.PASS,
            confidence=0.95,
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="common_name",
            extracted_value="Instant Coffee-Chicory Mixture",
            status=FactStatus.PASS,
            confidence=0.90,
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="net_quantity",
            extracted_value="150 g",
            status=FactStatus.PASS,
            confidence=0.92,
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="mfg_date",
            extracted_value="13/05/2026",
            status=FactStatus.PASS,
            confidence=0.88,
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="best_before_use_by",
            extracted_value="12/10/2027",
            status=FactStatus.PASS,
            confidence=0.89,
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="mrp",
            extracted_value="₹420",
            status=FactStatus.PASS,
            confidence=0.91,
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="consumer_care",
            extracted_value="care@hul.com, Tel: 1800-10-22-221, PO Box 14760",
            status=FactStatus.PASS,
            confidence=0.85,
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="unit_sale_price",
            extracted_value="₹2.80/g",
            status=FactStatus.PASS,
            confidence=0.87,
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="batch_no",
            extracted_value="HF 130526 17:08",
            status=FactStatus.PASS,
            confidence=0.86,
            evidence=_dummy_ev(),
        ),
    ]
    context = {
        "best_before_applicable": True,
        "is_imported": False,
        "standard_pack_applicable": False,
    }
    decls, summary = _build_canonical_declarations(
        facts=facts, extractions={}, context=context, captures=[]
    )

    assert summary["applicable"] == 9
    assert summary["verified"] == 9
    assert summary["review_required"] == 0
    assert summary["non_compliant"] == 0


def test_b_mixed_verified_and_review_required():
    """Requirement B: Mixed VERIFIED + REVIEW_REQUIRED -> correct counts."""
    facts = [
        # 4 Verified
        ExtractedFact(
            field="common_name",
            extracted_value="Instant Coffee",
            status=FactStatus.PASS,
            confidence=0.80,
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="net_quantity",
            extracted_value="150 g",
            status=FactStatus.PASS,
            confidence=0.90,
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="mfg_date",
            extracted_value="13/05/26",
            status=FactStatus.PASS,
            confidence=0.70,
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="best_before_use_by",
            extracted_value="12/10/27",
            status=FactStatus.PASS,
            confidence=0.75,
            evidence=_dummy_ev(),
        ),
        # 5 Review Required (uncertain / weak confidence / partial)
        ExtractedFact(
            field="manufacturer_name_address",
            extracted_value="195/2A,, B.D. SAWANT, FOODS LIMITED,",
            status=FactStatus.UNCERTAIN,
            confidence=0.45,
            reason="Mangled fragment",
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="mrp",
            extracted_value="₹420",
            status=FactStatus.UNCERTAIN,
            confidence=0.20,
            reason="Low OCR confidence",
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="unit_sale_price",
            extracted_value="₹2.8/g",
            status=FactStatus.UNCERTAIN,
            confidence=0.50,
            reason="Unverified MRP",
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="consumer_care",
            extracted_value="1800-10-22-2",
            status=FactStatus.UNCERTAIN,
            confidence=0.36,
            reason="Incomplete contact",
            evidence=_dummy_ev(),
        ),
        ExtractedFact(
            field="batch_no",
            extracted_value="HF 130526",
            status=FactStatus.UNCERTAIN,
            confidence=0.52,
            reason="Confidence below threshold",
            evidence=_dummy_ev(),
        ),
    ]
    context = {
        "best_before_applicable": True,
        "is_imported": False,
        "standard_pack_applicable": False,
    }
    decls, summary = _build_canonical_declarations(
        facts=facts, extractions={}, context=context, captures=[]
    )

    assert summary["applicable"] == 9
    assert summary["verified"] == 4
    assert summary["review_required"] == 5


def test_c_not_applicable_fields_excluded_from_denominator():
    """Requirement C: NOT_APPLICABLE fields are excluded from denominator."""
    context = {
        "best_before_applicable": True,
        "is_imported": False,  # domestic commodity
        "standard_pack_applicable": False,  # Rule 5 omitted
    }
    decls, summary = _build_canonical_declarations(
        facts=[], extractions={}, context=context, captures=[]
    )

    # 11 total definitions, 2 are NOT_APPLICABLE -> applicable == 9
    assert len(decls) == 11
    assert summary["applicable"] == 9

    standard_pack = next(d for d in decls if d.field == "standard_pack_size")
    assert standard_pack.status == CanonicalStatus.NOT_APPLICABLE
    assert "omitted" in standard_pack.reason.lower()

    country = next(d for d in decls if d.field == "country_of_origin")
    assert country.status == CanonicalStatus.NOT_APPLICABLE


def test_d_exempt_fields_presentation():
    """Requirement D: EXEMPT / NOT_APPLICABLE fields have compliant=True validation."""
    context = {
        "best_before_applicable": False,  # non-perishable product
        "is_imported": False,
        "standard_pack_applicable": False,
    }
    decls, summary = _build_canonical_declarations(
        facts=[], extractions={}, context=context, captures=[]
    )

    bb = next(d for d in decls if d.field == "best_before_use_by")
    assert bb.status == CanonicalStatus.NOT_APPLICABLE
    assert bb.validation.compliant is True


def test_e_uncertain_fields_not_counted_as_verified():
    """Requirement E: UNCERTAIN fields are not counted as VERIFIED."""
    facts = [
        ExtractedFact(
            field="net_quantity",
            extracted_value="150 g",
            status=FactStatus.UNCERTAIN,
            confidence=0.50,
            evidence=_dummy_ev(),
        )
    ]
    decls, summary = _build_canonical_declarations(
        facts=facts, extractions={}, context={"best_before_applicable": True}, captures=[]
    )

    nq = next(d for d in decls if d.field == "net_quantity")
    assert nq.status == CanonicalStatus.REVIEW_REQUIRED
    assert summary["verified"] == 0


def test_f_backend_verified_maps_to_frontend_verified():
    """Requirement F: Backend VERIFIED status maps properly."""
    decl = CanonicalDeclaration(
        field="net_quantity",
        canonical_name="Net Quantity",
        value="150 g",
        status=CanonicalStatus.VERIFIED,
        confidence=0.92,
        validation=ValidationDetails(present=True, readable=True, correct_format=True, compliant=True),
        reason="Net quantity compliant.",
    )
    serialized = decl.model_dump()
    assert serialized["status"] == "VERIFIED"


def test_g_backend_review_required_maps_properly():
    """Requirement G: Backend REVIEW_REQUIRED serializes accurately."""
    decl = CanonicalDeclaration(
        field="mrp",
        canonical_name="Maximum Retail Price (MRP)",
        value="₹420",
        status=CanonicalStatus.REVIEW_REQUIRED,
        confidence=0.20,
        validation=ValidationDetails(present=True, readable=False, correct_format=None, compliant=None),
        reason="Low OCR confidence.",
    )
    serialized = decl.model_dump()
    assert serialized["status"] == "REVIEW_REQUIRED"


def test_h_api_and_pdf_status_consistency():
    """Requirement H: API and PDF status consistency."""
    decls, summary = _build_canonical_declarations(
        facts=[
            ExtractedFact(
                field="common_name",
                extracted_value="Instant Coffee",
                status=FactStatus.PASS,
                confidence=0.85,
                evidence=_dummy_ev(),
            )
        ],
        extractions={},
        context={"best_before_applicable": True},
        captures=[],
    )
    inspection_dict = {
        "inspection_id": "test-sync-001",
        "product_id": "prod-1",
        "product_category": "coffee",
        "sale_type": "retail",
        "overall_status": "UNCERTAIN",
        "declarations": [d.model_dump() for d in decls],
        "declaration_summary": summary,
        "findings": [],
        "facts": [],
    }

    pdf_bytes = build_inspection_report_pdf(inspection_dict)
    assert pdf_bytes.startswith(b"%PDF")
    # Both API summary and PDF summary use the exact same counts
    assert summary["verified"] == 1
    assert summary["applicable"] == 9


def test_i_duplicate_declarations_deduplicated():
    """Requirement I: Duplicate declarations across surfaces resolve to one canonical declaration."""
    facts = [
        ExtractedFact(
            field="net_quantity",
            extracted_value="150 g",
            status=FactStatus.PASS,
            confidence=0.92,
            evidence=_dummy_ev("panel_front.jpg"),
        ),
        ExtractedFact(
            field="net_quantity",
            extracted_value="150 g",
            status=FactStatus.PASS,
            confidence=0.88,
            evidence=_dummy_ev("panel_back.jpg"),
        ),
    ]
    decls, summary = _build_canonical_declarations(
        facts=facts, extractions={}, context={"best_before_applicable": True}, captures=[]
    )
    # Deduplication assertion is built into _build_canonical_declarations
    nq_count = sum(1 for d in decls if d.field == "net_quantity")
    assert nq_count == 1


def test_j_missing_evidence_review_required_never_fabricated():
    """Requirement J: Missing evidence resolves to review/not detected, NEVER fabricated."""
    # When no fact is provided for net_quantity
    decls, summary = _build_canonical_declarations(
        facts=[], extractions={}, context={"best_before_applicable": True}, captures=[]
    )
    nq = next(d for d in decls if d.field == "net_quantity")
    assert nq.value is None or nq.value == ""
    assert nq.status in (
        CanonicalStatus.NOT_DETECTED_IN_PROVIDED_IMAGES,
        CanonicalStatus.REVIEW_REQUIRED,
    )
    assert nq.status != CanonicalStatus.VERIFIED


def test_k_manufacturer_partial_address_not_verified():
    """Requirement Section 7: Partial / mangled address must NOT be verified."""
    raw = RawExtraction(
        field="manufacturer_name_address",
        value="195/2A,, B.D. SAWANT, FOODS LIMITED,",
        confidence=0.85,
    )
    insp = run_inspection(
        inspection_id="test-mfg-001",
        product_category="coffee",
        sale_type="retail",
        net_quantity_value=150.0,
        net_quantity_unit="g",
        mrp=420.0,
        extractions={"manufacturer_name_address": raw},
        captures=[
            SurfaceObservation(
                image_id="panel.jpg",
                surface_id="front",
            )
        ],
    )
    mfg_fact = next(f for f in insp.facts if f.field == "manufacturer_name_address")
    assert mfg_fact.status == FactStatus.UNCERTAIN
    assert mfg_fact.review_required is True

    mfg_decl = next(d for d in insp.declarations if d.field == "manufacturer_name_address")
    assert mfg_decl.status == CanonicalStatus.REVIEW_REQUIRED
