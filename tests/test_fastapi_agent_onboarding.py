"""Tests for FastAPI agent-onboarding routes and auth middleware."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agent_layer.agent_onboarding import OnboardingConfig
from agent_layer.fastapi.agent_onboarding import (
    agent_onboarding_auth_middleware,
    agent_onboarding_routes,
)


def make_config(**overrides) -> OnboardingConfig:
    defaults = {"provisioning_webhook": "https://api.example.com/provision"}
    defaults.update(overrides)
    return OnboardingConfig(**defaults)


@pytest.fixture
def config() -> OnboardingConfig:
    return make_config()


@pytest.fixture
def app(config: OnboardingConfig) -> FastAPI:
    fa = FastAPI()
    fa.include_router(agent_onboarding_routes(config))
    return fa


def _registration_body() -> dict:
    return {
        "agent_id": "agent-123",
        "agent_name": "TestBot",
        "agent_provider": "test-provider",
    }


def _mock_webhook_response(body: dict, status_code: int = 200):
    """Create a mock httpx response (non-async .json())."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = json.dumps(body)
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_register_success(app: FastAPI) -> None:
    mock_resp = _mock_webhook_response({"api_key": "key-abc", "status": "provisioned"})

    with patch("agent_layer.agent_onboarding.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/agent/register", json=_registration_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "provisioned"


@pytest.mark.asyncio
async def test_register_missing_fields(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/agent/register", json={"agent_id": ""})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_auth_middleware_blocks_unauthenticated() -> None:
    """Auth middleware blocks requests without credentials (always, since should_return_401 checks for auth headers)."""
    config = make_config()
    fa = FastAPI()
    fa.include_router(agent_onboarding_routes(config))
    fa.middleware("http")(agent_onboarding_auth_middleware(config))

    @fa.get("/protected")
    async def protected():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=fa), base_url="http://test") as client:
        resp = await client.get("/protected")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_middleware_passes_with_auth_header() -> None:
    """Auth middleware allows requests that have an Authorization header."""
    config = make_config()
    fa = FastAPI()
    fa.include_router(agent_onboarding_routes(config))
    fa.middleware("http")(agent_onboarding_auth_middleware(config))

    @fa.get("/protected")
    async def protected():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=fa), base_url="http://test") as client:
        resp = await client.get("/protected", headers={"Authorization": "Bearer tok-123"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_middleware_passes_with_api_key() -> None:
    """Auth middleware allows requests that have an X-API-Key header."""
    config = make_config()
    fa = FastAPI()
    fa.include_router(agent_onboarding_routes(config))
    fa.middleware("http")(agent_onboarding_auth_middleware(config))

    @fa.get("/protected")
    async def protected():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=fa), base_url="http://test") as client:
        resp = await client.get("/protected", headers={"X-API-Key": "key-123"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_middleware_allows_exempt_paths() -> None:
    config = make_config()
    fa = FastAPI()
    fa.include_router(agent_onboarding_routes(config))
    fa.middleware("http")(agent_onboarding_auth_middleware(config))

    @fa.get("/llms.txt")
    async def llms_txt():
        return "llms"

    @fa.get("/robots.txt")
    async def robots_txt():
        return "robots"

    async with AsyncClient(transport=ASGITransport(app=fa), base_url="http://test") as client:
        resp_llms = await client.get("/llms.txt")
        resp_robots = await client.get("/robots.txt")

    assert resp_llms.status_code == 200
    assert resp_robots.status_code == 200


@pytest.mark.asyncio
async def test_register_with_provider_allowlist() -> None:
    config = make_config(allowed_providers=["allowed-provider"])
    fa = FastAPI()
    fa.include_router(agent_onboarding_routes(config))

    body = _registration_body()
    body["agent_provider"] = "blocked-provider"

    async with AsyncClient(transport=ASGITransport(app=fa), base_url="http://test") as client:
        resp = await client.post("/agent/register", json=body)

    assert resp.status_code == 403
