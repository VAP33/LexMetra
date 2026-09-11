from __future__ import annotations

import time

from backend.runtime_hardening import CachePolicy, CircuitOpenError, FailureCircuit, TTLCache, stable_cache_key


def test_cache_expires_and_is_bounded():
    cache = TTLCache(CachePolicy(ttl_seconds=1, max_items=2))
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert len(cache._items) == 2
    assert cache.get("a") is None
    assert cache.get("c") == 3


def test_cache_key_is_stable_and_namespaced():
    assert stable_cache_key("rag", "rule6", "2026-01-01") == stable_cache_key("rag", "rule6", "2026-01-01")
    assert stable_cache_key("rag", "x") != stable_cache_key("inspection", "x")


def test_circuit_opens_only_after_threshold_and_recovers():
    circuit = FailureCircuit(failure_threshold=2, cooldown_seconds=1)
    assert circuit.allow()
    circuit.failure()
    assert circuit.allow()
    circuit.failure()
    assert not circuit.allow()
    time.sleep(1.02)
    assert circuit.allow()
    circuit.success()
    assert circuit.allow()


def test_circuit_run_never_returns_fake_value_on_failure():
    circuit = FailureCircuit(failure_threshold=1)
    def boom():
        raise RuntimeError("provider failed")
    try:
        circuit.run(boom)
    except RuntimeError:
        pass
    else:
        raise AssertionError("provider failure was swallowed")
    try:
        circuit.run(lambda: "must not run")
    except CircuitOpenError:
        pass
    else:
        raise AssertionError("open circuit executed provider")
