from datetime import date
import pytest
from backend.amendments import calculate_impact
from backend.regulatory.models import ApprovalState,AmendmentChange,KnowledgeChunk,RuleVersion
from backend.regulatory.versions import RuleVersionSelectionError,select_rule_version,validate_rule_version_intervals
def _version(version_id,version,start,end,state):
    return RuleVersion(id=version_id,module="LMPC",regulation="LMPC Rules",rule_id="rule-6",version=version,effective_from=start,effective_to=end,approval_state=state)
def test_historical_version_selection():
    old=_version("rv-old","2024.1",date(2024,1,1),date(2025,1,1),ApprovalState.ACTIVE); new=_version("rv-new","2025.1",date(2025,1,1),None,ApprovalState.ACTIVE)
    assert select_rule_version([old,new],module="LMPC",rule_id="rule-6",inspection_date=date(2024,8,1)).id=="rv-old"
    assert select_rule_version([old,new],module="LMPC",rule_id="rule-6",inspection_date=date(2025,8,1)).id=="rv-new"
def test_future_or_unapproved_version_cannot_apply():
    with pytest.raises(RuleVersionSelectionError):
        select_rule_version([_version("rv-future","2027.1",date(2027,1,1),None,ApprovalState.APPROVED)],module="LMPC",rule_id="rule-6",inspection_date=date(2026,9,10))
def test_approved_version_must_become_scheduled_or_active_before_application():
    with pytest.raises(RuleVersionSelectionError):
        select_rule_version([_version("rv-approved","2026.1",date(2026,1,1),None,ApprovalState.APPROVED)],module="LMPC",rule_id="rule-6",inspection_date=date(2026,9,10))
def test_overlap_is_rejected():
    assert validate_rule_version_intervals([_version("rv-1","1",date(2025,1,1),date(2026,6,1),ApprovalState.ACTIVE),_version("rv-2","2",date(2026,5,1),None,ApprovalState.SCHEDULED)])
def _chunk(chunk_id,start,end,rule_id="rule-6"):
    return KnowledgeChunk(id=chunk_id,module="LMPC",department="Consumer Affairs",regulation="LMPC Rules",document_id="doc-1",document_version="v1",rule_version="2025.1",rule_id=rule_id,effective_from=start,effective_to=end,index_version="idx-1",text="sample legal text")
def test_amendment_impact_identifies_only_overlapping_chunks():
    change=AmendmentChange(rule_id="rule-6",change_type="TEXT",effective_from=date(2026,4,1),new_text="updated")
    impact=calculate_impact([change],"LMPC",rag_chunks=[_chunk("affected",date(2026,1,1),None),_chunk("historical",date(2024,1,1),date(2025,1,1)),_chunk("other-rule",date(2026,1,1),None,rule_id="rule-8")])
    assert impact.affected_rag_chunks==("affected",)
def test_amendment_impact_accepts_generator_inputs():
    impact=calculate_impact((c for c in [AmendmentChange(rule_id="rule-6",change_type="TEXT",effective_from=date(2026,4,1))]),"LMPC",rag_chunks=(c for c in [_chunk("affected",date(2026,1,1),None)]))
    assert impact.affected_rules==("rule-6",); assert impact.affected_rag_chunks==("affected",)
