"""Tests for async-to-sync bridge utility."""

import asyncio

import pytest

from agent_layer.async_utils import run_async_in_sync


class TestRunAsyncInSync:
    def test_basic_coroutine(self):
        async def add(a, b):
            return a + b

        assert run_async_in_sync(add(1, 2)) == 3

    def test_async_sleep(self):
        async def delayed():
            await asyncio.sleep(0.01)
            return "done"

        assert run_async_in_sync(delayed()) == "done"

    def test_exception_propagation(self):
        async def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            run_async_in_sync(fail())

    def test_from_running_loop(self):
        """Test that it works even when called from an async context."""

        async def outer():
            async def inner():
                return 42

            return run_async_in_sync(inner())

        result = asyncio.run(outer())
        assert result == 42
