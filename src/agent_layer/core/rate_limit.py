"""
Rate limiting — In-memory sliding window counter.

Provides a pluggable rate limiter with an in-memory store that
automatically cleans up expired entries.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class RateLimitStore(Protocol):
    """Protocol for rate limit storage backends."""

    async def increment(self, key: str, window_ms: int) -> int: ...
    async def get(self, key: str) -> int: ...
    async def reset(self, key: str) -> None: ...


@dataclass
class _WindowEntry:
    count: int
    expires_at: float


class MemoryStore:
    """In-memory sliding window counter store.

    Entries are automatically cleaned up when they expire.
    """

    def __init__(self) -> None:
        self._windows: dict[str, _WindowEntry] = {}

    async def increment(self, key: str, window_ms: int) -> int:
        now = time.time() * 1000  # ms
        entry = self._windows.get(key)

        if entry is None or now >= entry.expires_at:
            self._windows[key] = _WindowEntry(count=1, expires_at=now + window_ms)
            return 1

        entry.count += 1
        return entry.count

    async def get(self, key: str) -> int:
        now = time.time() * 1000
        entry = self._windows.get(key)

        if entry is None or now >= entry.expires_at:
            return 0

        return entry.count

    async def reset(self, key: str) -> None:
        self._windows.pop(key, None)

    def cleanup(self) -> None:
        """Remove expired entries. Useful for long-running processes."""
        now = time.time() * 1000
        expired = [k for k, v in self._windows.items() if now >= v.expires_at]
        for k in expired:
            del self._windows[k]


@dataclass
class RateLimitConfig:
    """Configuration for the rate limiter."""

    max: int
    """Maximum number of requests per window."""

    window_ms: int = 60_000
    """Window size in milliseconds. Default: 60,000 (1 minute)."""

    key_fn: Callable[[Any], str] = field(default_factory=lambda: lambda req: "__global__")
    """Key extractor function. Default: returns a fixed key (global limit)."""

    store: MemoryStore | None = None
    """Pluggable store. Default: MemoryStore."""


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    limit: int
    remaining: int
    reset_ms: int
    retry_after: int | None = None


def create_rate_limiter(config: RateLimitConfig) -> Callable[[Any], Any]:
    """Create a rate limiter with the given configuration.

    Returns an async function that checks whether a request is allowed.

    Usage:
        check = create_rate_limiter(RateLimitConfig(max=100))
        result = await check(request)
        if not result.allowed:
            # Return 429
    """
    window_ms = config.window_ms
    store = config.store or MemoryStore()
    key_fn = config.key_fn

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
            result.retry_after = (window_ms + 999) // 1000  # ceil division

        return result

    return check_rate_limit
