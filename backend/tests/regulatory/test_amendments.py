from datetime import datetime
import pytest
from backend.amendments import calculate_impact,transition_amendment
from backend.regulatory.models import AmendmentChange,AmendmentDraft,ApprovalState
def draft():
    return AmendmentDraft(id="a1",module="lmpc",source_document_id="doc1",extracted_at=datetime(2026,9,9))
def test_amendment_requires_review_before_approval():
    with pytest.raises(ValueError): transition_amendment(draft(),ApprovalState.APPROVED)
def test_amendment_transition_is_explicit():
    d=transition_amendment(draft(),ApprovalState.EXTRACTED); d=transition_amendment(d,ApprovalState.AI_PARSED)
    d=transition_amendment(d,ApprovalState.PENDING_REVIEW); d=transition_amendment(d,ApprovalState.APPROVED)
    assert d.approval_state is ApprovalState.APPROVED
def test_impact_report_is_deterministic():
    impact=calculate_impact([AmendmentChange(rule_id="R6(11)",change_type="MODIFIED",changed_fields=["unit_sale_price"],threshold_changes=[{"value":"25","unit":"kg"}])],"lmpc")
    assert impact.affected_rules==("R6(11)",); assert impact.affected_fields==("unit_sale_price",); assert impact.affected_modules==("lmpc",)
