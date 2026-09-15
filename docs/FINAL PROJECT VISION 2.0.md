### AI-Assisted, Evidence-Backed, Multilingual Regulatory Compliance & Inspection Platform

---

# 1. PROJECT VISION

## LexMetra

LexMetra is an **AI-assisted, evidence-backed, multilingual regulatory compliance and inspection platform** designed initially for packaged commodities under Legal Metrology, with extensibility to food-safety verification and consumer protection workflows.

The system combines:

- Computer Vision
- YOLO-based package/label understanding
- Multilingual OCR
- Evidence extraction and provenance
- Open-source rule execution through **OpenL Tablets**
- Immutable multiversioned legal rules
- Controlled amendment management
- Packaging tampering detection
- FSSAI cross-verification
- Consumer product verification
- Consumer-to-authority reporting
- Inspector workflow management
- Legal RAG
- Multilingual voice assistance
- Analytics and regulatory intelligence
    

### The project should NOT be presented as:

> "An AI that decides whether a product violates the law."

### It should be presented as:

> **"An evidence-backed regulatory inspection platform that uses computer vision and multilingual OCR to collect and validate evidence, an open-source rule engine to execute verified legal rules, and controlled versioning, human validation and auditability to support reliable regulatory decisions."**

The core philosophy is:

> **AI extracts. Evidence validates. OpenL evaluates. Humans govern. Audit proves.**

---

# 2. THE COMPLETE LEXMETRA ECOSYSTEM

LexMetra should not be only an inspector application.

It should connect three major ecosystems:

```text
                         LEXMETRA
                            │
       ┌────────────────────┼────────────────────┐
       │                    │                    │
       ▼                    ▼                    ▼
    CONSUMER             INSPECTOR           AUTHORITY
    ECOSYSTEM             ECOSYSTEM          ECOSYSTEM
       │                    │                    │
       │                    │                    │
       └────────────────────┼────────────────────┘
                            ▼
                    SHARED EVIDENCE LAYER
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        Legal Metrology   FSSAI       Packaging
          Compliance    Verification   Integrity
              │             │             │
              └─────────────┼─────────────┘
                            ▼
                    UNIFIED CASE / RECORD
                            │
                            ▼
                        ANALYTICS
```

This creates a complete chain:

```text
Consumer
   ↓
Product
   ↓
Evidence
   ↓
Compliance
   ↓
Report / Inspection
   ↓
Authority Action
   ↓
Analytics / Intelligence
```

---

# 3. CORE DIFFERENTIATORS / USPs

The final LexMetra USP set should be:

### USP 1 — Evidence-backed legal decisions

Every result can be traced to:

```text
Original image
↓
Detected region
↓
OCR text
↓
Confidence
↓
Evidence agreement
↓
Applicable rule
↓
Rule version
↓
Rule source
↓
Decision
↓
Audit trail
```

---

### USP 2 — Open-source, multiversioned legal rule engine

Use **OpenL Tablets** as the production rule-execution engine.

Legal rules are:

```text
Versioned
Immutable
Source-linked
Effective-date aware
Human-approved
Auditable
```

---

### USP 3 — AI cannot silently change the law

The architecture explicitly prevents:

```text
OCR
 ↓
automatic rule modification
```

Instead:

```text
Amendment
 ↓
OCR
 ↓
proposed change
 ↓
diff
 ↓
Inspector validation
 ↓
Legal/domain verification
 ↓
new RuleSet
 ↓
OpenL deployment
 ↓
scheduled activation
```

This is one of the project's strongest governance features.

---

### USP 4 — Packaging tampering detection

Detect suspicious:

```text
MRP stickers
Over-labeling
Re-labelling
Print inconsistencies
Possible package alteration
Seal anomalies
Suspicious date alteration
Visual inconsistencies
```

Tampering is **advisory evidence**, not automatic legal proof.

```text
Tamper suspicion
       ↓
Review Required
```

Never:

```text
Tamper suspicion
       ↓
automatic FAIL
```

The existing system already treats sticker detection as advisory rather than allowing it to independently produce a legal failure.

---

### USP 5 — FSSAI cross-verification

For applicable food products:

```text
Product
 ↓
Domain applicability
 ↓
Legal Metrology checks
+
FSSAI checks
 ↓
Unified result
```

Legal Metrology and FSSAI remain separate regulatory domains with independent rule sources and versioning.

They should never be merged into one ambiguous "law database."

---

### USP 6 — Consumer product verification

Consumers can scan a package and receive a simplified result:

```text
MRP
Quantity
Manufacturer
Date
Relevant regulatory checks
Packaging integrity
```

The consumer sees understandable results rather than internal legal-engine complexity.

---

### USP 7 — Consumer-to-authority reporting

Consumers can report suspicious products directly:

```text
Consumer
 ↓
Scan / Capture
 ↓
AI pre-screen
 ↓
Evidence
 ↓
Consumer confirmation
 ↓
Complaint / Case
 ↓
Authority queue
 ↓
Inspector
```

This creates a direct **citizen → government enforcement feedback loop**.

---

### USP 8 — Complaint-to-inspection intelligence

