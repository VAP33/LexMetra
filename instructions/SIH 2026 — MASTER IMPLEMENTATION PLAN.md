# SIH 2026 — MASTER IMPLEMENTATION
# Problem Statement 26034
# AI-Powered Legal Metrology Packaged Commodity Compliance Platform

You are the PRINCIPAL ENGINEERING AGENT responsible for turning the existing SIH 2026 repository into one coherent, production-grade software system.

Do not treat this as a greenfield rewrite.
Do not blindly merge folders.
Do not create another Claude/agent folder.
Do not throw away working specialist implementations.

The repository must end with ONE canonical implementation.

============================================================
1. PROJECT OBJECTIVE
============================================================

Build an AI-powered evidence-backed inspection platform for checking compliance of packaged commodities under:

- Legal Metrology Act, 2009
- Legal Metrology (Packaged Commodities) Rules, 2011
- Applicable amendments and effective dates
- Sector-specific regulatory modules where applicable

The system should allow an inspector/user to:

1. Start an inspection session.
2. Capture multiple images/surfaces of a physical package.
3. Guide the user toward usable evidence.
4. Detect package/surface/label geometry.
5. Extract text and structured declarations.
6. Associate extracted facts with image regions.
7. Track confidence, provenance, OCR engine, conflicts and alternatives.
8. Reconstruct evidence across multiple images when justified.
9. Determine applicability/exemptions before evaluating rules.
10. Run deterministic, versioned legal rules.
11. Produce PASS / FAIL / UNCERTAIN / EXEMPT outcomes.
12. Send uncertain/conflicting cases to Human-in-the-Loop review.
13. Persist the complete inspection and evidence trail.
14. Generate an evidence-backed PDF inspection report.
15. Maintain audit history.
16. Support authorized users through JWT/RBAC.
17. Provide an architecture that can later support mobile/offline/cloud deployment.

The system must NEVER make a legal failure decision merely because information was not visible.

NOT OBSERVED != MISSING.

Insufficient evidence must result in:
- recapture guidance,
- UNCERTAIN,
- or human review,

depending on the situation.

============================================================
2. CORE ARCHITECTURE PRINCIPLE
============================================================

The fundamental architecture is:

CAMERA / IMAGE
      ↓
IMAGE QUALITY GATE
      ↓
PACKAGE / SURFACE / LABEL DETECTION
      ↓
GEOMETRY + CALIBRATION
      ↓
OCR / VISION EXTRACTION
      ↓
EVIDENCE FUSION
      ↓
MULTI-SURFACE / MULTI-IMAGE RECONSTRUCTION
      ↓
FIELD FACTS + PROVENANCE
      ↓
APPLICABILITY / EXEMPTION
      ↓
DETERMINISTIC VERSIONED LEGAL RULE ENGINE
      ↓
FINDINGS
      ↓
PASS / FAIL / UNCERTAIN / EXEMPT
      ↓
HUMAN REVIEW WHERE REQUIRED
      ↓
AUDITABLE REPORT

AI assists with evidence extraction and interpretation.

AI does NOT replace the deterministic legal rules.

RAG must NOT be the final legal decision-maker.

VLM must NOT directly declare a product legally compliant/non-compliant.

============================================================
3. CANONICAL REPOSITORY
============================================================

There may be multiple existing specialist implementations/folders originating from:

- Claude 1
- Claude 2
- Claude 4
- Claude 5 / recovery work
- earlier experiments

Treat these as engineering source material.

The canonical application must remain ONE repository and ONE source tree.

Do NOT create:

- Claude 6/
- merged_claude/
- final_final/
- new_duplicate_backend/
- parallel_frontend/
- alternate_rule_engine/

Instead:

1. Inventory every existing implementation.
2. Identify the strongest implementation for each responsibility.
3. Compare interfaces/contracts.
4. Integrate useful specialist functionality into canonical modules.
5. Preserve attribution/documentation where useful.
6. Archive obsolete implementations only after their useful functionality has been integrated and tested.

Every responsibility must eventually have one canonical implementation.

============================================================
4. SPECIALIST RESPONSIBILITY MAP
============================================================

Use the existing specialist work according to these boundaries.

------------------------------------------------------------
CLAUDE 1 — FRONTEND / UX
------------------------------------------------------------

Primary responsibility:

