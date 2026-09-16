"""
Consumer -> Authority Reporting Workflow & Authority Dashboard Engine (USP 3).

Enables consumers and field inspectors to escalate non-compliant packages,
counterfeit signals, or tampering evidence directly into the Legal Metrology
and FSSAI Authority enforcement queue.

LIFECYCLE:
SUBMITTED -> UNDER_REVIEW -> INVESTIGATION_ORDERED -> NOTICE_ISSUED -> RESOLVED / DISMISSED
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import config

logger = logging.getLogger("lexmetra.reporting")

REPORTS_STORE_FILE = Path(__file__).resolve().parent / "db" / "data_local" / "authority_cases.json"
REPORTS_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class CaseAction:
    action_id: str
    timestamp: str
    officer_username: str
    action_type: str  # "ASSIGNED", "REVIEW_STARTED", "SHOW_CAUSE_NOTICE", "SEIZURE_ORDERED", "SAMPLE_COLLECTED", "PENALTY_LEVIED", "CLOSED"
    notes: str
    statutory_clause: Optional[str] = None


@dataclass
class AuthorityCase:
    case_id: str
    report_id: str
    inspection_id: str
    created_at: str
    updated_at: str
    status: str  # "SUBMITTED", "UNDER_REVIEW", "NOTICE_ISSUED", "INVESTIGATION_ORDERED", "RESOLVED", "DISMISSED"
    priority: str  # "HIGH", "MEDIUM", "LOW"
    reporter_type: str  # "Consumer", "Field Inspector", "Retail Merchant"
    reporter_name: Optional[str]
    reporter_contact: Optional[str]
    product_name: str
    product_id: Optional[str]
    category: str
    issue_category: str  # "Misleading Net Weight", "Price Alteration / Dual MRP", "Expired / Best Before Violation", "Missing Declarations", "Suspected Alteration"
    details: str
    location: Optional[str]
    retailer_name: Optional[str]
    lmpc_verdict: str  # "COMPLIANT", "VIOLATION", "UNCERTAIN"
    lmpc_violations_count: int
    fssai_status: Optional[str]
    integrity_status: Optional[str]
    evidence_image_urls: List[str]
    assigned_officer: Optional[str] = None
    actions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# In-memory case cache with JSON file persistence
_CASES: Dict[str, AuthorityCase] = {}


def _load_cases() -> None:
    global _CASES
    if REPORTS_STORE_FILE.exists():
        try:
            with open(REPORTS_STORE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for c_dict in data:
                c = AuthorityCase(**c_dict)
                _CASES[c.case_id] = c
        except Exception as e:
            logger.warning("Could not load authority cases from %s: %s", REPORTS_STORE_FILE, e)

    # Seed default demonstration cases if empty
    if not _CASES:
        _seed_demo_cases()


def _save_cases() -> None:
    try:
        data = [c.to_dict() for c in _CASES.values()]
        with open(REPORTS_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error("Could not persist authority cases: %s", e)


def _seed_demo_cases() -> None:
    now_iso = datetime.now().isoformat()
    demo_cases = [
        AuthorityCase(
            case_id="CASE-2026-0842",
            report_id="REP-2026-0842",
            inspection_id="64934436:scan-1e48cc41",
            created_at=now_iso,
            updated_at=now_iso,
            status="UNDER_REVIEW",
            priority="HIGH",
            reporter_type="Consumer",
            reporter_name="Ramesh Sharma",
            reporter_contact="ramesh.s@example.com",
            product_name="BRU Instant Coffee 150g Pouch",
            product_id="64934436",
            category="Food / Beverage",
            issue_category="Misleading Net Weight",
            details="Package declares Net Weight 150g but shelf measurement indicated 100g. Retailer charging full MRP Rs 420.",
            location="Super Bazaar, MG Road, Pune",
            retailer_name="Shree Ganesh Retailers",
            lmpc_verdict="COMPLIANT",
            lmpc_violations_count=0,
            fssai_status="VERIFIED / MATCH",
            integrity_status="NO SIGNIFICANT DIFFERENCE DETECTED",
            evidence_image_urls=["/uploads/Screenshot_2026-09-06-22-06-12-38_92460851df6f172a4592fca41cc2d2e6.jpg"],
            assigned_officer="inspector",
            actions=[
                {
                    "action_id": "ACT-101",
                    "timestamp": now_iso,
                    "officer_username": "inspector",
                    "action_type": "ASSIGNED",
                    "notes": "Case assigned to District Legal Metrology Officer (Pune Division).",
                    "statutory_clause": "Rule 6(1)(e) Legal Metrology Rules",
                }
            ],
        ),
        AuthorityCase(
            case_id="CASE-2026-0841",
            report_id="REP-2026-0841",
            inspection_id="INSP-88219401",
            created_at=now_iso,
            updated_at=now_iso,
            status="NOTICE_ISSUED",
            priority="HIGH",
            reporter_type="Field Inspector",
            reporter_name="Field Inspector",
            reporter_contact="inspector@lexmetra.gov.in",
            product_name="Traya Hair Actives 30ml",
            product_id="TRAYA-30ML",
            category="Cosmetics / Ayurvedic",
            issue_category="Missing Mandatory Declarations",
            details="No Unit Sale Price (USP) declared. Missing Consumer Care contact number on outer retail carton.",
            location="Apollo Pharmacy, Sector 14, Gurugram",
            retailer_name="Apollo Pharmacy",
            lmpc_verdict="VIOLATION",
            lmpc_violations_count=2,
            fssai_status="NOT APPLICABLE",
            integrity_status="POTENTIAL ALTERATION DETECTED",
            evidence_image_urls=["/uploads/TRAYA BACK.jpg"],
            assigned_officer="inspector",
            actions=[
                {
                    "action_id": "ACT-102",
                    "timestamp": now_iso,
                    "officer_username": "inspector",
                    "action_type": "SHOW_CAUSE_NOTICE",
                    "notes": "Form 4 Show Cause Notice issued to Packer under Section 36(1) of Legal Metrology Act, 2009.",
                    "statutory_clause": "Rule 6(11) USP Mandate & Section 36(1) LM Act",
                }
            ],
        ),
    ]
    for c in demo_cases:
        _CASES[c.case_id] = c
    _save_cases()


def create_consumer_report(
    inspection_id: str,
    product_name: str,
    issue_category: str,
    details: str,
    reporter_type: str = "Consumer",
    reporter_name: Optional[str] = None,
    reporter_contact: Optional[str] = None,
    product_id: Optional[str] = None,
    category: str = "Packaged Commodity",
    location: Optional[str] = None,
    retailer_name: Optional[str] = None,
    lmpc_verdict: str = "UNCERTAIN",
    lmpc_violations_count: int = 0,
    fssai_status: Optional[str] = None,
    integrity_status: Optional[str] = None,
    evidence_image_urls: Optional[List[str]] = None,
) -> AuthorityCase:
    """Submits a new consumer/inspector complaint and creates an official Authority Case."""
    _load_cases()
    suffix = uuid.uuid4().hex[:4].upper()
    case_id = f"CASE-2026-{suffix}"
    report_id = f"REP-2026-{suffix}"
    now_iso = datetime.now().isoformat()

    priority = "HIGH" if (lmpc_verdict == "VIOLATION" or "alteration" in str(integrity_status).lower()) else "MEDIUM"

    c = AuthorityCase(
        case_id=case_id,
        report_id=report_id,
        inspection_id=inspection_id,
        created_at=now_iso,
        updated_at=now_iso,
        status="SUBMITTED",
        priority=priority,
        reporter_type=reporter_type,
        reporter_name=reporter_name or "Anonymous Citizen",
        reporter_contact=reporter_contact or "N/A",
        product_name=product_name or "Packaged Commodity",
        product_id=product_id,
        category=category,
        issue_category=issue_category,
        details=details,
        location=location or "Not specified",
        retailer_name=retailer_name or "Not specified",
        lmpc_verdict=lmpc_verdict,
        lmpc_violations_count=lmpc_violations_count,
        fssai_status=fssai_status,
        integrity_status=integrity_status,
        evidence_image_urls=evidence_image_urls or [],
        assigned_officer="inspector",
        actions=[
            {
                "action_id": f"ACT-{uuid.uuid4().hex[:6].upper()}",
                "timestamp": now_iso,
                "officer_username": "system",
                "action_type": "REPORT_FILED",
                "notes": f"Automated complaint docket created via Consumer Escalation Gateway ({report_id}).",
            }
        ],
    )
    _CASES[case_id] = c
    _save_cases()
    return c


def list_authority_cases(
    status_filter: Optional[str] = None,
    priority_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Returns all authority enforcement cases."""
    _load_cases()
    res = list(_CASES.values())
    if status_filter and status_filter.upper() != "ALL":
        res = [c for c in res if c.status.upper() == status_filter.upper()]
    if priority_filter and priority_filter.upper() != "ALL":
        res = [c for c in res if c.priority.upper() == priority_filter.upper()]

    # Sort newest first
    res = sorted(res, key=lambda c: c.created_at, reverse=True)
    return [c.to_dict() for c in res]


