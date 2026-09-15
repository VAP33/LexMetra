# RULE-01 — Rule Engine → OpenL Tablets Migration

This directory is RULE-01's persistent context, per CDD Instructions §13 and the
Agent Execution Guide §4. Read `STATE.md` and the latest `WORKLOG.md` entries
before resuming any work here after a context wipe or new conversation — do not
rely on memory.

Files:
- `TASK.md` — mission, scope, contracts (source: CDD package, Wave 1).
- `CONTEXT.md` — repo facts RULE-01 needs, as of assignment.
- `CONTRACTS.md` — what RULE-01 owns/consumes/produces.
- `STATE.md` — current phase, verified facts, next action.
- `WORKLOG.md` — chronological log of actual commands run and their output.
- `DECISIONS.md` — recorded decisions, including any assumptions made in
  place of a blocking dependency that had not formally executed.
- `HANDOFF.md` — summary for the next agent / future self (esp. DEVOPS-01, TEST-01).

Working artifacts (created as the migration proceeds) live under
`backend/openl/` (resolver client + rule-project sources + deploy scripts), not
in this docs directory.
