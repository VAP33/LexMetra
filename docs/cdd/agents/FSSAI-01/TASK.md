# CDD Package — FSSAI-01 (FSSAI Cross-Verification Layer)

(Verbatim from `CDD/Wave 2/FSSAI-01.md`, copied here for persistent context.)

**Agent ID:** FSSAI-01
**Depends on:** RULE-02's generalized versioning/deploy pipeline (coordinate live if timing is tight — don't fork a second scheme while waiting).

**Purpose:** Add FSSAI (food safety) rules as a genuinely **parallel** regulatory domain alongside Legal Metrology — never merged into the same rule set, per the vision's explicit USP5 requirement that these stay distinct domains with distinct legal bases.

**You must:**
1. Read `backend/regulatory/models.py`'s `RegulatoryContext.regulatory_modules` field — this already anticipates multiple rule domains (`"lmpc"` is the existing value). Add `"fssai"` as a new module value; do not repurpose or overload the existing `"lmpc"` module for food-safety rules.
2. Source real FSSAI labeling requirements (e.g. FSSAI packaging and labeling regulations) the same way RAG-01 sourced Legal Metrology text — real regulatory text, sourced and documented, not fabricated.
3. Encode FSSAI rules following the exact same pattern as `rules/rules.json` (per-rule `verification_status: needs_official_verification`, effective dates, thresholds) — a new `rules_fssai.json` or a namespaced section, coordinate the exact file/schema shape with ARCH-01 since it's a new top-level artifact, not a change to the existing frozen file.
4. Route FSSAI rule execution through the same `RuleSet Resolver` pattern RULE-01 built for OpenL, using RULE-02's versioned-deploy pipeline — FSSAI decision tables are a new OpenL rule project, not a fork of the Legal Metrology one, but they use the identical deployment mechanism.
5. Findings from FSSAI rules populate the same `RuleFinding` shape (`01-CONTRACTS.md` §1.2) with the same four-status invariant — an `overall_status` for an inspection may need to reflect **both** domains' verdicts (e.g. LMPC-compliant but FSSAI-non-compliant); design how `ProductInspection` communicates this without conflating the two domains into one number — propose the shape to ARCH-01 as a Scope Change Request since it likely needs a small, additive schema extension (e.g. per-module status breakdown) rather than overloading the single `overall_status` field.

**You must NOT:**
- Merge FSSAI rules into `rules/rules.json` or `backend/rule_engine.py`/`exemption.py` — these are Legal Metrology-specific and must stay a distinct domain, per the vision's own explicit requirement.
- Invent a second `RegulatoryContext` — extend the existing one's `regulatory_modules` field.

## CONTEXT.md

- `RegulatoryContext.regulatory_modules` already exists as a list field, anticipating exactly this kind of extension — check its current usage in `rule_engine.py` before assuming you need to add plumbing that's already there.
- FSSAI cross-verification is entirely `MISSING` today — this is genuinely greenfield work, unlike most other Final Wave agents who are extending existing code.
- The Legal Metrology/FSSAI distinction matters legally, not just architecturally: they're different Acts with different enforcement bodies. Do not present a combined verdict that obscures which domain found what.

## CONTRACTS.md

**Contract you consume:** `RegulatoryContext` (extend, don't fork), `RuleFinding`/`ExtractedFact` shapes, RULE-02's versioned-deploy pipeline.
**Contract you produce (proposed, needs ARCH-01 sign-off):** a per-module status breakdown addition to `ProductInspection` — draft the shape, submit as an SCR, implement once approved.
