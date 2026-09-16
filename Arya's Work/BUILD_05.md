# Build 05 — Rule Versioning & Amendment/RAG Impact (Corrected)

Baseline: Build 4 / commit 60473ae

Purpose:
- Add date-aware RuleVersion selection without changing the inspection verdict path yet.
- Reject overlapping rule-version intervals.
- Calculate exact affected RAG chunk IDs for amendment changes.
- Preserve approval gating and historical immutability.

Important:
- Do NOT apply the old amendments_patch.diff. It was malformed and has been superseded by this corrected patch.
- Do NOT commit until the commands below pass.

Apply:
1. Keep the existing Build 04 regulatory compatibility exports in backend/regulatory/__init__.py and add the three exports from versions.py.
2. Copy backend/regulatory/versions.py and backend/tests/test_build05_rule_versioning.py from this package.
3. Apply amendments_patch.diff:
   git apply --check amendments_patch.diff
   git apply amendments_patch.diff

Verify:
  $env:PYTHONPATH="backend"
  python -m pytest backend/tests/test_build05_rule_versioning.py -q
  python -m py_compile backend/regulatory/versions.py backend/amendments.py
  git diff --check

Expected: all Build 05 tests pass and git diff --check is clean.

This build does NOT integrate RuleVersion selection into run_inspection(). That is deliberately deferred to the next verified build so historical-rule selection is tested independently first.
