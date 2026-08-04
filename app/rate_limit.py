from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from urllib.parse import urlparse


MIN_REQUEST_INTERVAL_SECONDS = float(os.getenv("CRAWLER_DOMAIN_DELAY_SECONDS", "1.0"))
DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 30
MAX_RATE_LIMIT_COOLDOWN_SECONDS = 300
_domain_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_domain_last_request_at: dict[str, float] = {}
_domain_cooldown_until: dict[str, float] = {}
_domain_rate_limit_streak: dict[str, int] = {}


def domain_key(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def reset_domain_rate_limits() -> None:
    """Clear transient cooldown state; used by isolated tests and local restarts."""
    _domain_cooldown_until.clear()
    _domain_rate_limit_streak.clear()


def record_domain_rate_limit(url: str, retry_after_seconds: int | None = None) -> int:
    key = domain_key(url)
    if not key:
        return 0
    now = time.monotonic()
    streak = _domain_rate_limit_streak.get(key, 0) + 1
    _domain_rate_limit_streak[key] = streak
    delay = retry_after_seconds if retry_after_seconds and retry_after_seconds > 0 else min(
        DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS * (2 ** (streak - 1)),
        MAX_RATE_LIMIT_COOLDOWN_SECONDS,
    )
    _domain_cooldown_until[key] = max(_domain_cooldown_until.get(key, 0.0), now + delay)
    return delay


def record_domain_success(url: str) -> None:
    key = domain_key(url)
    if key:
        _domain_rate_limit_streak.pop(key, None)


def domain_cooldown_remaining(url: str) -> float:
    key = domain_key(url)
    if not key:
        return 0.0
    remaining = _domain_cooldown_until.get(key, 0.0) - time.monotonic()
    return max(0.0, remaining)


async def wait_for_domain_slot(url: str) -> None:
    key = domain_key(url)
    if not key:
        return
    lock = _domain_locks[key]
    async with lock:
        cooldown = domain_cooldown_remaining(url)
        if cooldown > 0:
            await asyncio.sleep(cooldown)
        now = time.monotonic()
        last = _domain_last_request_at.get(key)
        if last is not None:
            delay = MIN_REQUEST_INTERVAL_SECONDS - (now - last)
            if delay > 0:
                await asyncio.sleep(delay)
        _domain_last_request_at[key] = time.monotonic()
