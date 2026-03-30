"""Tests for Django agent-onboarding URL patterns and auth middleware."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        ROOT_URLCONF=__name__,
        MIDDLEWARE=[],
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    )
    django.setup()

import pytest
from django.test import AsyncRequestFactory, RequestFactory

from agent_layer.agent_onboarding import OnboardingConfig
from agent_layer.django.agent_onboarding import (
    AgentOnboardingAuthMiddleware,
    agent_onboarding_urlpatterns,
)


def make_config(**overrides) -> OnboardingConfig:
    defaults = {"provisioning_webhook": "https://api.example.com/provision"}
    defaults.update(overrides)
    return OnboardingConfig(**defaults)


def _registration_body() -> dict:
    return {
        "agent_id": "agent-123",
        "agent_name": "TestBot",
        "agent_provider": "test-provider",
    }


def _mock_webhook_response(body: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = json.dumps(body)
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture
def config() -> OnboardingConfig:
    return make_config()


@pytest.mark.asyncio
async def test_register_success(config: OnboardingConfig) -> None:
    urlpatterns = agent_onboarding_urlpatterns(config)
    view = urlpatterns[0].callback

    mock_resp = _mock_webhook_response({"api_key": "key-abc", "status": "provisioned"})

    factory = AsyncRequestFactory()
    request = factory.post(
        "/agent/register",
        data=json.dumps(_registration_body()),
        content_type="application/json",
    )

    with patch("agent_layer.agent_onboarding.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        resp = await view(request)

    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["status"] == "provisioned"


@pytest.mark.asyncio
async def test_register_missing_fields(config: OnboardingConfig) -> None:
    urlpatterns = agent_onboarding_urlpatterns(config)
    view = urlpatterns[0].callback

    factory = AsyncRequestFactory()
    request = factory.post(
        "/agent/register",
        data=json.dumps({"agent_id": ""}),
        content_type="application/json",
    )

    resp = await view(request)
    assert resp.status_code == 400


def _make_middleware(config: OnboardingConfig):
    def get_response(request):
        from django.http import JsonResponse

        return JsonResponse({"ok": True})

    return AgentOnboardingAuthMiddleware(get_response, config=config)


def test_auth_middleware_blocks_unauthenticated(config: OnboardingConfig) -> None:
    mw = _make_middleware(config)
    factory = RequestFactory()
    request = factory.get("/protected")
    resp = mw(request)
    assert resp.status_code == 401


def test_auth_middleware_passes_with_auth_header(config: OnboardingConfig) -> None:
    mw = _make_middleware(config)
    factory = RequestFactory()
    request = factory.get("/protected", HTTP_AUTHORIZATION="Bearer tok-123")
    resp = mw(request)
    assert resp.status_code == 200


def test_auth_middleware_passes_with_api_key(config: OnboardingConfig) -> None:
    mw = _make_middleware(config)
    factory = RequestFactory()
    request = factory.get("/protected", HTTP_X_API_KEY="key-123")
    resp = mw(request)
    assert resp.status_code == 200


def test_auth_middleware_allows_exempt_paths(config: OnboardingConfig) -> None:
    mw = _make_middleware(config)
    factory = RequestFactory()

    for path in ["/llms.txt", "/robots.txt", "/agents.txt", "/agent/register"]:
        request = factory.get(path)
        resp = mw(request)
        assert resp.status_code == 200, (
            f"Expected 200 for exempt path {path}, got {resp.status_code}"
        )


@pytest.mark.asyncio
async def test_register_blocked_provider() -> None:
    config = make_config(allowed_providers=["allowed-provider"])
    urlpatterns = agent_onboarding_urlpatterns(config)
    view = urlpatterns[0].callback

    body = _registration_body()
    body["agent_provider"] = "blocked-provider"

    factory = AsyncRequestFactory()
    request = factory.post(
        "/agent/register",
        data=json.dumps(body),
        content_type="application/json",
    )

    resp = await view(request)
    assert resp.status_code == 403