Multiple consumer complaints about the same product or issue can be clustered:

```text
17 complaints
8 locations
same product family
same suspected issue
        ↓
Pattern detected
        ↓
Authority alert
        ↓
Inspection priority
```

This changes LexMetra from a passive inspection system into a **regulatory intelligence platform**.

---

### USP 9 — Product intelligence / historical comparison

LexMetra can maintain product history:

```text
Package versions
MRP history
Label history
Inspection history
Tampering history
Complaint history
Regulatory findings
```

Therefore:

```text
Current package
      ↓
Historical package
      ↓
Visual difference
      ↓
Change classification
```

---

### USP 10 — Evidence-backed analytics

Analytics aren't just:

```text
100 inspections
20 failures
```

Instead they cover:

```text
Violation trends
Consumer complaints
Tampering patterns
OCR reliability
Human-review rates
Amendment trends
Product risk patterns
Regulatory trends
```

---

# 4. HIGH-LEVEL TECHNICAL ARCHITECTURE

```text
                         ┌───────────────────────┐
                         │     INSPECTOR UI      │
                         │ multilingual + voice │
                         └──────────┬────────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │ Guided Capture   │
                          └────────┬─────────┘
                                   │
                 ┌─────────────────┴─────────────────┐
                 ▼                                   ▼
          ┌──────────────┐                    ┌──────────────┐
          │ YOLO / CV    │                    │ OCR Ensemble │
          │ layout       │                    │ PaddleOCR    │
          │ detection    │                    │ Tesseract    │
          └──────┬───────┘                    └──────┬───────┘
                 └─────────────────┬─────────────────┘
                                   ▼
                       ┌────────────────────────┐
                       │ Evidence Normalizer    │
                       │ bbox / confidence /    │
                       │ provenance / conflicts │
                       └────────────┬───────────┘
                                    │
                                    ▼
                       ┌────────────────────────┐
                       │ Evidence Safety Layer  │
                       │ coverage / conflict /  │
                       │ applicability          │
                       └────────────┬───────────┘
                                    │
                                    ▼
                       ┌────────────────────────┐
                       │ RuleSet Resolver       │
                       └────────────┬───────────┘
                                    │
                                    ▼
                       ┌────────────────────────┐
                       │     OpenL Tablets      │
                       │ Open-source Rule Engine│
                       └────────────┬───────────┘
                                    │
                                    ▼
                       ┌────────────────────────┐
                       │ LexMetra Safety Gate   │
                       └────────────┬───────────┘
                                    │
                     ┌──────────────┼──────────────┐
                     ▼              ▼              ▼
                   PASS           FAIL         UNCERTAIN
                     │              │              │
                     └──────────────┴──────────────┘
                                    │
                                    ▼
                           Evidence + Audit
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
             Evidence Viewer                    Analytics
```

Separate legal knowledge system:

```text
Official Documents
      ↓
Document parsing / OCR
      ↓
Legal Knowledge Base
      ↓
BGE-M3
      +
pgvector
      +
Hybrid Retrieval
      ↓
Adaptive Legal RAG
      ↓
Cited Explanation
```

Amendment system:

```text
Gazette / Notification
        ↓
Document OCR
        ↓
Proposed Changes
        ↓
Rule Diff
        ↓
Inspector Validation
        ↓
Legal Verification
        ↓
New RuleSet
        ↓
OpenL
        ↓
Schedule
        ↓
Activate
```

---

# 5. COMPUTER VISION LAYER

## Purpose

Computer Vision answers:

> **Where is the relevant information?**

Pipeline:

```text
Image
 ↓
Package detection
 ↓
Region detection
 ↓
YOLO semantic detection
 ↓
Relevant regions
 ↓
OCR
```

Candidate classes:

```text
MRP
NET_QUANTITY
MFG_DATE
BEST_BEFORE
MANUFACTURER
COMMON_NAME
CONSUMER_CARE
COUNTRY_OF_ORIGIN
UNIT_PRICE
BARCODE
QR
STICKER
TAMPER
PDP
```

YOLO is a **layout/evidence detector**, not a legal decision-maker.

---

# 6. OCR ARCHITECTURE

Final production OCR target:

```text
                  Image Region
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
        PaddleOCR             Tesseract
            │                     │
            └──────────┬──────────┘
                       ▼
                  OCR Fusion
                       │
                       ▼
               Canonical OCR Object
```

## Primary

**PaddleOCR PP-OCRv5**

Primary multilingual candidate, particularly valuable for Indian-language text such as Hindi and Marathi.

## Secondary

**Tesseract**

Retained as an independent OCR source and fallback.

## Experimental

**Surya**

Benchmark separately before making it a production dependency.

---

# 7. OCR CONFIDENCE

Maintain separate concepts:

```text
OCR Confidence
CV Confidence
Evidence Confidence
Decision State
```

Example:

```text
PaddleOCR = 0.96
Tesseract = 0.92

Agreement = CORROBORATED
Evidence = SUFFICIENT
```

Where:

```text
PaddleOCR = ₹499
Tesseract = ₹4990

Agreement = CONFLICTING
Decision = UNCERTAIN / REVIEW
```