- Inspector dashboard
- Inspection workflow
- Capture UI
- Evidence viewer
- Findings UI
- Review workflow
- Reports/history
- Responsive web interface
- Future mobile-compatible architecture

Preferred planned stack:

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui

The final frontend must communicate with the real FastAPI backend.

Do NOT leave a static mock dashboard pretending to be connected.

Required workflow:

LOGIN
→ DASHBOARD
→ NEW INSPECTION
→ PRODUCT IDENTIFICATION
→ CAPTURE GUIDANCE
→ CAPTURE MULTIPLE SURFACES
→ ANALYZE
→ EVIDENCE
→ FINDINGS
→ REVIEW
→ FINALIZE
→ REPORT
→ HISTORY

------------------------------------------------------------
CLAUDE 2 — VISION / OCR / EVIDENCE
------------------------------------------------------------

Primary responsibility:

- OCR
- Orientation-aware OCR
- Region-aware extraction
- Multi-engine OCR
- PaddleOCR integration
- Tesseract fallback
- Evidence fusion
- Cross-image evidence fusion
- Barcode/QR advisory identification
- Image quality
- Recapture guidance
- Provenance
- Confidence
- Conflict detection

Planned technologies:

- PaddleOCR
- Tesseract
- OpenCV
- optional VLM
- barcode/QR libraries

Use the strongest existing Claude 2 implementations where they are technically sound.

Important:

Every extracted fact should retain, where available:

- field name
- normalized value
- raw text
- confidence
- source engine
- image ID
- bounding box
- region
- OCR alternatives
- agreement
- conflict state
- provenance
- verification status

Never reduce rich evidence into:

field → value

and discard the evidence metadata.

------------------------------------------------------------
CLAUDE 4 — GEOMETRY / CALIBRATION / MEASUREMENT
------------------------------------------------------------

Primary responsibility:

- Package geometry
- Surface geometry
- PDP detection
- Perspective correction
- Shape handling
- Spatial relationships
- Calibration
- Physical measurement
- Font-size measurement support
- Geometry-aware evidence
- Measurement confidence
- Rule 7 measurement support
- Rule 8 spatial/PDP support

Planned technologies:

- OpenCV
- computer vision geometry
- camera calibration
- AR/depth capability where available
- perspective transformation
- spatial measurement

CRITICAL:

Geometry provides measurement/evidence.

Geometry does NOT decide the legal rule.

For example:

Geometry:
"Estimated character height = X mm, confidence Y, calibration source Z."

Rule engine:
"Given applicable Rule 7 threshold for this package class and effective ruleset version, evaluate X."

A normal arbitrary photograph must NOT be represented as legally verified physical measurement.

Measurement status should distinguish:

- VERIFIED
- ESTIMATED
- UNCERTAIN
- NOT_OBSERVED

Calibration evidence must be persisted.

------------------------------------------------------------
CLAUDE 5 / PRINCIPAL INTEGRATION
------------------------------------------------------------

Use the recovery/integration work as the architectural baseline.

Responsibilities:

- canonical integration
- contract consistency
- API
- persistence
- legal engine integration
- evidence integrity
- authentication
- workflow
- testing
- deployment
- final integration

Do not duplicate specialist subsystems unnecessarily.

============================================================
5. FRONTEND TECHNOLOGY
============================================================

Target architecture:

Next.js
TypeScript
Tailwind CSS
shadcn/ui

Frontend must use typed API contracts.

Authentication:

JWT
RBAC

Roles should support at minimum:

- INSPECTOR
- REVIEWER
- ADMIN

Do not rely solely on frontend authorization.

Backend must enforce authorization.

The UI should expose:

- inspection status
- capture readiness
- evidence quality
- detected declarations
- confidence
- conflicts
- applicability
- rule findings
- review-required status
- final decision
- audit history

============================================================
6. BACKEND
============================================================

Use:

FastAPI
Python

Organize backend into coherent modules such as:

backend/
    api/
    auth/
    config/
    db/
    vision/
    geometry/
    evidence/
    product/
    legal/
    reports/
    inspections/
    review/
    tests/

Do not reorganize solely for aesthetics.

Preserve working modules when their interfaces are sound.

All major operations should have clear typed schemas.

============================================================
7. DATABASE
============================================================

Use PostgreSQL.

Persist at minimum:

