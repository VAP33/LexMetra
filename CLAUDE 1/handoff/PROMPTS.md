# Prompts to paste into each of your 4 Claude accounts

For each session: upload the files listed at the end of that workstream's
`.md` brief, paste the corresponding prompt below as your first message,
then attach the brief itself too (or paste its content in).

---

## Session 1 — Capture & Extraction

```
I'm building the capture/extraction layer for a Legal Metrology compliance
platform (Smart India Hackathon project). Attached: 00_PROJECT_STATUS_AND_SPLIT.md
(shared project context — read this first) and 01_capture_and_extraction.md
(your actual brief), plus the current schema.py, ocr_extraction.py, main.py,
vlm_verifier.py, rule_engine.py, and real product photos.

Read both markdown files fully before writing any code. The brief explains
why training a custom object-detection model is likely the wrong move for
our constraints, and recommends a multimodal-LLM extraction approach
instead — engage with that reasoning, don't just default to it or dismiss
it without stating why.

Build the deliverables in the brief. Test everything against the real
photos I've attached before telling me anything is done — this project has
already been burned twice by code that looked right but wasn't run. Show
me actual output, not just the code.
```

---

## Session 2 — Legal Engine Versioning

```
I'm building the amendment-aware, multi-versioned rule engine for a Legal
Metrology compliance platform (Smart India Hackathon project). Attached:
00_PROJECT_STATUS_AND_SPLIT.md (shared project context — read this first)
and 02_legal_engine_versioning.md (your actual brief), plus the current
rules.json, rule_engine.py, exemption.py, and schema.py.

Read both markdown files fully before writing any code. Confirm for
yourself (don't take my word for it) that rule_engine.py currently never
reads effective_from/effective_to — grep for it. Then build the
family/version restructuring and the date-based resolver described in the
brief, preserving every existing rule_id as a current-version id so nothing
else in the codebase breaks.

Do not invent legal thresholds or amendment dates you can't source — leave
a clear TODO instead of guessing. Write and run actual unit tests with
fabricated dates (before/on/after an amendment, and a future-dated
amendment) before telling me this is done.
```

---

## Session 3 — Tampering Detection + FSSAI Cross-Verification

```
I'm building two USP features for a Legal Metrology compliance platform
(Smart India Hackathon project): packaging tampering detection against
trusted reference images, and FSSAI cross-verification. Attached:
00_PROJECT_STATUS_AND_SPLIT.md (shared project context — read this first)
and 03_tampering_and_fssai.md (your actual brief), plus the current
sticker_detection.py, product_similarity.py, schema.py, schema.sql, and
persistence.py.

Read both markdown files fully first. Note explicitly that
sticker_detection.py and product_similarity.py are NOT this USP — the
brief explains why. Build the reference-image registry and field-level
comparison logic described.

For the FSSAI part: do not fabricate license numbers or product records.
If you don't have access to real FSSAI data, build against a clearly
labeled sample dataset and tell me plainly that it's a sample, the same way
this project already discloses its synthetic image dataset elsewhere.
Never let either signal auto-fail a product — both must only raise a
review flag, feeding the deterministic rule engine's own decision, not
replacing it. Confirm you understood this constraint in your own words
before implementing it.
```

---

## Session 4 — Consumer Reporting + PDF Generation

```
I'm building the consumer-to-authority reporting feature and PDF report
generation for a Legal Metrology compliance platform (Smart India
Hackathon project). Attached: 00_PROJECT_STATUS_AND_SPLIT.md (shared
project context — read this first) and 04_reporting_and_pdf.md (your
actual brief), plus the current schema.py, schema.sql, persistence.py, and
main.py.

Read both markdown files first. This workstream has no existing code to
build on — you're building the reports data model, endpoints, and PDF
generation from scratch, following the same patterns already established
for inspections (I've attached persistence.py and main.py as the style to
match).

Think about consumer privacy before building the data model — reporter
identity should be optional, not required. Test by actually submitting a
report through your endpoint and reading it back from Postgres, and by
generating a real PDF from an existing inspection and showing me its
actual content, not just working code.
```
