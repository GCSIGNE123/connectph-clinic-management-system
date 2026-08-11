"""Simple fixed-window rate limiter.

Uses Redis (async client) when `settings.REDIS_URL` is reachable; otherwise
falls back to an in-process in-memory counter. The in-memory fallback is NOT
safe across multiple worker processes/instances - it exists so the platform
still degrades gracefully in dev/test environments without Redis. Document
this assumption for anyone deploying multiple API workers: point REDIS_URL at
a real shared Redis instance in production so limits are enforced globally.
"""

import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status

from app.core.config import settings

_memory_buckets: dict[str, list[float]] = defaultdict(list)
_memory_lock = Lock()

_redis_client = None
_redis_unavailable = False


def _get_redis():
    """Lazily construct a redis-py async client. Returns None if unavailable."""
    global _redis_client, _redis_unavailable
    if _redis_unavailable:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis.asyncio as redis  # noqa: PLC0415

        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        return _redis_client
    except Exception:  # pragma: no cover - redis lib absent or misconfigured
        _redis_unavailable = True
        return None


async def _check_memory(key: str, *, max_attempts: int, window_seconds: int) -> bool:
    now = time.monotonic()
    with _memory_lock:
        bucket = _memory_buckets[key]
        cutoff = now - window_seconds
        bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= max_attempts:
            return False
        bucket.append(now)
        return True


async def _check_redis(redis_client, key: str, *, max_attempts: int, window_seconds: int) -> bool:
    try:
        pipe = redis_client.pipeline()
        pipe.incr(key, 1)
        pipe.expire(key, window_seconds, nx=True)
        count, _ = await pipe.execute()
        return int(count) <= max_attempts
    except Exception:  # pragma: no cover - redis connectivity issue at call time
        return await _check_memory(key, max_attempts=max_attempts, window_seconds=window_seconds)


async def check_rate_limit(*, bucket: str, identifier: str, max_attempts: int, window_seconds: int) -> None:
    """Raise HTTP 429 if `identifier` has exceeded `max_attempts` within `window_seconds`."""
    key = f"ratelimit:{bucket}:{identifier}"
    redis_client = _get_redis()
    if redis_client is not None:
        allowed = await _check_redis(redis_client, key, max_attempts=max_attempts, window_seconds=window_seconds)
    else:
        allowed = await _check_memory(key, max_attempts=max_attempts, window_seconds=window_seconds)

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
        )


def client_identifier(request: Request) -> str:
    """Best-effort client identifier for rate limiting (IP address)."""
    if request.client:
        return request.client.host
    return "unknown"


async def rate_limit_login(request: Request) -> None:
    await check_rate_limit(
        bucket="login",
        identifier=client_identifier(request),
        max_attempts=settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS,
        window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
    )


async def rate_limit_forgot_password(request: Request) -> None:
    await check_rate_limit(
        bucket="forgot-password",
        identifier=client_identifier(request),
        max_attempts=settings.RATE_LIMIT_FORGOT_PASSWORD_MAX_ATTEMPTS,
        window_seconds=settings.RATE_LIMIT_FORGOT_PASSWORD_WINDOW_SECONDS,
    )


async def rate_limit_tv_public(request: Request) -> None:
    """Post-RC1 (short TV display URL): the public TV endpoint now accepts
    a short, guessable `short_code` alongside the existing high-entropy
    `public_slug` - see `models/tv_display_config.py`'s docstring. This
    throttles per-IP lookups to blunt brute-force enumeration of short
    codes without affecting a real TV's normal poll/reconnect traffic."""
    await check_rate_limit(
        bucket="tv-public",
        identifier=client_identifier(request),
        max_attempts=settings.RATE_LIMIT_TV_PUBLIC_MAX_ATTEMPTS,
        window_seconds=settings.RATE_LIMIT_TV_PUBLIC_WINDOW_SECONDS,
    )
