from datetime import date
from backend.models import ApprovalState, RuleVersion
from backend.versioning import select_rule_version


def rv(state, version, start):
    return RuleVersion(
        id=f"r-{version}", module="LMPC", regulation="LMPC", rule_id="rule-1", version=version,
        effective_from=date.fromisoformat(start), effective_to=None,
        approval_state=state,
    )


def test_approved_future_candidate_is_not_runtime_eligible():
    approved = rv(ApprovalState.APPROVED, "2.0", "2026-01-01")
    assert select_rule_version([approved], date(2026, 6, 1)) is None


def test_only_active_versions_are_runtime_eligible_by_date():
    scheduled = rv(ApprovalState.SCHEDULED, "2.0", "2026-01-01")
    active = rv(ApprovalState.ACTIVE, "1.0", "2025-01-01")
    chosen = select_rule_version([active, scheduled], date(2026, 6, 1))
    assert chosen is active
