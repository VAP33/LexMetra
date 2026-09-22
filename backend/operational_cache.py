"""Non-authoritative operational cache.

This module is deliberately incapable of representing regulatory truth.
Cache keys must include the rule/index version whenever cached data depends
on regulatory knowledge. A cache miss, outage, or stale entry must never
change a compliance verdict.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class CacheEntry:
    value: str
    expires_at: float


class LocalTTLCache:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[str]:
        item = self._items.get(key)
        if item is None:
            return None
        if item.expires_at <= time.time():
            self._items.pop(key, None)
            return None
        return item.value

    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        self._items[key] = CacheEntry(value=value, expires_at=time.time() + ttl)


class OperationalCache:
    """Redis when configured, otherwise a bounded local TTL fallback."""

    def __init__(self) -> None:
        self.redis_url = os.environ.get("REDIS_URL", "")
        self._local = LocalTTLCache(
            ttl_seconds=int(os.environ.get("CACHE_TTL_SECONDS", "300"))
        )
        self._redis = None

    def _client(self):
        if self._redis is not None:
            return self._redis
        if not self.redis_url:
            return None
        try:
            import redis
            self._redis = redis.Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            self._redis.ping()
            return self._redis
        except Exception:
            self._redis = None
            return None

    def get(self, key: str) -> Optional[str]:
        client = self._client()
        if client is not None:
            try:
                return client.get(key)
            except Exception:
                self._redis = None
        return self._local.get(key)

    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds or self._local.ttl_seconds
        client = self._client()
        if client is not None:
            try:
                client.setex(key, ttl, value)
                return
            except Exception:
                self._redis = None
        self._local.set(key, value, ttl)


cache = OperationalCache()