USER
ROLE
INSPECTION_SESSION
INSPECTION
SURFACE_OBSERVATION
CAPTURE
IMAGE
IMAGE_QUALITY
PACKAGE_IDENTITY
OCR_READING
EXTRACTED_FIELD
EVIDENCE
EVIDENCE_PROVENANCE
GEOMETRY_MEASUREMENT
CALIBRATION
APPLICABILITY_RESULT
EXEMPTION_RESULT
RULE_EVALUATION
FINDING
REVIEW
AUDIT_LOG
REPORT
PRODUCT_REFERENCE

Evidence must survive the complete pipeline.

Do not persist only the final PASS/FAIL result.

The database should allow an auditor to answer:

"What evidence caused this rule to pass or fail?"

============================================================
8. REDIS
============================================================

Redis may be used for:

- background processing
- job state
- caching
- temporary workflow state
- asynchronous OCR/VLM processing

Do not make Redis a hard dependency for simple synchronous inspection operations unless justified.

The system should degrade gracefully where practical.

============================================================
9. VISION PIPELINE
============================================================

Implement:

CAPTURED IMAGE
→ QUALITY
→ PACKAGE DETECTION
→ SURFACE/PDP DETECTION
→ GEOMETRIC NORMALIZATION
→ TEXT REGION DETECTION
→ PREPROCESSING ENSEMBLE
→ OCR ENSEMBLE
→ EVIDENCE FUSION
→ FIELD EXTRACTION
→ BARCODE/QR
→ CROSS-IMAGE RECONSTRUCTION
→ CONFIDENCE/PROVENANCE
→ LEGAL ENGINE

Use PaddleOCR as the preferred modern OCR engine where deployable.

Use Tesseract as a robust fallback.

Optional VLM:

- difficult text
- ambiguous visual regions
- spatial interpretation
- semantic assistance
- conflict investigation

VLM output must be advisory evidence.

It must not bypass deterministic rules.

============================================================
10. MULTI-SURFACE INSPECTION
============================================================

Do NOT assume a single image contains the entire package.

InspectionSession must support:

SurfaceObservation[]

Examples:

- FRONT
- BACK
- SIDE
- TOP
- BOTTOM
- LABEL_REGION
- OTHER

The capture system should guide the user to obtain sufficient evidence.

Multiple images may contribute to the same physical surface.

Where practical, use overlap and spatial compatibility.

Suggested overlap target:

approximately 20–30% where useful,

but do not turn this into a rigid legal requirement.

Derived mosaics/reconstructed surfaces must retain links to source images.

============================================================
11. EVIDENCE FUSION
============================================================

Cross-image reconstruction is permitted only when evidence is sufficiently compatible.

Example:

Image A:
"MRP ₹"

Image B:
"149.00"

The system may reconstruct the field only when:

- same inspection
- same physical surface or justified relationship
- spatially compatible
- syntax compatible
- confidence sufficient
- no contradictory evidence

If ambiguity remains:

UNCERTAIN
+ REVIEW_REQUIRED

Never invent missing characters.

Never infer digits that are not visible.

============================================================
12. LIVE CAPTURE VS CAPTURED ANALYSIS
============================================================

Implement two conceptual modes.

LIVE:

Lightweight:

- blur detection
- glare
- framing
- package presence
- orientation
- readiness
- focus guidance

States:

NOT_READY
ALMOST_READY
READY

READY means:

"image is suitable for evidence capture"

It does NOT mean:

"product is legally compliant."

CAPTURED:

Run the complete expensive pipeline.

Do not run full legal analysis continuously on every camera frame.

============================================================
13. PRODUCT IDENTITY
============================================================

Support optional:

- barcode
- QR
- SKU/product identity
- trusted reference images

Product identity is advisory unless backed by trusted authoritative data.

Reference images can support:

- packaging similarity
- tamper indications
- packaging-version comparison

Reference images are NOT required for ordinary Legal Metrology compliance.

Do not confuse:

"not similar to reference"

with:

"legal non-compliance."

Tamper detection should produce evidence and review signals.

============================================================
14. FSSAI / CDSCO / SECTOR MODULES
============================================================

Architecture must support sector-specific compliance modules.

Core:

LEGAL_METROLOGY

Additional modules:

FSSAI
CDSCO_DRUGS
COSMETICS
MEDICAL_DEVICES

Do not blend all regulations into one giant rule engine.

Each module should expose:

- applicability
- extracted facts
- rules
- findings
- evidence
- authority/source
- version
- effective date

