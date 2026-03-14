"""Tests for rate limiting."""

import pytest

from agent_layer.rate_limit import MemoryStore, create_rate_limiter
from agent_layer.types import RateLimitConfig


class TestMemoryStore:
    @pytest.mark.asyncio
    async def test_increment(self):
        store = MemoryStore()
        assert await store.increment("k", 60000) == 1
        assert await store.increment("k", 60000) == 2

    @pytest.mark.asyncio
    async def test_get(self):
        store = MemoryStore()
        assert await store.get("k") == 0
        await store.increment("k", 60000)
        assert await store.get("k") == 1

    @pytest.mark.asyncio
    async def test_reset(self):
        store = MemoryStore()
        await store.increment("k", 60000)
        await store.reset("k")
        assert await store.get("k") == 0


class TestCreateRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_within_limit(self):
        check = create_rate_limiter(RateLimitConfig(max=3))
        result = await check(None)
        assert result.allowed is True
        assert result.remaining == 2

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        check = create_rate_limiter(RateLimitConfig(max=1))
        await check(None)
        result = await check(None)
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after is not None

    @pytest.mark.asyncio
    async def test_custom_key_fn(self):
        check = create_rate_limiter(RateLimitConfig(max=1, key_fn=lambda r: r))
        r1 = await check("user-a")
        assert r1.allowed is True
        r2 = await check("user-b")
        assert r2.allowed is True  # Different key
        r3 = await check("user-a")
        assert r3.allowed is False  # Same key, over limit