Never treat:

```text
OCR confidence = legal confidence
```

---

# 8. FINAL EVIDENCE CONTRACT

Every extracted fact should carry:

```text
field
value
raw_text
normalized_value
confidence
bbox
image_id
surface_id
OCR engine
agreement state
alternative values
measurement
provenance
```

Example:

```json
{
  "field": "mrp",
  "value": "499",
  "confidence": 0.96,
  "bbox": [421, 308, 214, 62],
  "image_id": "img_024",
  "engines": ["PADDLEOCR", "TESSERACT"],
  "agreement": "CORROBORATED"
}
```

This becomes the shared contract between:

```text
CV
OCR
Backend
OpenL
Frontend
Audit
RAG
```

---

# 9. MULTI-SURFACE INSPECTION

One product can require multiple images:

```text
Front
Back
Side
Bottom
Close-up
```

Evidence is accumulated:

```text
Capture 1 → MRP
Capture 2 → Manufacturer
Capture 3 → Quantity
Capture 4 → Consumer care

              ↓

       Cumulative Evidence
```

The legal evaluation happens against the accumulated evidence rather than treating every photograph as a complete package.

The current session architecture already follows this union-of-evidence approach.

---

# 10. OPEN-SOURCE RULE ENGINE

## Production executor

### OpenL Tablets

The existing LexMetra deterministic engine becomes the:

### Reference / Migration Engine

Therefore:

```text
Existing Engine
      ↓
Expected Result

same facts
      ↓
OpenL
      ↓
Actual Result
```

The two are compared through differential testing until equivalence is established.