For food, distinguish:

Legal Metrology declarations
from
FSSAI food-safety/labeling requirements.

Never claim actual chemical/ingredient composition from package images.

An image can establish a declared value.

Actual composition requires laboratory/regulatory evidence.

============================================================
15. LEGAL RULE ENGINE
============================================================

The legal engine is the most important non-vision subsystem.

Use a deterministic, versioned architecture.

Every rule evaluation should include:

- rule_id
- rule_name
- legal_source
- ruleset_version
- effective_from
- effective_to if applicable
- applicability
- input facts
- evidence
- result
- confidence
- review_required
- explanation

Possible outcomes:

PASS
FAIL
UNCERTAIN
EXEMPT
NOT_APPLICABLE

Never allow an LLM to directly create a legal verdict.

============================================================
16. LEGAL METROLOGY COVERAGE
============================================================

Core rules to support and/or systematically extend include:

- Rule 3 — Scope
- Rule 4 — Multi-pack
- Rule 5 — Standard quantities
- Rule 6 — Mandatory declarations
- Rule 6(11) — Unit Sale Price
- Rule 7 — Size of letters/numerals
- Rule 8 — Principal Display Panel
- Rule 24 — Wholesale packages
- Rule 25 — Export/repackaging
- Rule 26 — Exemptions
- Rule 27 — Registration
- Rule 31 — Advertisement
- Rule 32 — Penalties/reference handling
- Rule 33 — Relaxation/reference handling

Do not invent legal thresholds.

Do not rely on stale hardcoded law where the current official source has changed.

Rules requiring official verification must be clearly marked and verified against authoritative DoCA material before being treated as production-ready.

The ruleset must support amendments and effective dates.

============================================================
17. APPLICABILITY FIRST
============================================================

The correct sequence is:

SCOPE
→ APPLICABILITY
→ EXEMPTION
→ REQUIRED DECLARATIONS
→ EVIDENCE
→ RULE EVALUATION
→ FINDING

Do not evaluate a declaration requirement before determining whether it applies.

Examples of contextual facts:

- imported
- export
- wholesale
- retail
- multi-pack
- pre-packaged
- commodity category
- package type
- exemption
- sector

Missing applicability evidence should not silently become:

is_imported = false

Instead:

UNKNOWN / UNCERTAIN

unless explicitly established.

============================================================
18. NOT OBSERVED SAFETY INVARIANT
============================================================

This is mandatory.

The following must never occur:

NOT_OBSERVED
→ MISSING
→ FAIL

unless there is explicit positive evidence that the declaration is required and its absence has actually been established from sufficient coverage.

For every mandatory declaration:

UNKNOWN
and
NOT_OBSERVED

must remain distinct from:

OBSERVED_ABSENT

A photo not showing the MRP is not proof that the package has no MRP.

============================================================
19. CONFLICT SAFETY
============================================================

If evidence conflicts:

Example:

OCR A:
MRP = ₹50

OCR B:
MRP = ₹90

Do not select one silently.

Set:

CONFLICTING
review_required = true

and cap legal confidence appropriately.

The same principle applies to:

- OCR
- VLM
- multiple images
- geometry measurements
- product identity
- applicability

============================================================
20. CONFIDENCE
============================================================

Confidence must represent evidence quality, not cosmetic certainty.

Do not output:

confidence = 1.0

merely because a rule function executed successfully.

Confidence should account for:

- image quality
- OCR quality
- engine agreement
- evidence provenance
- visibility
- calibration
- geometry
- cross-image consistency
- ambiguity
- conflict

Legal result and evidence confidence must remain conceptually separate.

============================================================
21. PRINCIPAL DISPLAY PANEL
============================================================

Geometry subsystem should estimate/detect PDP.

Legal engine should evaluate Rule 8 based on:

- PDP geometry
- declaration placement
- required spacing
- relevant declaration visibility

Do not treat:

PACKAGE BOUNDARY == PDP

as a valid assumption.

Do not declare compliance solely because one declaration box happens to lie inside a detected rectangle.

============================================================
22. MEASUREMENT SAFETY
============================================================

Physical measurements must carry measurement status.

Examples:

font height
PDP dimensions
package dimensions
spacing

Possible:

VERIFIED
ESTIMATED
UNCERTAIN
NOT_OBSERVED

Calibration record must be linked to verified measurements.

A normal photograph without scale/calibration must not magically become a legally verified millimetre measurement.

