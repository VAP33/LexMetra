# Workstream 2: Legal Engine Versioning (multi-versioned rule engine)

## Read first
`handoff/00_PROJECT_STATUS_AND_SPLIT.md` — shared ground truth and the
non-negotiable contract. Don't skip it.

## What's actually true right now (verified by grep, not opinion)
`rules.json` already has `effective_from`/`effective_to` fields on every
rule. `rule_engine.py` never reads them (`grep -c "effective_from"
rule_engine.py` → 0). Every rule is always treated as currently in force.
There is no concept of "what did this rule require on a given past date."
Your "multi-versioned deterministic rule engine that applies the correct
LMPC requirements based on applicability, exemptions, amendments, and
effective dates" does not exist yet. This is what you're building.

## The core design problem

A single `rule_id` like `LMPC-2011-R7-2-FONT` currently represents ONE
version of that rule. But Rule 7(2)'s numeral-height table was actually
amended (GSR 629(E), effective 2018-01-01) — before that date, different
thresholds applied. Right now there's only one `LMPC-2011-R7-2-FONT` record
in `rules.json`, holding only the POST-amendment thresholds, with no
representation of the pre-2018 version at all. If you ever need to evaluate
a historical inspection or explain "what changed and when" to a judge, you
can't.

## What to build

1. **Restructure `rules.json` into rule "families."** Each family shares a
   stable identifier (e.g. `family: "R7-2-FONT"`) and contains multiple
   dated versions, each with its own `effective_from`/`effective_to` and its
   own `threshold`/`requirements`. Example shape:
   ```json
   {
     "family": "R7-2-FONT",
     "versions": [
       {
         "rule_id": "LMPC-2011-R7-2-FONT-V1",
         "effective_from": "2011-04-01",
         "effective_to": "2017-12-31",
         "threshold": { "...pre-2018 bands..." }
       },
       {
         "rule_id": "LMPC-2011-R7-2-FONT-V2",
         "effective_from": "2018-01-01",
         "effective_to": null,
         "threshold": { "...current bands..." }
       }
     ]
   }
   ```
   **Do this as a migration, not a rewrite** — preserve every existing
   `rule_id` string as the *current* version's id, so `rule_engine.py`'s
   existing `_find_rule()` lookups keep working without you having to touch
   every call site on day one.

2. **Add a rule-resolution function**: given a `family` and an
   `inspection_date` (default: today), return the version whose
   `effective_from <= inspection_date < effective_to (or open-ended)`. This
   is the actual "multi-versioned" logic — a pure function, easy to unit
   test with fabricated dates before touching the real engine.

3. **Wire `inspection_date` through.** `schema.py`'s `ProductInspection`
   already has `inspection_date: Optional[str]` and
   `applicable_rule_version: Optional[str]` fields — currently unused
   placeholders. Populate them: when an inspection runs, resolve every rule
   family to its applicable version for that date, record which version was
   used in `applicable_rule_version` (or per-finding, in
   `RuleFinding.rule_version`), and make `rule_engine.py`'s lookups go
   through your new resolution function instead of a flat dict lookup.

4. **Legal Metrology-specific tricky case worth handling explicitly**:
   amendments are sometimes announced with a future effective date (a
   gazette notification dated today taking effect in 90 days). Your
   `rules.json` should be able to represent a version whose
   `effective_from` is in the future, and your resolver must correctly NOT
   apply it yet. Write a test for this specifically.

5. **Verification workflow.** Every rule in the current file is flagged
   `verification_status: "needs_official_verification"`. Design (don't
   necessarily fully build, unless you have time) a simple way for your
   Legal Lead to flip a specific *version* to `"verified"` — verification is
   per-version, not per-family, since confirming the 2018+ thresholds says
   nothing about whether the pre-2018 ones were encoded correctly.

## What NOT to do

- Don't invent amendment dates/thresholds you can't source. If you don't
  know what a rule looked like before a given amendment, encode only the
  version you can verify and leave a clear `TODO` rather than guessing.
- Don't change `LMPC-2011-R6-DECLARATIONS`' `requirements[].field` names —
  Workstream 1's extraction code and `main.py`'s `_prepare_extractions()`
  bridge depend on those exact strings. If your restructuring changes them,
  you must also update that bridge and say so loudly in your handoff notes.

## What to test and report back

- Unit tests with fabricated dates: a date before an amendment, exactly on
  the effective date, and after — confirm the resolver picks the right
  version each time, including the future-effective-date edge case.
- Re-run the existing rule_engine test scenarios (see
  `ENGINE_UPGRADE_NOTES.md` in the project root for what was already
  verified) with today's date and confirm identical output — your
  refactor must not change current behavior, only add the ability to ask
  about other dates.

## Files to upload to this Claude session

`rules/rules.json`, `backend/rule_engine.py`, `backend/exemption.py`,
`backend/schema.py`, `handoff/00_PROJECT_STATUS_AND_SPLIT.md`, and
`ENGINE_UPGRADE_NOTES.md`.
