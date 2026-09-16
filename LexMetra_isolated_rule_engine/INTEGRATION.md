# Integration Contract

## Intended integration

The host application supplies product information to the engine. It should not depend on engine internals.

```python
from engine import ComplianceEngine

engine = ComplianceEngine()
report = engine.evaluate(product_json)
payload = report.to_dict()
```

The host may also supply an assessment date and additional context:

```python
report = engine.evaluate(
    product_json,
    assessment_date="2026-09-16",
    context={"trade_type": "retail"},
)
```

For existing callers that already build `Evidence`, pass the Evidence object directly; the underlying RuleEngine contract is preserved.

## Do not couple to

- OCR classes
- image processing
- frontend components
- FastAPI routes
- database models
- Redis

## Current limitation

This is the framework boundary, not the finished regulatory reasoning layer. Product classification, advanced legal applicability, exclusion/proviso handling, dynamic clarification questions, and a regulatory golden test suite should be built as subsequent isolated tasks.