============================================================
23. RAG
============================================================

Implement RAG as an explanatory/retrieval subsystem.

RAG can retrieve:

- applicable legal provision
- rule explanation
- amendment
- source document
- effective date
- inspector guidance

RAG must NOT decide:

PASS
FAIL
UNCERTAIN
EXEMPT

The deterministic rule engine remains authoritative.

Every retrieved legal source must retain:

- document
- provision
- version/date
- source authority

============================================================
24. VLM
============================================================

VLM may assist with:

- difficult packaging interpretation
- label region interpretation
- ambiguous text
- spatial understanding
- visual anomalies
- evidence description

VLM output must be stored as advisory evidence.

Never:

VLM says illegal
→ FAIL

Instead:

VLM observation
→ evidence fusion
→ deterministic facts
→ legal rule

============================================================
25. TAMPER DETECTION
============================================================

Use pHash and visual comparison for packaging integrity.

Potential outputs:

- similar
- changed
- significantly changed
- unable to compare

Tamper detection must not automatically equal legal non-compliance.

Use it as:

- evidence
- anomaly
- review trigger

Compare against trusted references where available.

============================================================
26. HUMAN-IN-THE-LOOP
============================================================

Any case with material uncertainty should support review.

Review UI should show:

- original image
- cropped evidence
- OCR text
- bounding boxes
- alternative readings
- confidence
- conflict state
- geometry measurement
- calibration
- legal rule
- rule inputs
- retrieved legal source
- system explanation

Reviewer should be able to:

- confirm
- reject
- correct
- request recapture
- mark unresolved

All review actions must be audited.

============================================================
27. REPORTING
============================================================

Generate evidence-backed PDF reports.

Report must contain:

- inspection ID
- date/time
- inspector
- product identity
- captured images
- relevant evidence crops
- extracted declarations
- confidence
- applicability
- exemptions
- rule evaluations
- findings
- final result
- reviewer information
- legal ruleset version
- evidence provenance

Do not generate a report that claims a measurement or fact was verified when it was only estimated.

============================================================
28. SECURITY
============================================================

Implement:

- JWT authentication
- RBAC
- password hashing
- protected API routes
- audit logging
- configurable CORS
- environment-based secrets
- safe file handling
- input validation
- upload size/type validation
- secure database configuration
- no hardcoded credentials
- no API secrets in source code

Provide:

.env.example

Never commit secrets.

============================================================
29. DOCKER / DEPLOYMENT
============================================================

Provide production-oriented:

- Dockerfile
- docker-compose.yml
- PostgreSQL
- Redis
- backend
- frontend
- worker if asynchronous processing is implemented

Document:

- local development
- database migration
- environment variables
- startup
- health checks
- test execution

============================================================
30. TESTING STRATEGY
============================================================

Tests must test REAL behavior.

Do not create tests that pass only because dependencies are mocked into existence.

Required categories:

1. Schema tests
2. OCR tests
3. Orientation tests
4. Evidence fusion tests
5. NOT_OBSERVED safety tests
6. Conflict tests
7. Applicability tests
8. Exemption tests
9. Geometry tests
10. Calibration tests
11. Measurement tests
12. Legal rule tests
13. API tests
14. Authentication tests
15. RBAC tests
16. Persistence tests
17. Report tests
18. Multi-surface tests
19. Real-photo benchmark tests
20. End-to-end inspection tests

At least some tests must use:

- real images
- real OCR
- real Pydantic
- real PostgreSQL
- real HTTP endpoints

No vacuous tests.

============================================================
31. REAL-PHOTO BENCHMARK
============================================================

Create/maintain a benchmark based on real Indian packaged products.

Measure field-level performance for:

- manufacturer
- packer
- importer
- country of origin
- common name
- net quantity
- MRP
- unit sale price
- dates
- consumer care
- dimensions where applicable
- other declarations

Track:

- correct
- incorrect
- not observed
- ambiguous
- conflicting

Do not report OCR character accuracy alone as the primary project metric.

The real metric is:

Can the system reliably obtain evidence sufficient for a correct legal evaluation?

============================================================
32. PERFORMANCE
============================================================

Separate:

LIVE CAPTURE latency

from

FULL ANALYSIS latency.

Use asynchronous/background processing where appropriate.

Do not sacrifice evidence integrity simply to make the demo fast.