OpenL supports decision tables, calculations, decision trees and version/effective-date-oriented rule selection. ([openl-tablets.org](https://openl-tablets.org/features?utm_source=chatgpt.com))

---

# 11. RULE ARCHITECTURE

Do not put all legal metadata inside OpenL.

Use:

```text
LEXMETRA RULE REGISTRY
        │
        ├── legal metadata
        ├── source
        ├── version
        ├── effective dates
        ├── verification status
        ├── approval status
        └── hash
                 │
                 ▼
            OPENL TABLES
                 │
                 ▼
        executable legal logic
```

And around OpenL:

```text
LEXMETRA SAFETY LAYER
        │
        ├── evidence sufficiency
        ├── conflict handling
        ├── applicability
        └── review routing
```

---

# 12. MULTIVERSION RULE ENGINE

Every RuleSet is immutable.

Example:

```text
LMPC-2026.1
LMPC-2026.2
LMPC-2026.3
```

Each stores:

```text
ruleset_id
version
effective_from
effective_to
status
source_document
source_hash
created_by
reviewed_by
approved_by
created_at
approved_at
```

An inspection also records:

```text
inspection_id
ruleset_id
ruleset_version
ruleset_hash
```

Therefore a historical decision remains reproducible.

---

# 13. RULESET LIFECYCLE

```text
DRAFT
 ↓
OCR_EXTRACTED
 ↓
PENDING_INSPECTOR_REVIEW
 ↓
INSPECTOR_APPROVED
 ↓
LEGAL_VERIFICATION
 ↓
APPROVED
 ↓
SCHEDULED
 ↓
ACTIVE
```

Alternative:

```text
PENDING_REVIEW → REJECTED
```

or:

```text
LEGAL_VERIFICATION → REJECTED
```

Never:

```text
ACTIVE → silently overwritten
```

---

# 14. AMENDMENT GOVERNANCE

The system must enforce:

> **No OCR result can directly become law.**

Final process:

```text
Inspector uploads official amendment
        ↓
Document OCR
        ↓
Extract proposed changes
        ↓
Compare with active RuleSet
        ↓
Generate visual diff
        ↓
Create DRAFT RuleSet
        ↓
Inspector validates
        ↓
Legal/domain validation
        ↓
Approval
        ↓
Create immutable new version
        ↓
Deploy OpenL version
        ↓
Schedule activation
        ↓
Effective date reached
        ↓
ACTIVE
```

No:

```text
[Auto Apply OCR Changes]
```

button.

---

# 15. RULESET HASHING

Each approved version should have:

```text
SHA-256(canonicalized ruleset)
```

Example:

```text
RuleSet: LMPC-2026.2
Hash: 5bc8...
```

That hash is recorded with every inspection.

This answers:

> **Exactly which legal configuration produced this result?**

---

# 16. DIFFERENTIAL RULE TESTING

Before OpenL becomes authoritative:

```text
100+ legal scenarios
        ↓
Reference Engine
        ↓
Expected Results

same scenarios
        ↓
OpenL
        ↓
Actual Results
```

Target:

```text
100% equivalence
0 unexplained differences
```

Any mismatch:

```text
BLOCK RELEASE
      ↓
REVIEW
```

This is also an excellent technical proof for the SIH evaluator that the open-source rule-engine migration was actually done correctly.

---

# 17. FINAL LEGAL DECISION PIPELINE

```text
Evidence
   ↓
Coverage sufficient?
   │
   ├── NO → UNCERTAIN / KEEP CAPTURING
   │
   ▼
Conflict?
   │
   ├── YES → UNCERTAIN / REVIEW
   │
   ▼
Applicable RuleSet?
   │
   ├── NO → REVIEW
   │
   ▼
OpenL
   ↓
Rule Result
   ↓
LexMetra Safety Gate
   ↓
Final Status
```

Possible statuses:

```text
PASS
FAIL
UNCERTAIN
EXEMPT
REVIEW_REQUIRED
```

---

# 18. PACKAGING TAMPERING DETECTION

Create a separate subsystem:

```text
backend/cv/tamper/
    sticker_detector.py
    seal_detector.py
    print_consistency.py
    anomaly_fusion.py
```

Pipeline:

```text
Image
 ↓
Package geometry
 ↓
Sticker detection
 ↓
Print consistency
 ↓
Texture / edge analysis
 ↓
Date / MRP comparison
 ↓
Historical package comparison
 ↓
Tamper suspicion
```

Output:

```text
NO SUSPICIOUS ALTERATION DETECTED
```

or:

```text
POSSIBLE ALTERATION

Reason:
Visual discontinuity around MRP region.

Confidence:
0.87

Action:
Inspector review recommended.
```

The system should never equate:

```text
suspicious ≠ legally proven
```

---

# 19. PRODUCT HISTORY / PACKAGE COMPARISON

Maintain historical package evidence:

```text
Product
 ├── Current package
 ├── Historical images
 ├── Historical MRP
 ├── Historical labels
 ├── Inspection records
 ├── Tamper findings
 └── Consumer complaints
```

Then:

```text
Current Image
      ↓
Historical Match
      ↓
Difference Analysis
      ↓
Change Classification
```

Potential result:

```text
MRP changed: ₹470 → ₹499

Packaging difference:
Detected

Sticker indication:
Low

Conclusion:
Change detected; no conclusive tampering established.
```

That level of wording is important.

---

# 20. FSSAI CROSS-VERIFICATION

For food products:

```text
Product Classification
       ↓
Is FSSAI verification applicable?
       ↓
      YES
       ↓
FSSAI checks
       ↓
FSSAI findings
```

Keep regulatory domains separated:

```text
regulations/
    legal_metrology/
    fssai/
```

Each should maintain its own:

```text
RuleSet
Source hierarchy
Version
Effective dates
Verification status
```

The final report can combine them:

```text
LEGAL METROLOGY
✓ MRP
✓ Net Quantity
✓ Manufacturer

FSSAI
✓ Applicable checks
⚠ One field requires review

PACKAGING
⚠ Possible alteration
```

---

# 21. CONSUMER DASHBOARD

Consumer Mode should be deliberately simpler than Inspector Mode.

Navigation:

```text
Home
Scan Product
My Scans
Product Details
Report an Issue
My Reports
Learn
Profile
```

Core flow:

```text
Scan Package
      ↓
Identify Product
      ↓
Analyze
      ↓
Consumer Result
```

Example:

```text
LEXMETRA PRODUCT CHECK

Product:
XYZ Biscuits

LEGAL METROLOGY
✓ MRP
✓ Net Quantity
✓ Manufacturer
✓ Date

FOOD SAFETY
✓ Applicable checks

PACKAGING
✓ No suspicious alteration detected

Overall:
No issue detected in captured evidence
```

Avoid absolute consumer statements such as:

> "This product is completely safe."

Use scoped language:

```text
No issue detected in the checks performed
Review recommended
Unable to determine from available evidence
Potential issue detected
```

---

# 22. CONSUMER TRUST CARD

A signature UI element:

```text
┌──────────────────────────────┐
│       LEXMETRA CHECK         │
│                              │
│ Legal Metrology       ✓      │
│ Food Safety            ✓     │
│ Packaging Integrity    ⚠     │
│ Evidence Quality       HIGH  │
│                              │
│ Overall: REVIEW ADVISED      │
└──────────────────────────────┘
```

The result uses both:

```text
icon + text + colour
```

so status is never communicated by colour alone.

---

# 23. CONSUMER REPORTING

Consumer can report:

```text
MRP mismatch
Missing declaration
Expired product
Suspicious packaging
Incorrect quantity
Suspicious label
Other issue
```

Flow:

```text
Consumer
 ↓
Capture
 ↓
AI pre-screen
 ↓
Evidence extraction
 ↓
Consumer confirmation
 ↓
Submit report
 ↓
Authority case
```

Evidence can include:

```text
Product photos
OCR results
Bounding boxes
Detected issue
Date/time
Location
Optional bill
Consumer description
```

---

# 24. AUTHORITY CASE MANAGEMENT

Authority Dashboard:

```text
Citizen Reports
 ├── New
 ├── Under Review
 ├── Assigned
 ├── Evidence Requested
 ├── Escalated
 ├── Resolved
 └── Rejected
```

Inspector can:

```text
Accept
Request evidence
Assign
Inspect
Escalate
Dismiss
Resolve
```

---

# 25. CONSUMER REPORT STATUS

Consumer sees:

```text
REPORT #LM-2026-004251

Submitted
✓

AI Pre-screened
✓

Forwarded to Authority
✓

Inspector Assigned
✓

Under Review
●

Resolved
○
```

This gives the consumer a transparent interaction with the authority.

---

# 26. COMPLAINT-TO-INSPECTION INTELLIGENCE

This can become one of LexMetra's strongest advanced USPs.

Suppose:

```text
17 reports
8 locations
1 product family
same suspected issue
```

The platform can generate:

```text
EMERGING REGULATORY PATTERN

Product:
XYZ

Reports:
17

Locations:
8

Primary issue:
Possible MRP alteration

Recommendation:
Prioritise inspection
```

This is not autonomous enforcement.

It is:

> **decision support for authorities.**

---

# 27. ANALYTICS DASHBOARD

Three data sources:

```text
INSPECTIONS
+
CONSUMER REPORTS
+
REGULATORY FINDINGS
```

### Inspection analytics

```text
Total inspections
PASS
FAIL
UNCERTAIN
EXEMPT
REVIEW
```

### Violation analytics

```text
MRP
Net Quantity
Date
Manufacturer
Consumer Care
Unit Sale Price
```

### Consumer analytics

```text
Reports/day
Top reported products
Top reported categories
Issue distribution
Resolution rate
```

### Tampering analytics

```text
Tampering alerts
MRP sticker alerts
Packaging anomalies
Repeated product issues
```

### AI analytics

```text
OCR confidence
OCR conflict rate
Recapture rate
Evidence sufficiency
Human-review rate
```

### Operational analytics

```text
Average inspection time
Average number of captures
Amendment processing time
Case resolution time
```

---

# 28. REGULATORY RISK INTELLIGENCE

Analytics can aggregate patterns without automatically accusing businesses.

Example:

```text
REGULATORY RISK

High
MRP mismatch

Medium
Missing declarations

High
Repeated tampering complaints

Emerging
Specific product category showing
increased complaint frequency
```

This can become an authority decision-support layer.

---

# 29. LEGAL RAG

RAG does NOT determine legality.

It provides:

```text
Legal explanation
Rule search
Amendment lookup
Historical rule information
Inspection explanation
Source citations
```

Example:

> Why was this inspection marked FAIL?

RAG can combine:

```text
Inspection
+
OpenL finding
+
RuleSet version
+
Official source
```

and return:

```text
Rule:
LMPC-2011-R6-11

Version:
2026.2

Finding:
Declared unit sale price differs from
calculated unit sale price.

Evidence:
MRP ₹499
Net Quantity 500 g
...

Source:
Official notification...
```

---

# 30. FINAL RAG STACK

```text
PostgreSQL
+
pgvector
+
BGE-M3
+
Lexical/BM25 retrieval
+
Reranker
```

No separate vector database is necessary initially.

RAG result:

```text
answer
rule_id
clause
version
source
page
citation
```

---

# 31. ADAPTIVE RAG

Query routing:

```text
User Question
      ↓
Intent Classifier
      │
      ├── Exact Rule Lookup
      ├── Amendment Lookup
      ├── Inspection Lookup
      ├── Legal Explanation
      └── Evidence Question
```

For example:

```text
"Show Rule 6(11)"
      ↓
structured RuleSet lookup
```

while:

```text
"Why is unit sale price required?"
      ↓
semantic legal retrieval
```

---

# 32. MULTILINGUAL SYSTEM

Initial supported languages:

```text
English
Hindi
Marathi
```

Internally, canonical fields remain stable:

```text
mrp
net_quantity
mfg_date
common_name
```

The UI can display:

```text
MRP
अधिकतम खुदरा मूल्य
कमाल किरकोळ किंमत
```

Rule IDs never change with language.

---

# 33. TRANSLATION + VOICE

Translation candidate:

**IndicTrans2**

Voice architecture:

```text
Voice
 ↓
Speech-to-Text
 ↓
Intent extraction
 ↓
Structured action
 ↓
Backend
 ↓
Response
 ↓
Text-to-Speech
```

Use a provider abstraction so Bhashini/local services can be swapped later.

---

# 34. INSPECTOR ASSISTANT

Do not build a generic unrestricted chatbot.

Build:

# Inspector Assistant

Default actions:

```text
[ Scan Package ]
[ Check Compliance ]
[ Explain Violation ]
[ View Evidence ]
[ Search Rule ]
[ Check Amendment ]
[ Inspection History ]
```

Voice:

```text
🎤 Speak
```

The menu-first model reduces typing and limits hallucination risk.

---

# 35. EVIDENCE VIEWER

A central screen:

```text
┌──────────────────────────────────────┐
│                                      │
│        ORIGINAL PRODUCT IMAGE        │
│                                      │
│     ┌──────────────────────┐         │
│     │ MRP ₹499             │         │
│     └──────────────────────┘         │
│                                      │
│     ┌─────────────────────┐          │
│     │ NET QTY 500 g       │          │
│     └─────────────────────┘          │
│                                      │
└──────────────────────────────────────┘

Selected:
MRP

OCR: ₹499
Confidence: 96%
Engine: PaddleOCR + Tesseract
Agreement: CORROBORATED
Rule: 6(11)
RuleSet: 2026.2
```

Interaction:

```text
Click finding
 ↓
Zoom
 ↓
Highlight bbox
 ↓
Show OCR
 ↓
Show confidence
 ↓
Show provenance
 ↓
Show rule
 ↓
Show version
```

---

# 36. GOVERNMENT-STYLE UI

The visual language should be:

```text
Trust
Authority
Precision
Clarity
Evidence
Accessibility
```

not:

```text
Gaming
Neon
Fintech
Startup SaaS
```

The current GIGW 3.0 framework is intended for Indian government websites/apps and emphasizes user-centricity, accessibility, multilingual delivery, security and citizen-facing usability. ([guidelines.india.gov.in](https://guidelines.india.gov.in/new-features-of-gigw-3-0/?utm_source=chatgpt.com))

---

# 37. FINAL COLOUR SYSTEM

|Role|Direction|
|---|---|
|Primary|Deep government navy / blue|
|Background|Warm/light neutral|
|Surface|White|
|Primary text|Very dark charcoal|
|Secondary text|Slate grey|
|Success|Accessible green|
|Warning|Accessible amber|
|Error|Accessible red|
|Information|Blue|

Avoid excessive gradients and saturated decorative colours.

---

# 38. ACCESSIBILITY / STATUS DESIGN

Never use colour as the only indicator.

Use:

```text
✓ PASS
✕ FAIL
! UNCERTAIN
↻ REVIEW
○ EXEMPT
```

with appropriate colour support.

Target:

```text
4.5:1 normal text contrast
3:1 relevant UI/graphic contrast
```

and design toward WCAG 2.1 AA/GIGW expectations.

---

# 39. GOVERNMENT INFORMATION ARCHITECTURE

Header:

```text
Government / Department Context
LexMetra
Language Selector
Inspector / User
```

Sidebar:

```text
Dashboard
Inspections
Scan Package
Amendments
Rules
Evidence
Analytics
Assistant
```

Footer:

```text
About
Help
Accessibility
Privacy
Contact
Feedback
Version
Last Updated
```

For an SIH prototype, do not falsely represent LexMetra as an officially deployed government system. Clearly distinguish prototype/demo identity from the eventual deployment context.

---

# 40. SECURITY / RBAC

Core roles:

```text
Inspector
Reviewer
Admin
Legal / Domain Authority
```

Examples:

|Action|Inspector|Reviewer|Admin|
|---|--:|--:|--:|
|Scan|✓|✓|✓|
|Review inspection|—|✓|✓|
|Upload amendment|✓|✓|✓|
|Validate amendment|✓|✓|✓|
|Activate RuleSet|—|controlled|✓|
|Audit|—|—|✓|

Exact production permissions can be refined during implementation.

---

# 41. AUDIT TRAIL

Record:

```text
Login
Inspection creation
OCR result
Rule evaluation
Review action
Amendment upload
Amendment approval
Rule activation
Report generation
Consumer report
Case assignment
Case resolution
```

Every important event:

```text
Who
What
When
Object
Rule version
Result
```

---

# 42. FINAL DATABASE MODEL

```text
users

consumers

products

inspections
inspection_sessions
session_captures
inspection_facts
evidence

rulesets
rules

amendments
amendment_changes

legal_documents
legal_embeddings

fssai_rules
fssai_findings

tamper_findings
product_history

consumer_scans
consumer_reports

cases
case_assignments
case_status_history

audit_log
```

Logical relationships:

```text
Consumer
   ↓
Consumer Report
   ↓
Case
   ↓
Inspection
   ↓
Evidence
   ↓
Findings
   ↓
Action
   ↓
Resolution
```

and:

```text
Product
   ↓
Historical Packages
   ↓
Inspections
   ↓
Complaints
   ↓
Tampering
   ↓
Regulatory Intelligence
```

---

# 43. FINAL REPOSITORY STRUCTURE

```text
LexMetra/
│
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── auth.py
│   │
│   ├── api/
│   │   ├── inspection.py
│   │   ├── consumer.py
│   │   ├── amendments.py
│   │   ├── reports.py
│   │   └── analytics.py
│   │
│   ├── cv/
│   │   ├── yolo_detector.py
│   │   ├── region_detection.py
│   │   ├── image_quality.py
│   │   └── tamper/
│   │       ├── sticker_detector.py
│   │       ├── seal_detector.py
│   │       ├── print_consistency.py
│   │       └── anomaly_fusion.py
│   │
│   ├── ocr/
│   │   ├── ocr_engine.py
│   │   ├── tesseract_adapter.py
│   │   ├── paddleocr_adapter.py
│   │   ├── fusion.py
│   │   └── extraction.py
│   │
│   ├── evidence/
│   │   ├── normalizer.py
│   │   ├── provenance.py
│   │   ├── confidence.py
│   │   └── coverage.py
│   │
│   ├── rules/
│   │   ├── openl_adapter.py
│   │   ├── resolver.py
│   │   ├── safety_gate.py
│   │   └── reference_engine.py
│   │
│   ├── regulations/
│   │   ├── legal_metrology/
│   │   └── fssai/
│   │
│   ├── amendments/
│   │   ├── ingestion.py
│   │   ├── diff.py
│   │   ├── workflow.py
│   │   └── approval.py
│   │
│   ├── consumer/
│   │   ├── products.py
│   │   ├── reports.py
│   │   └── cases.py
│   │
│   ├── analytics/
│   │   └── service.py
│   │
│   ├── rag/
│   │   ├── embeddings.py
│   │   ├── retriever.py
│   │   ├── router.py
│   │   └── citations.py
│   │
│   ├── assistant/
│   │   ├── intent.py
│   │   ├── chat.py
│   │   ├── voice.py
│   │   └── actions.py
│   │
│   ├── db/
│   │   ├── schema.sql
│   │   └── persistence.py
│   │
│   └── tests/
│
├── openl/
│   ├── rulesets/
│   │   ├── 2026.1/
│   │   ├── 2026.2/
│   │   └── ...
│   └── tables/
│
├── frontend/
│   ├── inspector/
│   ├── consumer/
│   ├── authority/
│   ├── evidence/
│   ├── amendments/
│   ├── analytics/
│   └── assistant/
│
├── dataset/
│   ├── images/
│   ├── annotations/
│   ├── tampering/
│   ├── fssai/
│   └── evaluation/
│
├── rag/
│   ├── legal_documents/
│   └── indexes/
│
├── docs/
│   ├── architecture/
│   ├── rule-governance/
│   ├── fssai/
│   ├── consumer-flow/
│   ├── gigw/
│   └── testing/
│
├── experiments/
│   ├── paddleocr/
│   ├── yolo/
│   ├── surya/
│   ├── tamper/
│   └── rag/
│
├── docker-compose.yml
├── README.md
└── .env.example
```

### Repository principle

```text
main = clean + tested + runnable
```

Experimental work stays inside:

```text
experiments/
```

until it passes defined evaluation criteria.

---

# 44. GIT / DEVELOPMENT DISCIPLINE

Recommended branches:

```text
main
develop (optional)

feature/openl-migration
feature/paddleocr
feature/yolo-layout
feature/evidence-viewer
feature/amendment-workflow
feature/multilingual-ui
feature/analytics
feature/tamper-detection
feature/fssai
feature/consumer-dashboard
feature/consumer-reporting
feature/assistant
```

No direct experimental commits into `main`.

---

# 45. CI/CD GATES

Every PR:

```text
Lint
Tests
Integration tests
Database/schema checks
OpenL differential tests
Frontend checks
Secrets scan
```

Only merge when all pass.

---

# 46. FINAL IMPLEMENTATION PHASES

## PHASE 0 — Baseline Freeze

```text
Current repo
 ↓
Tests
 ↓
Docker
 ↓
Database
 ↓
Clean main
 ↓
BASELINE RELEASE
```

---

## PHASE 1 — OpenL Migration

```text
Current engine
 ↓
Reference implementation

OpenL
 ↓
Adapter

Differential testing
 ↓
OpenL production execution
```

---

## PHASE 2 — Multiversion Legal Governance

```text
RuleSet
Version
Effective date
Approval
Hash
```

Output:

> Immutable legal-rule history.

---

## PHASE 3 — Amendment System

```text
Gazette
 ↓
OCR
 ↓
Proposed change
 ↓
Diff
 ↓
Inspector validation
 ↓
Legal validation
 ↓
New RuleSet
 ↓
OpenL
 ↓
Scheduled activation
```

---

## PHASE 4 — Evidence Viewer

```text
Original image
+
bbox
+
OCR
+
confidence
+
rule
+
version
+
provenance
```

---

## PHASE 5 — OCR Upgrade

```text
PaddleOCR
+
Tesseract
+
Existing fusion
```

Initial language target:

```text
English
Hindi
Marathi
```

---

## PHASE 6 — YOLO/CV

```text
YOLO region detection
 ↓
Semantic region
 ↓
OCR
```

---

## PHASE 7 — Packaging Tampering

```text
Stickers
Seals
Print consistency
Visual anomalies
Historical comparison
```

---

## PHASE 8 — FSSAI Cross-Verification

```text
Food detection
 ↓
FSSAI applicability
 ↓
FSSAI RuleSet
 ↓
Cross-regulatory report
```

---

## PHASE 9 — Consumer Platform

```text
Scan
 ↓
Product Check
 ↓
Trust Card
 ↓
Report Issue
 ↓
Track Report
```

---

## PHASE 10 — Authority Case Management

```text
Consumer Report
 ↓
AI pre-screen
 ↓
Authority Queue
 ↓
Inspector Assignment
 ↓
Inspection
 ↓
Resolution
```

---

## PHASE 11 — Analytics + Intelligence

```text
Inspection analytics
+
Consumer analytics
+
Tamper analytics
+
Regulatory analytics
+
Complaint clustering
+
Risk intelligence
```

---

## PHASE 12 — Legal RAG

```text
Official documents
 ↓
Parsing
 ↓
BGE-M3
 ↓
pgvector
 ↓
Hybrid retrieval
 ↓
Reranking
 ↓
Citations
```

---

## PHASE 13 — Inspector Assistant

```text
Menu-driven assistant
+
Chat
+
Multilingual
+
Voice
+
Structured actions
```

---

## PHASE 14 — Final Hardening

```text
Security
Accessibility
GIGW alignment
Multilingual QA
Docker
Clean deployment
Real-product testing
Failure scenarios
Demo reliability
```

---

# 47. WHAT IS CORE FOR SIH

## Tier A — Absolute Core

```text
✓ Legal Metrology compliance
✓ OCR
✓ Multilingual OCR
✓ YOLO/CV
✓ Evidence extraction
✓ Multi-surface inspection
✓ OpenL
✓ Multiversion rules
✓ Amendment governance
✓ Inspector validation
✓ Evidence viewer
✓ Audit trail
✓ RBAC
✓ Government-oriented frontend
```

## Tier B — Major USPs

```text
✓ Packaging tampering detection
✓ FSSAI cross-verification
✓ Consumer dashboard
✓ Consumer reporting
✓ Authority case workflow
✓ Analytics
✓ Product history
✓ Complaint intelligence
```

## Tier C — Advanced Differentiation

```text
✓ Legal RAG
✓ Multilingual voice assistant
✓ Regulatory risk intelligence
✓ Complaint clustering
✓ Advanced product intelligence
```

---

# 48. WHAT NOT TO LET BECOME SCOPE CREEP

Do not make these prerequisites:

```text
✗ Autonomous legal agent
✗ GraphRAG
✗ Massive VLM fine-tuning
✗ Custom LLM
✗ Kafka/event-driven architecture
✗ Multiple vector databases
✗ ARCore
✗ Complex microservices
✗ Full native mobile + web rewrite
```

They can remain future roadmap items.

---

# 49. FINAL TECHNOLOGY STACK

|Layer|Final Choice|
|---|---|
|Backend|**FastAPI**|
|Database|**PostgreSQL**|
|Vector|**pgvector**|
|Primary OCR|**PaddleOCR PP-OCRv5**|
|Secondary OCR|**Tesseract**|
|Experimental OCR|Surya|
|CV|**YOLO**|
|OCR fusion|Existing LexMetra fusion|
|Rule engine|**OpenL Tablets**|
|Reference engine|Existing LexMetra implementation|
|Rule versioning|**LexMetra Governance + OpenL**|
|Embeddings|**BGE-M3**|
|Retrieval|Hybrid lexical + semantic|
|Reranking|Multilingual reranker|
|Translation|IndicTrans2|
|Voice|Bhashini-compatible/provider abstraction|
|Evidence|Existing provenance + bbox architecture|
|Tampering|CV anomaly/sticker pipeline|
|Food regulation|FSSAI regulatory layer|
|Auth|Existing RBAC|
|Analytics|PostgreSQL-backed|
|Deployment|Docker|
|Testing|pytest + integration + differential testing|
|Frontend|Government-oriented multilingual UI|
|Assistant|Structured multilingual inspector assistant|

---

# 50. FINAL PRODUCT MODEL

The complete final LexMetra model is:

```text
                         LEXMETRA
                            │
       ┌────────────────────┼────────────────────┐
       │                    │                    │
       ▼                    ▼                    ▼
    DETECT                VERIFY                ACT
       │                    │                    │
       ▼                    ▼                    ▼
 YOLO / OCR            OpenL + Rules        Reports / Cases
 Tampering             LMPC + FSSAI        Authority Workflow
 Evidence              Versioning           Consumer Workflow
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                            ▼
                         CONNECT
                            │
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
         Consumer        Inspector       Authority
             │              │              │
             └──────────────┼──────────────┘
                            ▼
                       ANALYTICS
                            │
                            ▼
                 REGULATORY INTELLIGENCE
```

---

# 51. THE SINGLE MOST IMPORTANT ARCHITECTURAL PRINCIPLE

```text
AI / CV / OCR
    =
Evidence extraction

Evidence Layer
    =
Trustworthiness + sufficiency

OpenL
    =
Execution of approved legal rules

Rule Governance
    =
Version + effective date + approval

Human Inspector / Legal Authority
    =
Amendment validation

RAG
    =
Knowledge + explanation

Consumer Platform
    =
Detection + reporting + engagement

Authority Platform
    =
Investigation + action

Analytics
    =
Patterns + intelligence

Audit
    =
Proof of what happened
```

And the two invariants that should guide the entire team:

> **No uncertain OCR result can silently become an active legal rule.**

> **No uncertain evidence can silently become a definitive legal violation.**

---

# 52. FINAL ONE-LINE PROJECT PITCH

> **LexMetra is an evidence-backed, multilingual regulatory intelligence platform that combines computer vision, OCR, packaging-integrity analysis, FSSAI cross-verification and an open-source multiversioned rule engine to connect consumers, inspectors and authorities through explainable, auditable compliance workflows.**

## The stronger SIH differentiator

> **LexMetra doesn't just detect a violation—it shows the evidence, identifies the exact rule and rule version behind the decision, prevents AI from silently changing the law, lets consumers report suspicious products, and turns inspection and complaint data into actionable regulatory intelligence.**