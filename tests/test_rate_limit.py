"""Tests for rate limiting."""

import asyncio
import time

import pytest

from agent_layer.core.rate_limit import (
    MemoryStore,
    RateLimitConfig,
    create_rate_limiter,
)


class TestMemoryStore:
    @pytest.mark.asyncio
    async def test_increment(self):
        store = MemoryStore()
        count = await store.increment("key1", 60000)
        assert count == 1
        count = await store.increment("key1", 60000)
        assert count == 2

    @pytest.mark.asyncio
    async def test_get(self):
        store = MemoryStore()
        assert await store.get("key1") == 0
        await store.increment("key1", 60000)
        assert await store.get("key1") == 1

    @pytest.mark.asyncio
    async def test_reset(self):
        store = MemoryStore()
        await store.increment("key1", 60000)
        await store.reset("key1")
        assert await store.get("key1") == 0

    @pytest.mark.asyncio
    async def test_expired_entry(self):
        store = MemoryStore()
        # Use a very short window
        await store.increment("key1", 1)  # 1ms window
        await asyncio.sleep(0.01)  # Wait 10ms
        assert await store.get("key1") == 0

    @pytest.mark.asyncio
    async def test_expired_resets_on_increment(self):
        store = MemoryStore()
        await store.increment("key1", 1)
        await asyncio.sleep(0.01)
        count = await store.increment("key1", 60000)
        assert count == 1  # Reset after expiry

    @pytest.mark.asyncio
    async def test_cleanup_no_error(self):
        store = MemoryStore()
        await store.increment("key1", 60000)
        store.cleanup()  # Should not error on non-expired
        assert await store.get("key1") == 1

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired(self):
        store = MemoryStore()
        await store.increment("key1", 1)  # 1ms window
        await asyncio.sleep(0.01)
        store.cleanup()
        assert await store.get("key1") == 0

    @pytest.mark.asyncio
    async def test_separate_keys(self):
        store = MemoryStore()
        await store.increment("key1", 60000)
        await store.increment("key2", 60000)
        assert await store.get("key1") == 1
        assert await store.get("key2") == 1


class TestCreateRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        check = create_rate_limiter(RateLimitConfig(max=5))
        result = await check(None)
        assert result.allowed is True
        assert result.limit == 5
        assert result.remaining == 4

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        check = create_rate_limiter(RateLimitConfig(max=2))
        await check(None)  # 1
        await check(None)  # 2
        result = await check(None)  # 3 → blocked
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after is not None

    @pytest.mark.asyncio
    async def test_custom_key_fn(self):
        check = create_rate_limiter(
            RateLimitConfig(max=1, key_fn=lambda req: req)
        )
        r1 = await check("user1")
        r2 = await check("user2")
        assert r1.allowed is True
        assert r2.allowed is True
        # Same user again → blocked
        r3 = await check("user1")
        assert r3.allowed is False

    @pytest.mark.asyncio
    async def test_custom_window(self):
        check = create_rate_limiter(
            RateLimitConfig(max=1, window_ms=10)  # 10ms window
        )
        await check(None)  # 1 → allowed
        result = await check(None)  # 2 → blocked
        assert result.allowed is False
        await asyncio.sleep(0.02)  # Wait for window to expire
        result = await check(None)  # Should be allowed again
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_result_fields(self):
        check = create_rate_limiter(RateLimitConfig(max=10, window_ms=30000))
        result = await check(None)
        assert result.limit == 10
        assert result.remaining == 9
        assert result.reset_ms == 30000
        assert result.retry_after is None

    @pytest.mark.asyncio
    async def test_retry_after_calculation(self):
        check = create_rate_limiter(RateLimitConfig(max=1, window_ms=5000))
        await check(None)
        result = await check(None)
        assert result.retry_after == 5  # ceil(5000/1000)

    @pytest.mark.asyncio
    async def test_custom_store(self):
        store = MemoryStore()
        check = create_rate_limiter(RateLimitConfig(max=5, store=store))
        await check(None)
        assert await store.get("__global__") == 1
