"""Production-runtime hardening helpers for LexMetra.

This module is deliberately independent of the legal rule engine. It provides
bounded caching keys, safe operational metrics, and OCR backend circuit-breaking
so infrastructure failures cannot become legal decisions.
"""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional


class EngineStatus(str, Enum):
    """Explicit lifecycle and degradation states for OCR engines."""

    CONFIGURED = "CONFIGURED"
    INITIALIZING = "INITIALIZING"
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class CachePolicy:
    ttl_seconds: int = 300
    max_items: int = 1024


class TTLCache:
    """Small thread-safe in-process cache; correctness never depends on it."""

    def __init__(self, policy: CachePolicy | None = None) -> None:
        self.policy = policy or CachePolicy()
        self._items: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            row = self._items.get(key)
            if row is None:
                return None
            expires_at, value = row
            if expires_at <= now:
                self._items.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        expires_at = time.monotonic() + max(1, int(self.policy.ttl_seconds))
        with self._lock:
            self._items[key] = (expires_at, value)
            while len(self._items) > max(1, int(self.policy.max_items)):
                oldest = min(self._items, key=lambda item: self._items[item][0])
                self._items.pop(oldest, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


def stable_cache_key(prefix: str, *parts: Any) -> str:
    payload = "|".join([str(prefix), *(str(p) for p in parts)])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


class CircuitOpenError(RuntimeError):
    """Raised when an optional provider is temporarily circuit-open."""


class FailureCircuit:
    """Tiny circuit breaker for optional native/remote providers.

    The circuit only controls whether a provider is attempted. It never supplies
    an alternative legal result and therefore cannot affect compliance semantics.
    """

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 30) -> None:
        self.failure_threshold = max(1, int(failure_threshold))
        self.cooldown_seconds = max(1, int(cooldown_seconds))
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.RLock()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if time.monotonic() - self._opened_at >= self.cooldown_seconds:
                self._opened_at = None
                self._failures = 0
                return True
            return False

    def success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.monotonic()

    def run(self, fn: Callable[[], Any]) -> Any:
        if not self.allow():
            raise CircuitOpenError("provider circuit is temporarily open")
        try:
            value = fn()
        except Exception:
            self.failure()
            raise
        self.success()
        return value