Cache expensive operations where safe.

============================================================
33. API CONTRACT
============================================================

Maintain consistent contracts across:

Frontend
↕
FastAPI
↕
Vision
↕
Geometry
↕
Evidence
↕
Legal Engine
↕
Database

Avoid adapters that silently discard fields.

When a schema changes:

1. update Pydantic models
2. update backend
3. update frontend types
4. update persistence
5. update tests
6. update API documentation

Search for all consumers before changing shared schemas.

============================================================
34. OBSERVABILITY
============================================================

Add structured logging around:

- inspection
- capture
- OCR
- geometry
- evidence fusion
- legal evaluation
- review
- report generation

Errors must not be swallowed.

If image persistence fails, the system must not pretend evidence was stored.

If OCR fails, the system must not silently return an empty successful extraction.

If a legal evaluator cannot run, it must not silently PASS.

============================================================
35. FAILURE-SAFE PRINCIPLE
============================================================

The system must fail toward:

UNCERTAIN
REVIEW_REQUIRED
RECATURE_REQUIRED

rather than inventing evidence.

Never convert:

exception
timeout
missing model
missing image
missing applicability
OCR conflict
calibration failure

into:

PASS

============================================================
36. IMPLEMENTATION ORDER
============================================================

Execute in this order.

PHASE 1
Repository inventory and architecture map.

PHASE 2
Contract/evidence integrity.

PHASE 3
Integrate Claude 2 Vision/OCR/Evidence subsystem.

PHASE 4
Integrate Claude 4 Geometry/Calibration/Measurement subsystem.

PHASE 5
Integrate deterministic legal engine and expand missing evaluators.

PHASE 6
Integrate frontend.

PHASE 7
Integrate PostgreSQL persistence/auth/RBAC/audit.

PHASE 8
Integrate reports.

PHASE 9
Integrate Redis/background processing where justified.

PHASE 10
Integrate optional VLM.

PHASE 11
Integrate RAG as legal retrieval/explanation only.

PHASE 12
End-to-end real-photo benchmark.

PHASE 13
Docker/deployment/security hardening.

============================================================
37. GIT / GITLAB DISCIPLINE
============================================================

Before modifying anything:

1. Inspect git status.
2. Inspect branch.
3. Inspect recent commits.
4. Create a safe checkpoint if necessary.

Do not destroy existing work.

Make logical commits.

Suggested commit boundaries:

- architecture/contracts
- vision integration
- geometry integration
- legal engine
- frontend
- persistence/auth
- reports
- testing
- deployment

Do not commit:

- secrets
- database dumps
- generated junk
- model caches
- huge temporary files

============================================================
38. DOCUMENTATION
============================================================

Maintain:

README.md
ARCHITECTURE.md
API.md
LEGAL_ENGINE.md
VISION_PIPELINE.md
GEOMETRY.md
EVIDENCE_MODEL.md
SECURITY.md
DEPLOYMENT.md
TESTING.md
PROJECT_STATE.md
IMPLEMENTATION_STATUS.md

Documentation must distinguish:

IMPLEMENTED
TESTED
END-TO-END VERIFIED
DEMO READY
PRODUCTION READY
PLANNED
OPTIONAL

Never claim something is implemented merely because a folder exists.

============================================================
39. CRITICAL DO-NOT-BREAK RULES
============================================================

NEVER:

- replace deterministic legal logic with an LLM
- treat NOT_OBSERVED as MISSING
- silently resolve conflicting OCR
- invent missing digits
- claim uncalibrated measurements are verified
- treat package boundary as PDP
- treat VLM output as legal truth
- treat RAG output as legal truth
- treat tamper similarity as legal failure
- silently default unknown applicability to false
- discard evidence provenance
- discard bounding boxes
- discard OCR alternatives
- swallow storage errors
- hardcode credentials
- create duplicate canonical subsystems
- rewrite working systems without evidence
- claim production readiness without tests

============================================================
40. DEFINITION OF DONE
============================================================

The project is considered complete only when a user can perform:

LOGIN
↓
CREATE INSPECTION
↓
IDENTIFY PRODUCT
↓
CAPTURE FRONT
↓
CAPTURE BACK
↓
CAPTURE ADDITIONAL SURFACES
↓
LIVE QUALITY GUIDANCE
↓
FULL VISION ANALYSIS
↓
GEOMETRY / PDP ANALYSIS
↓
OCR / EVIDENCE FUSION
↓
APPLICABILITY / EXEMPTION
↓
LEGAL RULE EVALUATION
↓
FINDINGS
↓
HUMAN REVIEW WHEN NECESSARY
↓
FINAL RESULT
↓
PDF REPORT
↓
PERSISTED AUDIT HISTORY

