"""Shared utilities for checks."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import httpx

from ..types import ScanConfig


async def safe_fetch(
    url: str,
    config: ScanConfig,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> httpx.Response | None:
    """Safe HTTP fetch with timeout and error handling."""
    try:
        hdrs = {"User-Agent": config.user_agent}
        if headers:
            hdrs.update(headers)
        async with httpx.AsyncClient(follow_redirects=True, timeout=config.timeout_s) as client:
            return await client.request(method, url, headers=hdrs)
    except Exception:
        return None


def resolve_url(base: str, path: str) -> str:
    """Resolve a path against the base URL."""
    parsed = urlparse(base)
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
