"""Rate limiting with pluggable stores."""

from __future__ import annotations

import time
from typing import Any, Callable

from agent_layer.types import RateLimitConfig, RateLimitResult


class MemoryStore:
    """In-memory sliding window counter store."""

    def __init__(self) -> None:
        self._windows: dict[str, tuple[int, float]] = {}  # key -> (count, expires_at)

    async def increment(self, key: str, window_ms: int) -> int:
        now = time.monotonic() * 1000
        entry = self._windows.get(key)

        if entry is None or now >= entry[1]:
            self._windows[key] = (1, now + window_ms)
            return 1

        count = entry[0] + 1
        self._windows[key] = (count, entry[1])
        return count

    async def get(self, key: str) -> int:
        now = time.monotonic() * 1000
        entry = self._windows.get(key)
        if entry is None or now >= entry[1]:
            return 0
        return entry[0]

    async def reset(self, key: str) -> None:
        self._windows.pop(key, None)

    def cleanup(self) -> None:
        """Remove expired entries."""
        now = time.monotonic() * 1000
        expired = [k for k, (_, exp) in self._windows.items() if now >= exp]
        for k in expired:
            del self._windows[k]


def create_rate_limiter(config: RateLimitConfig) -> Callable[[Any], Any]:
    """Create a rate limiter function that checks whether a request is allowed."""
    window_ms = config.window_ms
    store = config.store or MemoryStore()
    key_fn = config.key_fn or (lambda _req: "__global__")

    async def check_rate_limit(req: Any) -> RateLimitResult:
        key = key_fn(req)
        count = await store.increment(key, window_ms)
        allowed = count <= config.max
        remaining = max(0, config.max - count)

        result = RateLimitResult(
            allowed=allowed,
            limit=config.max,
            remaining=remaining,
            reset_ms=window_ms,
        )

        if not allowed:
            result.retry_after = window_ms // 1000 + (1 if window_ms % 1000 else 0)

        return result

    return check_rate_limit