and the entire chain is backed by testable evidence.

============================================================
41. FIRST ACTION
============================================================

DO NOT START BY WRITING NEW CODE.

First inspect the repository and produce a concise:

ARCHITECTURE_INVENTORY.md

containing:

- canonical source tree
- all specialist folders
- Claude 1 contributions
- Claude 2 contributions
- Claude 4 contributions
- Claude 5/recovery contributions
- duplicate implementations
- current dependencies
- current frontend
- current backend
- current database
- current legal engine
- current vision pipeline
- current geometry capability
- current test coverage
- known broken interfaces
- missing functionality
- recommended integration order

Then begin implementation immediately.

Do not spend the entire task writing a plan.

After the inventory, fix the highest-priority architectural defect and continue through the implementation phases.

============================================================
42. FINAL ENGINEERING PRINCIPLE
============================================================

This is not an OCR demo.

This is not a chatbot.

This is not a generic computer-vision application.

This is an:

AI-ASSISTED
EVIDENCE-BACKED
DETERMINISTIC
LEGAL-METROLOGY
INSPECTION PLATFORM.

AI extracts evidence.

Geometry measures evidence.

Evidence fusion establishes trustworthy facts.

Applicability determines what matters.

The deterministic rule engine determines compliance.

Humans resolve uncertainty.

Every important conclusion must be traceable back to evidence.

Build accordingly.
============================================================
43. LOGIC PRESERVATION / NO-UNAUTHORIZED-CHANGE CONTRACT
============================================================

THIS IS AN INTEGRATION AND HARDENING PROJECT.

It is NOT permission to redesign, simplify, rewrite, reinterpret,
or replace existing business logic.

Existing working logic is authoritative unless:

1. It contains a demonstrable defect,
2. It violates a stated safety invariant,
3. It is incompatible with another required subsystem,
4. It is required to integrate a specialist subsystem,
5. It is required to fix an actual runtime/integration error,
6. It is explicitly required by the master specification.

Otherwise:

PRESERVE IT.

------------------------------------------------------------
BEFORE CHANGING LOGIC
------------------------------------------------------------

For every non-trivial logic change:

1. Identify the existing behavior.
2. Identify the exact defect or integration requirement.
3. Identify all consumers of that behavior.
4. Determine whether the change affects:
   - legal semantics
   - evidence semantics
   - confidence
   - applicability
   - exemptions
   - persistence
   - API contracts
   - frontend behavior
5. Write/add a regression test for the existing expected behavior.
6. Make the smallest change necessary.
7. Run the relevant tests.
8. Run the full regression suite.

Do NOT make broad changes merely because another implementation
looks cleaner.

------------------------------------------------------------
LEGAL LOGIC PRESERVATION
------------------------------------------------------------

DO NOT rewrite legal rules merely to integrate the system.

Existing legal logic must remain unchanged unless:

- a verified implementation bug is found,
- an integration contract requires an explicit adaptation,
- an authoritative legal source requires a legal update.

If legal logic must change:

- preserve the previous version,
- document the reason,
- record the source,
- record effective date/version,
- add regression tests,
- ensure old inspections remain reproducible.

Never silently alter a legal threshold, applicability condition,
exemption, or verdict mapping.

------------------------------------------------------------
VISION LOGIC PRESERVATION
------------------------------------------------------------

Do not replace an existing OCR/vision algorithm simply because
another specialist implementation uses a different approach.

Compare them first.

If both are useful:

- retain the strongest canonical behavior,
- integrate complementary capabilities,
- preserve existing outputs,
- preserve provenance,
- add regression tests.

Do not silently change field extraction semantics.

------------------------------------------------------------
GEOMETRY LOGIC PRESERVATION
------------------------------------------------------------

Claude 4's geometry subsystem must be integrated as a provider
of geometric evidence.

Do not move legal decision logic into geometry.

Do not change the meaning of:

- PDP
- calibration
- measurement
- VERIFIED
- ESTIMATED
- UNCERTAIN
- NOT_OBSERVED

unless explicitly required by a verified defect.

