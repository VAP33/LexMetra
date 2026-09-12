# Build 10 — Production Hardening

This is the final engineering hardening build before the acceptance/cleanup build.
It is intentionally additive and provider-neutral. Existing inspection, OCR/CV,
RAG, authentication, PDF, audit, and frontend paths remain the source of truth.

## What this package contains

1. `backend/runtime_hardening.py`
   - bounded TTL cache;
   - deterministic cache-key helper;
   - optional-provider circuit breaker.
2. `backend/tests/test_build10_runtime_hardening.py`
   - expiration/bounds tests;
   - stable-key tests;
   - circuit-opening/recovery tests;
   - no-fake-result test.
3. `ops/README_BUILD10.md`
   - integration boundary and deployment notes.
4. `ops/redis.env.example`
   - optional Redis configuration surface.

## Important boundary

Redis/caches are operational acceleration only. They must never be used as the
legal rule registry, inspection evidence store, or final compliance decision.
PostgreSQL remains the durable persistence layer. Existing RAG legal chunks remain
immutable. Rule selection still depends on explicit effective-date/version data.

## OCR stability

The current repository deliberately keeps PaddleOCR optional. On some Windows
Python 3.12 environments its ModelScope/PaddleX/Torch import path can produce a
native access violation before Python exception handling can help. Build 10 does
not pretend that can be fixed in pure Python. The recommended hardening is to use
the circuit only around optional provider calls and prefer a container/Linux
runtime for the production OCR stack, while preserving Tesseract fallback.

## Verification

Set `PYTHONPATH=backend` in PowerShell before running the suite.

```powershell
$env:PYTHONPATH="backend"
python -m pytest backend\tests\test_build10_runtime_hardening.py -q
python -m py_compile backend\runtime_hardening.py
python -m pytest -q
```

## Do not delete

- existing `backend/rule_engine.py`
- existing `backend/report.py`
- existing audit persistence
- existing authentication
- existing frontend
- duplicate `Chatgpt Patch/` tree (comparison/cleanup remains Build 11)

## Build boundary

Build 10 does not activate legal amendments autonomously, replace official
sources, or make an ML model a legal authority. Build 11 is the final acceptance
and cleanup pass.
