# LexMetra Build 02: /scan Visual Evidence Recovery

This patch integrates the existing multimodal visual recovery into the real `/scan` pipeline.

## What changes
- Weak/absent OCR declarations are sent to `recover_fields_from_image()` using the actual uploaded PIL image.
- Recovered values enter the shared evidence map **before** `run_inspection()`.
- Existing OCR values are never overwritten.
- OCR/VLM disagreement is preserved as `CONFLICTING` evidence with `review_required=true` and an alternative value.
- The VLM remains an evidence extractor. It does not make PASS/FAIL decisions.
- If the VLM is unavailable or returns invalid data, the deterministic OCR/CV/rule-engine path continues.

## Apply
From the repository root:

```text
python apply_build02.py
```

Then run:

```text
python -m pytest backend/tests/test_visual_recovery_merge.py
python -m compileall backend
```

Push the resulting changes to GitHub yourself, then use the GitHub-backed repo as the source of truth for the next iteration.

## Safety invariant
`NOT_OBSERVED != FAIL`; conflicting evidence cannot silently become a confident fact; the deterministic rule engine remains the only compliance authority.
