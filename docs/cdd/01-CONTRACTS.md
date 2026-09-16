# 01 — Frozen Contracts (LexMetra)

**Owner:** ARCH-01. **No agent changes a contract in this file without ARCH-01 sign-off.**
A field change proposal is a Scope Change Request (CDD Instructions §46), not a unilateral edit.
**Last updated:** 2026-09-15 @ commit `ccd795c`

This file freezes the two contracts that hold the parallel work together:

1. **The canonical pipeline contract** (`ExtractedFact` / `ProductInspection`) — *exists today* in `backend/schema.py`; frozen here.
2. **The RuleSet Resolver → OpenL contract** — *does not exist yet*; its shape is *defined* here so RULE-01 can build against it. ARCH-01 owns keeping this in sync; RULE-01 owns the implementation.

---

## Contract 1 — Canonical pipeline contract (EXISTS, FROZEN)

**Source of truth:** `backend/schema.py`
**Producers:** OCR (`ocr_extraction.py`), CV (`region_detection.py`, geometry/calibration), rule engine.
**Consumers:** rule engine, persistence, report generation, every frontend surface.

### 1.1 Why this is the one contract that matters

It is the seam every module already imports across. It is deliberately
**evidence-first**: it describes what was *observed* and how *confident* the
observation is — it never encodes legal policy (that lives in `rules/rules.json`
and is decided only by the rule engine). Any new module (Consumer scan,
Authority case, Evidence viewer, OpenL resolver) targets *this*, not a fork of it.

### 1.2 The two anchor models (do not rename, do not remove fields)

`ExtractedFact` — one declaration field, extracted then evaluated:

```
field: str
extracted_value: Optional[str]
status: FactStatus            # PASS | FAIL | UNCERTAIN | EXEMPT
confidence: float [0..1]      # model/evidence confidence, NOT legal certainty
rule_id / rule_version: Optional[str]
evidence: List[EvidenceReference]     # preferred multi-capture pointer
evidence_image / bbox                 # backward-compatible single-image pointer
measurement_mode / measured_value / measured_unit
raw_text / normalized_value / label / canonical_field / canonical_name / canonical_status
validation / ocr_confidence / extraction_confidence / decision_confidence
reason: str
review_required: bool
```

