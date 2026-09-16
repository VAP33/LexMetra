# LexMetra SIH MVP Reliability Patch

## Purpose

This patch targets the remaining demo-critical seams in the OCR/CV/VLM/evidence pipeline while retaining the MVP fallback behavior.

## Fixed

- PaddleOCR is requested by default and integrated as a complementary OCR engine.
- PaddleOCR 3.x prediction output is normalized into LexMetra's existing OCR evidence model; a legacy 2.x adapter remains available.
- Tesseract remains a safe fallback when PaddleOCR is unavailable.
- Gemini visual recovery is enabled by default when a Gemini key exists and is invoked only for weak/partial fields.
- `/scan` now uses visual recovery as well as session captures.
- Manufacturer/packer/importer inline declarations are extracted from the same OCR line.
- Explicit Common Name labels are no longer swallowed by manufacturer follow-line association.
- Cross-surface contradictions remain visible as evidence but become `REVIEW_REQUIRED` rather than silently becoming authoritative.
- Canonical declarations are persisted and hydrated from history.
- `/health` reports active OCR engines and VLM availability without exposing credentials.
- Quantity/calibration safety changes from the previous patch remain in place.
- Rule 8 PDP placement logic remains evidence-based rather than passing on PDP existence alone.

## Validation

Targeted and non-auth/API tests:

**341 passed, 2 skipped**

The complete local suite cannot be collected in this stripped runtime because `python-jose` is not installed. The auth and API-integration modules therefore fail during collection before executing project assertions. This is an environment dependency issue, not a test assertion failure.

## Important demo note

The fallback remains deliberately intact. The product should demonstrate a layered evidence pipeline, not pretend that arbitrary photographs are always perfectly readable. When OCR is weak, the system can attempt visual recovery; when evidence still cannot be established, it reports insufficient/review-required evidence rather than inventing a declaration.

## Current limits

- PaddleOCR must be installed on the actual demo machine to become an active engine.
- Gemini visual recovery requires a working Gemini API key and network access.
- No claim is made that arbitrary glare, severe blur, extreme curvature, or occlusion can be recovered perfectly.
- Legal rule coverage is limited to the rules currently implemented in the repository.
