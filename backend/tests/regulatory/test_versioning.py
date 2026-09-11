from datetime import date
from backend.regulatory.models import ApprovalState,RuleVersion
from backend.regulatory.versions import RuleVersionSelectionError,select_rule_version
def rv(id,version,start,end=None,state=ApprovalState.ACTIVE):
    return RuleVersion(id=id,module="lmpc",regulation="LMPC",rule_id="R6",version=version,effective_from=date.fromisoformat(start),effective_to=date.fromisoformat(end) if end else None,approval_state=state)
def test_future_rule_does_not_affect_past_inspection():
    selected=select_rule_version([rv("old","2023","2023-01-01"),rv("future","2027","2027-01-01")],module="lmpc",rule_id="R6",inspection_date=date(2026,9,9))
    assert selected.id=="old"
def test_expired_rule_is_not_selected():
    selected=select_rule_version([rv("old","2023","2023-01-01","2025-01-01"),rv("new","2025","2025-01-01")],module="lmpc",rule_id="R6",inspection_date=date(2026,9,9))
    assert selected.id=="new"
def test_unapproved_rule_is_not_selected():
    with __import__("pytest").raises(RuleVersionSelectionError):
        select_rule_version([rv("draft","2027","2027-01-01",state=ApprovalState.DRAFT)],module="lmpc",rule_id="R6",inspection_date=date(2027,2,1))
