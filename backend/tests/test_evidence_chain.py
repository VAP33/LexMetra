"""EVID-01 evidence chain builder — no database required."""
from evidence_view import EvidenceChainResponse, build_evidence_chain
from schema import UNATTRIBUTED_IMAGE_ID


def test_evidence_chain_surfaces_invariants_and_verification_status():
    detail = {
        "inspection_id": "insp-e1",
        "overall_status": "UNCERTAIN",
        "review_required": True,
        "reviewed": False,
        "disclaimer": "screening aid",
        "facts": [
            {
                "field": "mrp",
                "extracted_value": "Rs 50",
                "status": "UNCERTAIN",
                "confidence": 0.41,
                "ocr_confidence": 0.41,
                "review_required": True,
                "reason": "low OCR confidence is not non-compliance",
                "evidence": [
                    {
                        "image_id": "front.jpg",
                        "bbox": {"x": 10, "y": 20, "width": 40, "height": 12},
                    }
                ],
                "validation": {"source_engine": "tesseract", "fusion_state": "SINGLE_SOURCE"},
            },
            {
                "field": "manufacturer_name_address",
                "extracted_value": None,
                "status": "UNCERTAIN",
                "confidence": 0.0,
                "reason": "NOT_DETECTED_IN_PROVIDED_IMAGES",
                "evidence": [{"image_id": UNATTRIBUTED_IMAGE_ID}],
            },
        ],
        "findings": [
            {
                "rule_id": "LMPC-2011-R6-DECLARATIONS",
                "status": "UNCERTAIN",
                "reason": "insufficient coverage",
                "confidence": 0.2,
                "review_required": True,
                "verification_status": "needs_official_verification",
                "required_evidence": ["manufacturer"],
                "missing_evidence": ["manufacturer"],
                "evidence": [],
            }
        ],
    }
    chain = build_evidence_chain(detail)
    assert isinstance(chain, EvidenceChainResponse)
    dumped = chain.model_dump()
    assert dumped["honesty"]["low_confidence_is_not_noncompliance"]
    assert dumped["honesty"]["not_observed_is_not_missing"]
    assert chain.findings[0].verification_status == "needs_official_verification"
    assert chain.regions[0].source_engine == "tesseract"
    assert chain.regions[0].confidence == 0.41
    assert chain.overall_status == "UNCERTAIN"


def test_evidence_endpoint_requires_auth(api_client):
    resp = api_client.get("/inspections/does-not-exist/evidence")
    assert resp.status_code == 401