def get_case_by_id(case_id: str) -> Optional[Dict[str, Any]]:
    _load_cases()
    c = _CASES.get(case_id)
    if not c:
        # Try matching by report_id
        for val in _CASES.values():
            if val.report_id == case_id:
                return val.to_dict()
        return None
    return c.to_dict()


def record_officer_action(
    case_id: str,
    officer_username: str,
    action_type: str,
    notes: str,
    statutory_clause: Optional[str] = None,
    new_status: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Records an immutable statutory action taken by an authorized Legal Metrology officer."""
    _load_cases()
    c = _CASES.get(case_id)
    if not c:
        return None

    now_iso = datetime.now().isoformat()
    action = {
        "action_id": f"ACT-{uuid.uuid4().hex[:6].upper()}",
        "timestamp": now_iso,
        "officer_username": officer_username,
        "action_type": action_type,
        "notes": notes,
        "statutory_clause": statutory_clause or "Legal Metrology Act, 2009",
    }
    c.actions.append(action)
    c.updated_at = now_iso

    if new_status:
        c.status = new_status
    elif action_type == "SHOW_CAUSE_NOTICE":
        c.status = "NOTICE_ISSUED"
    elif action_type == "SEIZURE_ORDERED":
        c.status = "INVESTIGATION_ORDERED"
    elif action_type == "CLOSED":
        c.status = "RESOLVED"
    elif c.status == "SUBMITTED":
        c.status = "UNDER_REVIEW"

    _save_cases()
    return c.to_dict()
