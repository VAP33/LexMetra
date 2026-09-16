# DECISIONS — FSSAI-01

## 2026-09-16 — Absence is UNCERTAIN
- Context: Pack photos often miss the FSSAI mark even when it exists on another panel.
- Decision: never FAIL for missing licence/veg/ingredients/date from images alone.
- Why: §1.3 absence ≠ non-compliance, applied to a second domain.
- Reversible? FAIL would require complete-coverage evidence rules + legal verification.

## 2026-09-16 — Do not extend ProductInspection this pass
- Decision: parallel GET + SQL table (ARCH-01 D-07).
- Why: `extra="forbid"` on the frozen model.
- Reversible? Future optional `module_statuses` SCR.
