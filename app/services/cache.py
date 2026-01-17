"""Simple in-memory cache with TTL for audit results."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional


class InMemoryCache:
    """Async-safe in-memory TTL cache."""

    def __init__(self, max_entries: int = 512):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._max_entries = max_entries

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            if entry["expires_at"] <= time.time():
                self._store.pop(key, None)
                return None
            return entry["value"]

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if ttl_seconds <= 0 or self._max_entries <= 0:
            return
        expires_at = time.time() + ttl_seconds
        async with self._lock:
            if len(self._store) >= self._max_entries:
                self._evict_oldest()
            self._store[key] = {"value": value, "expires_at": expires_at, "created_at": time.time()}

    def _evict_oldest(self) -> None:
        if not self._store:
            return
        oldest_key = min(self._store.items(), key=lambda item: item[1]["created_at"])[0]
        self._store.pop(oldest_key, None)
