"""Tests for FastAPI agent identity middleware."""

from __future__ import annotations

import base64
import json
import time

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_layer.agent_identity import AgentIdentityConfig
from agent_layer.fastapi.agent_identity import (
    agent_identity_middleware,
    agent_identity_optional_middleware,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.fakesig"


_NOW = int(time.time())

_VALID_PAYLOAD = {
    "iss": "https://auth.example.com",
    "sub": "spiffe://example.com/agent/test-bot",
    "aud": "https://api.example.com",
    "exp": _NOW + 600,
    "iat": _NOW,
    "scope": "read:data write:data",
}

_BASE_CONFIG = AgentIdentityConfig(
    trusted_issuers=["https://auth.example.com"],
    audience=["https://api.example.com"],
)


def _make_app(config: AgentIdentityConfig | None = None, optional: bool = False) -> FastAPI:
    app = FastAPI()
    cfg = config or _BASE_CONFIG

    if optional:
        mw = agent_identity_optional_middleware(cfg)
    else:
        mw = agent_identity_middleware(cfg)

    app.middleware("http")(mw)

    @app.get("/test")
    async def test_endpoint(request: Request):
        identity = getattr(request.state, "agent_identity", None)
        return JSONResponse({
            "agent_id": identity.agent_id if identity else None,
            "scopes": identity.scopes if identity else None,
            "delegated": identity.delegated if identity else None,
        })

    return app


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_accepts_valid_token():
    app = _make_app()
    token = _make_jwt(_VALID_PAYLOAD)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["agent_id"] == "spiffe://example.com/agent/test-bot"
    assert "read:data" in body["scopes"]
    assert "write:data" in body["scopes"]


@pytest.mark.asyncio
async def test_rejects_missing_token():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/test")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_rejects_untrusted_issuer():
    app = _make_app()
    token = _make_jwt({**_VALID_PAYLOAD, "iss": "https://evil.com"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_rejects_expired_token():
    app = _make_app()
    token = _make_jwt({**_VALID_PAYLOAD, "exp": _NOW - 600})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_rejects_wrong_audience():
    app = _make_app()
    token = _make_jwt({**_VALID_PAYLOAD, "aud": "https://wrong.example.com"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_rejects_malformed_token():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/test", headers={"Authorization": "Bearer not.a.jwt"})
    # Should reject (might be 401 or 403 depending on decode failure)
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_optional_allows_unauthenticated():
    app = _make_app(optional=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/test")
    assert res.status_code == 200
    body = res.json()
    assert body["agent_id"] is None


@pytest.mark.asyncio
async def test_optional_attaches_claims_when_present():
    app = _make_app(optional=True)
    token = _make_jwt(_VALID_PAYLOAD)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["agent_id"] == "spiffe://example.com/agent/test-bot"


@pytest.mark.asyncio
async def test_optional_ignores_invalid_token():
    app = _make_app(optional=True)
    token = _make_jwt({**_VALID_PAYLOAD, "iss": "https://evil.com"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["agent_id"] is None


@pytest.mark.asyncio
async def test_delegation_flag():
    app = _make_app()
    payload = {**_VALID_PAYLOAD, "act": {"sub": "human@example.com"}}
    token = _make_jwt(payload)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["delegated"] is True


@pytest.mark.asyncio
async def test_no_delegation_flag():
    app = _make_app()
    token = _make_jwt(_VALID_PAYLOAD)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/test", headers={"Authorization": f"Bearer {token}"})
    body = res.json()
    assert body["delegated"] is False
