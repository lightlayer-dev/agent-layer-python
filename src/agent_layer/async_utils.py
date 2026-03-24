"""Async-to-sync bridge utilities for sync frameworks (Flask, Django)."""

from __future__ import annotations

import asyncio
from typing import Any


def run_async_in_sync(coro: Any) -> Any:
    """Run an async coroutine from a synchronous context.

    Handles the case where an event loop may already be running
    (e.g., inside an async Django view or during testing).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)
