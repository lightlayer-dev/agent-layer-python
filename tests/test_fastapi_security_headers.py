"""Tests for FastAPI security_headers middleware."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agent_layer.fastapi.security_headers import security_headers_middleware
from agent_layer.security_headers import SecurityHeadersConfig


@pytest.fixture
def app() -> FastAPI:
    fa = FastAPI()
    security_headers_middleware(fa)

    @fa.get("/test")
    async def test_endpoint() -> dict[str, bool]:
        return {"ok": True}

    return fa


@pytest.mark.asyncio
async def test_default_security_headers(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/test")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["content-security-policy"] == "default-src 'self'"


@pytest.mark.asyncio
async def test_custom_security_headers() -> None:
    fa = FastAPI()
    config = SecurityHeadersConfig(frame_options="SAMEORIGIN", csp=False)
    security_headers_middleware(fa, config)

    @fa.get("/test")
    async def test_endpoint() -> dict[str, bool]:
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=fa), base_url="http://test") as client:
        resp = await client.get("/test")
    assert resp.headers["x-frame-options"] == "SAMEORIGIN"
    assert "content-security-policy" not in resp.headers
