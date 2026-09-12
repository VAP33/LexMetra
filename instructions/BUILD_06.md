# Build 06 — Dated RuleVersion Runtime Integration

## Purpose

Build 05 created the authoritative `RuleVersion` selector and amendment impact
calculation. Build 06 connects that selector to the deterministic inspection
engine without replacing the existing legal implementation dataset.

## What changed

- Added `backend/regulatory/runtime.py`.
- `run_inspection()` now accepts optional `inspection_date`, `rule_versions`, and
  `regulatory_module` arguments.
- A dated inspection requires an explicit RuleVersion registry. It **never**
  silently falls back to the current `rules.json` catalogue.
- Only `SCHEDULED` and `ACTIVE` versions can be selected, using Build 05's
  selector and overlap safety.
- Selected version identity, effective dates, and source provenance are copied
  onto the runtime rule object, so existing `_make_fact()` and `_finding()` paths
  continue to carry `rule_version` without rewriting every evaluator.
- `ProductInspection.inspection_date` and `applicable_rule_version` are now
  populated for dated inspections.
- The existing undated call path remains backward-compatible.
- `rules.json` remains the implementation catalogue. Build 06 does not invent
  substantive legal text from a registry record; the registry selects the dated
  authoritative identity and provenance. A future build can move the full
  substantive rule payload behind the approved registry once ingestion and
  approval workflows are wired to persistence.

## Apply

From the LexMetra repository root:

```powershell
python apply_build06.py
```

The script refuses to apply if Build 05's regulatory model/version files are
missing.

## Verify

```powershell
$env:PYTHONPATH="backend"
python -m pytest backend\tests\test_build05_rule_versioning.py backend\tests\test_build06_rule_version_runtime.py -q
python -m py_compile backend\regulatory\runtime.py backend\rule_engine.py
```

Then run the existing full test suite before pushing the verified result:

```powershell
$env:PYTHONPATH="backend"
python -m pytest -q
```

## Safety contract

1. No dated inspection uses an undated/current rule fallback.
2. Future versions cannot apply to an earlier inspection date.
3. `APPROVED` alone is insufficient. A version must be `SCHEDULED` or `ACTIVE`.
4. Overlapping applicable versions fail closed.
5. Historical rule versions are not overwritten by the runtime adapter.
6. Existing PDF/report/audit/auth/frontend paths are not modified by Build 06.
7. The rule engine remains deterministic. No LLM is introduced into legal
   decision-making.
