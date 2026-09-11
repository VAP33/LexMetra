# Build 10 — Production Hardening

Build 10 hardens runtime reliability around the existing LexMetra architecture.
It does not change the legal authority boundary.

## Scope

- bounded local caching helpers that are correctness-optional;
- provider circuit breaking for optional OCR/VLM/native runtimes;
- explicit Redis-ready configuration surface for deployment layers;
- structured operational verification commands;
- deployment hardening notes for PostgreSQL/Redis and health/readiness;
- no change to OCR evidence semantics, RAG citations, applicability, or the
  deterministic legal rule engine.

## Non-negotiable safety boundary

AI/OCR extracts evidence -> RAG retrieves knowledge -> applicability resolves
scope -> deterministic rule engine evaluates -> human resolves material
uncertainty.

Caches, Redis, queues, model providers, and health logic may change availability
or latency, but they MUST NOT become sources of legal truth or invent evidence.

## Integration

Copy `backend/runtime_hardening.py` and its test into the repository.
Add the Redis environment variables from `ops/redis.env.example` to the real
runtime only when Redis is actually deployed.

The circuit helper is intended for optional PaddleOCR/VLM/network adapters so a
native access violation or repeated provider exception can trip a bounded path
rather than repeatedly destabilizing the API process.

No legal verdict should ever be read from this cache or circuit state.