------------------------------------------------------------
SCHEMA PRESERVATION
------------------------------------------------------------

Do not casually rename or remove existing fields.

If a schema migration is required:

- preserve backwards compatibility where practical,
- migrate existing data safely,
- update all consumers,
- add migration tests,
- document the change.

Never silently discard:

- image IDs
- bounding boxes
- OCR alternatives
- provenance
- confidence
- conflict state
- applicability
- rule IDs
- ruleset versions
- review status
- audit information.

------------------------------------------------------------
API PRESERVATION
------------------------------------------------------------

Existing working API behavior must remain compatible unless
there is an explicit reason to change it.

Before changing an endpoint:

- inspect all frontend consumers,
- inspect tests,
- inspect internal callers,
- inspect persistence behavior.

Prefer additive changes over breaking changes.

------------------------------------------------------------
NO SILENT FALLBACKS
------------------------------------------------------------

Never hide an integration problem by silently substituting:

- empty extraction
- PASS
- confidence = 1.0
- applicability = false
- imported = false
- no evidence
- default rule result

When a dependency fails, return an explicit safe state.

------------------------------------------------------------
INTEGRATION DECISION RECORD
------------------------------------------------------------

For every specialist subsystem being integrated, create a short
decision record:

SUBSYSTEM
SOURCE
SELECTED IMPLEMENTATION
REUSED LOGIC
NEW LOGIC
CONFLICTS
RESOLUTION
REGRESSION TESTS

This is especially required for:

- Claude 1 frontend
- Claude 2 vision/OCR/evidence
- Claude 4 geometry/calibration/measurement
- Claude 5 recovery/integration

------------------------------------------------------------
NO DUPLICATE LOGIC
------------------------------------------------------------

After integration, search for duplicate implementations of:

- OCR
- field extraction
- evidence fusion
- geometry
- PDP detection
- calibration
- legal evaluation
- applicability
- exemption
- authentication
- inspection finalization

There must be ONE canonical implementation for each.

Adapters are allowed only when they preserve semantics.

------------------------------------------------------------
FINAL REGRESSION REQUIREMENT
------------------------------------------------------------

Before declaring integration complete:

1. Run all existing tests.
2. Run all newly added tests.
3. Run real database tests.
4. Run real API tests.
5. Run frontend integration tests.
6. Run representative real-image tests.
7. Run end-to-end inspection tests.
8. Compare critical outputs against pre-integration behavior.

The agent must report:

- tests before integration
- tests after integration
- failures before
- failures after
- behavior intentionally changed
- behavior preserved
- known remaining limitations

DO NOT claim "no logic changed" if logic was changed.

============================================================
44. FINAL CONSISTENCY AUDIT
============================================================

Before completion, perform a repository-wide consistency audit.

Check every layer:

FRONTEND
↓
API
↓
SCHEMAS
↓
VISION
↓
GEOMETRY
↓
EVIDENCE
↓
APPLICABILITY
↓
LEGAL ENGINE
↓
PERSISTENCE
↓
REVIEW
↓
REPORTING

For every boundary verify:

- field names
- types
- enums
- IDs
- confidence semantics
- evidence semantics
- error semantics
- review flags
- timestamps
- version fields

Search for stale/duplicate names and adapters.

Particularly search for cases where:

one subsystem produces a field
but another subsystem ignores or renames it.

Do not consider integration complete until these
cross-boundary contracts are consistent.

============================================================
45. FINAL COMPLETION GATE
============================================================

Do not declare the project complete because:

- code compiles,
- tests pass,
- frontend loads,
- backend starts,
- or a demo works.

Completion requires:

A. Architecture integrated
B. Specialist contributions integrated
C. Existing logic preserved
D. Legal semantics preserved
E. Evidence provenance preserved
F. NOT_OBSERVED safety preserved
G. Conflict safety preserved
H. Geometry measurement semantics preserved
I. Applicability/exemption semantics preserved
J. Database persistence verified
K. API contracts verified
L. Frontend connected to real APIs
M. Human review functional
N. PDF evidence report functional
O. Real-image end-to-end flow verified
P. Regression suite passing
Q. No duplicate canonical subsystems
R. Documentation updated
S. Known limitations explicitly documented

Only then declare:

INTEGRATED
TESTED
END-TO-END VERIFIED

Do not claim PRODUCTION READY unless the actual
production-readiness criteria have also been verified.