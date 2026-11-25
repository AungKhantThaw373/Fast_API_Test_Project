"""Small, dependency-free abuse controls for a single-process personal server.

The limits are intentionally in memory. A restart clears them, which is
acceptable for the home-server deployment in the build manual; a multi-process
deployment would move the buckets to Redis.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from app.models.app_models import User
from app.security import get_current_user

LOGIN_LIMIT = 5
LOGIN_WINDOW_SECONDS = 15 * 60
REGISTER_LIMIT = 3
REGISTER_WINDOW_SECONDS = 60 * 60
AI_SCAN_LIMIT = 10
AI_SCAN_WINDOW_SECONDS = 60 * 60
UPLOAD_LIMIT = 20
UPLOAD_WINDOW_SECONDS = 60 * 60
PASSWORD_RESET_LIMIT = 5
PASSWORD_RESET_WINDOW_SECONDS = 60 * 60


@dataclass
class _Bucket:
    tokens: float
    updated: float


class TokenBucketLimiter:
    """A monotonic-clock token bucket keyed by an arbitrary string."""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}

    def consume(self, key: str, limit: int, window_seconds: int) -> int | None:
        """Spend one token. Return ``None`` when allowed, else retry seconds."""
        now = time.monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=float(limit), updated=now)
        else:
            refill = (now - bucket.updated) * (limit / window_seconds)
            bucket.tokens = min(float(limit), bucket.tokens + refill)
            bucket.updated = now
        if bucket.tokens < 1:
            self._buckets[key] = bucket
            return max(1, math.ceil((1 - bucket.tokens) * window_seconds / limit))
        bucket.tokens -= 1
        self._buckets[key] = bucket
        return None

    def peek(self, key: str, limit: int, window_seconds: int) -> int | None:
        """Report the wait without spending a token."""
        bucket = self._buckets.get(key)
        if bucket is None:
            return None
        now = time.monotonic()
        tokens = min(float(limit), bucket.tokens + (now - bucket.updated) * (limit / window_seconds))
        if tokens >= 1:
            return None
        return max(1, math.ceil((1 - tokens) * window_seconds / limit))

    def reset(self, prefix: str | None = None) -> None:
        if prefix is None:
            self._buckets.clear()
            return
        for key in [key for key in self._buckets if key.startswith(prefix)]:
            self._buckets.pop(key, None)


limiter = TokenBucketLimiter()


def client_ip(request: Request) -> str:
    # Do not trust X-Forwarded-For here. The bundled deployment puts Caddy in
    # front only for TLS; if a proxy is added, make this trustworthy explicitly.
    return request.client.host if request.client and request.client.host else "unknown"


def _too_many(retry_after: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(retry_after)},
    )


async def register_rate_limit(request: Request) -> None:
    retry_after = limiter.consume(
        f"register:{client_ip(request)}", REGISTER_LIMIT, REGISTER_WINDOW_SECONDS
    )
    if retry_after is not None:
        raise _too_many(retry_after, "Too many accounts were created from this address. Try again later.")


async def ai_scan_rate_limit(user: User = Depends(get_current_user)) -> None:
    retry_after = limiter.consume(
        f"ai-scan:{user.id}", AI_SCAN_LIMIT, AI_SCAN_WINDOW_SECONDS
    )
    if retry_after is not None:
        raise _too_many(retry_after, "AI scan limit reached (10 per hour). Try again later.")


async def upload_rate_limit(user: User = Depends(get_current_user)) -> None:
    retry_after = limiter.consume(
        f"upload:{user.id}", UPLOAD_LIMIT, UPLOAD_WINDOW_SECONDS
    )
    if retry_after is not None:
        raise _too_many(retry_after, "Upload limit reached (20 per hour). Try again later.")


async def password_reset_rate_limit(request: Request) -> None:
    retry_after = limiter.consume(
        f"password-reset:{client_ip(request)}", PASSWORD_RESET_LIMIT, PASSWORD_RESET_WINDOW_SECONDS
    )
    if retry_after is not None:
        raise _too_many(retry_after, "Too many password reset requests. Try again later.")


def reset_rate_limits() -> None:
    """Test hook; also useful after an operator unlocks an account."""
    limiter.reset()