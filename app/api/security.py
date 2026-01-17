"""Security dependencies: rate limiting."""
from __future__ import annotations

import asyncio
import time
from typing import Dict, List

from fastapi import HTTPException, Request

from app.config import settings

_RATE_LIMIT_STORE: Dict[str, List[float]] = {}
_RATE_LIMIT_LOCK = asyncio.Lock()
_LAST_CLEANUP = 0.0
_CLEANUP_INTERVAL = 300  # Clean up every 5 minutes


def _extract_client_id(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip", "")
        if real_ip:
            return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def _cleanup_rate_limit_store(now: float) -> None:
    """Remove stale entries from rate limit store to prevent memory leak."""
    global _LAST_CLEANUP
    if now - _LAST_CLEANUP < _CLEANUP_INTERVAL:
        return

    _LAST_CLEANUP = now
    cutoff = now - 300  # Remove entries older than 5 minutes
    to_delete = []
    for client_id, timestamps in _RATE_LIMIT_STORE.items():
        # Keep only recent timestamps
        fresh = [ts for ts in timestamps if ts > cutoff]
        if not fresh:
            to_delete.append(client_id)
        else:
            _RATE_LIMIT_STORE[client_id] = fresh

    for client_id in to_delete:
        del _RATE_LIMIT_STORE[client_id]


async def rate_limit(request: Request) -> None:
    """Simple in-memory rate limiter (per client, per minute)."""
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return

    now = time.time()
    window = 60
    client_id = _extract_client_id(request)

    async with _RATE_LIMIT_LOCK:
        # Periodically clean up stale entries
        await _cleanup_rate_limit_store(now)

        timestamps = _RATE_LIMIT_STORE.get(client_id, [])
        window_start = now - window
        timestamps = [ts for ts in timestamps if ts > window_start]
        if len(timestamps) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        timestamps.append(now)
        _RATE_LIMIT_STORE[client_id] = timestamps