`ProductInspection` — the complete inspection result (the engine's verdict shape):

```
inspection_id: str
product_category / sale_type / inspection_date / applicable_rule_version
package_weight_or_volume / package_weight_unit / geometry
captures: List[SurfaceObservation]
facts: List[ExtractedFact]
declarations: List[CanonicalDeclaration]  + declaration_summary: Dict[str,int]
findings: List[RuleFinding]
product_identity: Optional[ProductIdentity]
overall_status: FactStatus                # PASS | FAIL | UNCERTAIN | EXEMPT
exempt_reason: Optional[str]
summary: InspectionSummary
evidence_complete: bool / review_required: bool
disclaimer: str  (screening aid, not a legal determination)
```

`RuleFinding` — result of evaluating **one** legal rule (this is the per-rule
verdict shape OpenL must reproduce):

```
rule_id: str / rule_version: Optional[str]
status: FactStatus            # PASS | FAIL | UNCERTAIN | EXEMPT
requirement_id / requirement_description
reason: str
evidence: List[EvidenceReference]
required_evidence / missing_evidence: List[str]
confidence: float [0..1]
review_required: bool
verification_status: Optional[str]
```

### 1.3 Invariants that MUST NOT be violated (they encode legal-safety guarantees)

These are not stylistic; each one prevents a class of silent legal defect that
already bit this codebase. Anyone proposing a change touching them must explain
how the guarantee is preserved.

1. **`FactStatus` has exactly four members: `PASS`, `FAIL`, `UNCERTAIN`, `EXEMPT`.**
   OpenL output maps onto these four and no others. No fifth verdict.
2. **Confidence ≠ legality.** `confidence` / `ocr_confidence` are about *readability*;
   `status` is the legal/evidence evaluation. Low confidence must never be silently
   converted into `FAIL`.
3. **Absence ≠ non-compliance.** "Not detected in the provided images" with
   insufficient coverage yields `UNCERTAIN`, never `FAIL`. See
   `CanonicalStatus.NOT_DETECTED_IN_PROVIDED_IMAGES`.
4. **Conflicting readings are a statement about the READING, never the package.**
   `EvidenceAgreement.CONFLICTING` caps a finding at `UNCERTAIN`; it is not a breach.
   `EvidenceAgreement.permits_definitive_finding()` is the single authority on
   which agreement states may reach PASS/FAIL — the engine may not disagree with it.
5. **Provenance breaks must be conspicuous.** A missing source image is
   `UNATTRIBUTED-NO-SOURCE-IMAGE`, never a plausible filename. Every legal finding
   must be traceable to its evidence.
6. **Every output carries the `disclaimer`** — automated screening aid, not a legal
   determination; findings require an authorized Legal Metrology officer.

### 1.4 Change protocol

- Additive optional fields (new `Optional[...]` with a safe default) → propose to
  ARCH-01; usually approved fast because existing consumers keep working.
- Renames, removals, type changes, or any change to §1.3 invariants → **blocked by
  default**; requires a written Scope Change Request and ARCH-01 sign-off before code.
- `ProductInspection.model_config = extra="forbid"` — unknown fields are rejected on
  purpose. Do not relax it to smuggle fields in.

---

## Contract 2 — RuleSet Resolver → OpenL (NEW, DEFINED, not yet built)

**Owned by (doc/shape):** ARCH-01. **Owned by (implementation):** RULE-01.
**Status:** shape frozen enough for RULE-01 to start; exact request/response JSON is
finalized here *jointly* once RULE-01 has a first `openltablets/ws` decision table
deployed and TEST-01's differential harness can compare it to `rule_engine.py`.

### 2.1 Purpose and placement

This is the new seam between existing evidence-normalization code and the new OpenL
REST call. It exists so the engine can be swapped **without any downstream change**:
report generation, DB persistence, and frontend must not know or care whether a
verdict came from `rule_engine.py` or OpenL.

```
 OCR/CV ──▶ ExtractedFact[] ─┐
                             ├─▶ RuleSet Resolver ──HTTP──▶ OpenL RuleServices (openltablets/ws)
 RegulatoryContext ──────────┘         │                          │
                                       └──────────────◀───────────┘
                                   verdict mapped back to ProductInspection.findings (RuleFinding[])
```

### 2.2 Input (what the resolver sends)

- **Facts:** an `ExtractedFact` set (Contract 1).
- **Regulatory context:** the **existing** `RegulatoryContext` from `backend/models.py`
  (re-exported via `backend/regulatory/models.py`). **Do not invent a second one.**
  Relevant fields the resolver must pass through: `product_category`, `commodity_type`,
  `package_type`, `net_quantity`, `unit`, `sale_type`, `consumer_type`, `is_imported`,
  `country`, `regulatory_modules`, `inspection_date` (**required** — drives rule
  versioning), `jurisdiction` (default `"IN"`), `special_conditions`.
- **Rule selection:** `module` (e.g. `"lmpc"`), `jurisdiction`, and `effective_date`
  (= `inspection_date`) so OpenL evaluates the *version in force on that date*,
  mirroring the engine's existing `apply_rule_versions(...)` dated-inspection rule.
  A dated request with no resolvable rule version is an error, not a fallback to
  "today" — this preserves invariant against legally time-travelling verdicts.

### 2.3 Output (what OpenL must return, mapped to existing shapes)

The transport payload is OpenL-shaped JSON, but the resolver **maps it back onto the
existing verdict shape** so nothing downstream changes:

- Per-rule results → `RuleFinding[]` (§1.2): each carries `rule_id`, `rule_version`,
  `status ∈ {PASS,FAIL,UNCERTAIN,EXEMPT}`, `reason`, `required_evidence`,
  `missing_evidence`, `confidence`, `review_required`, `verification_status`.
- Aggregate → `ProductInspection.overall_status` + `InspectionSummary`
  (counts of passed/failed/uncertain/exempt/review_required).
- **The four §1.3 invariants apply unchanged to OpenL output.** In particular:
  OpenL must be able to emit `UNCERTAIN`/`EXEMPT`, not only PASS/FAIL — an OpenL
  table that can only say PASS/FAIL is non-conformant, because it cannot express
  "insufficient evidence" or a statutory exemption and would therefore convert
  uncertainty into a false FAIL.

### 2.4 Transport

- **Protocol:** HTTP(S) to the OpenL RuleServices container (`openltablets/ws`).
- **Direction:** Python FastAPI backend is the client; OpenL is the server. (Re-stating
  the load-bearing fact: OpenL is a JVM service, not a `pip` package.)
- **Endpoint/JSON shape:** documented to the byte **once RULE-01 deploys the first
  decision table**. Until then this section is intentionally shape-level only.
- **Byte-level exemption slice (RULE-01, 2026-09-15, verified against
  `openltablets/ws:6.4.0`):**
  - Request `POST /{service}/classifyExemption` (`application/json`):
    `{"saleType","productCategory","massG","volumeMl","quantityEstablished",
      "isPrepackagedFalse","directIndInst","isExportOnly"}`
    `massG`/`volumeMl` use `-1.0` as "not applicable" (no JSON nulls into OpenL).
  - Response: JSON string `exemption_type` ∈ {`not_prepackaged`,
    `industrial_or_institutional_direct_sale`, `export_only_transaction`,
    `rule_3_quantity_exclusion`, `rule_26_small_pack`, `quantity_not_established`,
    `different_declaration_regime`, `unknown_sale_type`, `none`}.
  - Python maps that string onto `ExemptionResult` / `RuleFinding`. Full resolver
    aggregation across remaining LMPC rules is **not** cut over (`LMPC_ENABLE_OPENL`
    defaults false).
- **Config:** the OpenL base URL is an env var read by `config.py`; DEVOPS-01 adds the
  `openltablets/ws` service to `docker-compose.yml` **only after RULE-01 confirms the
  exact image tag and rule-deployment path** (see DEVOPS-01 package item 4).
  Confirmed: image `openltablets/ws:6.4.0`, compose profile `openl`, repo-zip mount of
  `backend/openl/dist/lmpc-exemption.zip`.

### 2.5 Cutover safety (binds RULE-01 + TEST-01)

- `rule_engine.py` stays as the reference implementation. No production cutover until
  **rule-by-rule parity** is proven via TEST-01's differential harness
  (same input → `{old_engine_result, openl_result}` → diff). This is required by CDD
  Instructions before cutover; it is not optional.
- Parity is measured on the `RuleFinding`/`overall_status` shapes above, so "parity"
  has a precise, testable meaning rather than a vibe.

---

## Ownership quick-reference

| Contract | Shape/doc owner | Implementation owner | Consumers who must not fork it |
|---|---|---|---|
| `ExtractedFact` / `ProductInspection` (`schema.py`) | ARCH-01 | — (exists) | OCR, CV, RULE-*, DB-01, EVID-01, report gen, FE-*, CON-*, AUTH-* |
| `RegulatoryContext` (`backend/models.py`) | ARCH-01 | — (exists) | RULE-*, RAG-*, FSSAI-01 |
| RuleSet Resolver → OpenL | ARCH-01 | RULE-01 | DEVOPS-01 (compose), TEST-01 (diff harness), report/DB/FE (unchanged by design) |
| Consumer scan response (`consumer_scan.ConsumerScanResponse`) | ARCH-01 (shape) | CON-01 | CON-02, AUTH-01, FE-02 |
| Evidence chain (`GET /inspections/{id}/evidence`) | EVID-01 | EVID-01 | FE-01, later FE-02 simplified |
| FSSAI module status (`GET /inspections/{id}/fssai`) | ARCH-01 SCR | FSSAI-01 | FE-02 / reports — **not** merged into `overall_status` |

---

## Proposed / draft contracts (Wave 2) — not frozen §1 fields

These are **additive** and do **not** change `ExtractedFact` / `ProductInspection`
(`extra="forbid"` stays). Implementers of CON-02 / FE-02 / AUTH-01 should build
against these drafts.

### CON-01 — `POST /consumer/scan` → `ConsumerScanResponse`

Flag: `LMPC_ENABLE_CONSUMER_SCAN` (default false). No new RBAC role (SCR: keep
inspector/reviewer/admin). Rate-limited by client address (`LMPC_CONSUMER_SCAN_RPM`).

```
scan_id: str
overall_status: PASS | FAIL | UNCERTAIN | EXEMPT   # UNCERTAIN is first-class
headline / plain_language: str
disclaimer: str   # same legal disclaimer as ProductInspection
review_required: bool
items[]: {label, observed, outcome, plain_language}
source: "consumer"
evidentially_weaker_than_inspector: true
```

Must not include bboxes, per-engine confidence, or rule IDs. Persisted in
`consumer_scans`, not `inspections`.

**ARCH-01 SCR (public access):** unauthenticated compute is allowed only behind
the feature flag + IP rate limit. No `consumer` role. CAPTCHA not implemented.

### FSSAI-01 — per-module status (SCR, not added to ProductInspection)

`ProductInspection.overall_status` remains the **LMPC** verdict. FSSAI results
live in `fssai_inspection_results` and `GET /inspections/{id}/fssai`:

```
module: "fssai"
module_status: PASS | FAIL | UNCERTAIN | EXEMPT | NOT_APPLICABLE | NOT_RUN
findings: RuleFinding[]   # same four-status invariant
```

Proposed later additive field (blocked until ARCH-01 signs):
`module_statuses: Optional[Dict[str, FactStatus]]` on ProductInspection.
Not implemented in this pass because `extra="forbid"`.

### RAG-02 — embeddings table

`knowledge_chunk_embeddings(chunk_id, embedding_json, backend)`. JSONB so
postgres:16-alpine works without pgvector. `CREATE EXTENSION vector` is attempted
and ignored when missing. BM25 path in `HybridRetriever.retrieve()` is unchanged.

