from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from urllib.parse import urlparse


MIN_REQUEST_INTERVAL_SECONDS = float(os.getenv("CRAWLER_DOMAIN_DELAY_SECONDS", "1.0"))
_domain_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_domain_last_request_at: dict[str, float] = {}


def domain_key(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


async def wait_for_domain_slot(url: str) -> None:
    key = domain_key(url)
    if not key:
        return
    lock = _domain_locks[key]
    async with lock:
        now = time.monotonic()
        last = _domain_last_request_at.get(key)
        if last is not None:
            delay = MIN_REQUEST_INTERVAL_SECONDS - (now - last)
            if delay > 0:
                await asyncio.sleep(delay)
        _domain_last_request_at[key] = time.monotonic()
