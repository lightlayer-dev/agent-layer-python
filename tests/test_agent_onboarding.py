"""Tests for agent_layer.agent_onboarding — mirrors the TS test suite."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from agent_layer.agent_onboarding import (
    OnboardingConfig,
    RegistrationRequest,
    create_onboarding_handler,
    sign_webhook_payload,
    verify_webhook_signature,
)


# ── Test Helpers ─────────────────────────────────────────────────────────


def make_config(**overrides: object) -> OnboardingConfig:
    defaults = {"provisioning_webhook": "https://api.example.com/provision"}
    defaults.update(overrides)
    return OnboardingConfig(**defaults)  # type: ignore[arg-type]


def make_request(**overrides: object) -> RegistrationRequest:
    defaults = {
        "agent_id": "agent-123",
        "agent_name": "Test Agent",
        "agent_provider": "openai",
    }
    defaults.update(overrides)
    return RegistrationRequest(**defaults)  # type: ignore[arg-type]


PROVISIONED_RESPONSE = {
    "status": "provisioned",
    "credentials": {
        "type": "api_key",
        "token": "sk-test-abc123",
        "header": "X-API-Key",
    },
}

REJECTED_RESPONSE = {
    "status": "rejected",
    "reason": "Agent not approved",
}


def _mock_httpx_post(response_json: dict, status_code: int = 200) -> AsyncMock:
    """Create a mock for httpx.AsyncClient.post."""
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.json.return_value = response_json
    mock_response.text = json.dumps(response_json)

    mock_post = AsyncMock(return_value=mock_response)
    return mock_post


# ── Tests ────────────────────────────────────────────────────────────────


class TestHandleRegister:
    @pytest.mark.asyncio
    async def test_registers_agent_successfully(self) -> None:
        handler = create_onboarding_handler(make_config())
        mock_post = _mock_httpx_post(PROVISIONED_RESPONSE)

        with patch("agent_layer.agent_onboarding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await handler.handle_register(make_request(), "1.2.3.4")

        assert result.status == 200
        assert result.body == PROVISIONED_RESPONSE
        mock_post.assert_called_once()

        call_kwargs = mock_post.call_args
        body = json.loads(call_kwargs.kwargs.get("content", call_kwargs[1].get("content", "")))
        assert body["agent_id"] == "agent-123"
        assert body["agent_name"] == "Test Agent"
        assert body["agent_provider"] == "openai"
        assert body["identity_verified"] is False
        assert body["request_ip"] == "1.2.3.4"
        assert "timestamp" in body

    @pytest.mark.asyncio
    async def test_sends_webhook_signature(self) -> None:
        handler = create_onboarding_handler(make_config(webhook_secret="test-secret"))
        mock_post = _mock_httpx_post(PROVISIONED_RESPONSE)

        with patch("agent_layer.agent_onboarding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await handler.handle_register(make_request(), "1.2.3.4")

        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
        sig = headers.get("X-Webhook-Signature", "")
        assert sig.startswith("sha256=")
        assert len(sig) == 71  # "sha256=" + 64 hex chars

    @pytest.mark.asyncio
    async def test_rejects_missing_agent_id(self) -> None:
        handler = create_onboarding_handler(make_config())
        result = await handler.handle_register(make_request(agent_id=""), "1.2.3.4")
        assert result.status == 400
        assert result.body["code"] == "missing_field"

    @pytest.mark.asyncio
    async def test_rejects_missing_agent_name(self) -> None:
        handler = create_onboarding_handler(make_config())
        result = await handler.handle_register(make_request(agent_name=""), "1.2.3.4")
        assert result.status == 400
        assert result.body["code"] == "missing_field"

    @pytest.mark.asyncio
    async def test_rejects_missing_agent_provider(self) -> None:
        handler = create_onboarding_handler(make_config())
        result = await handler.handle_register(make_request(agent_provider=""), "1.2.3.4")
        assert result.status == 400
        assert result.body["code"] == "missing_field"

    @pytest.mark.asyncio
    async def test_rejects_when_identity_required_but_not_provided(self) -> None:
        handler = create_onboarding_handler(make_config(require_identity=True))
        result = await handler.handle_register(make_request(), "1.2.3.4")
        assert result.status == 400
        assert result.body["code"] == "identity_required"

    @pytest.mark.asyncio
    async def test_accepts_when_identity_required_and_provided(self) -> None:
        handler = create_onboarding_handler(make_config(require_identity=True))
        mock_post = _mock_httpx_post(PROVISIONED_RESPONSE)

        with patch("agent_layer.agent_onboarding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await handler.handle_register(make_request(identity_token="eyJ..."), "1.2.3.4")

        assert result.status == 200
        call_kwargs = mock_post.call_args
        body = json.loads(call_kwargs.kwargs.get("content", call_kwargs[1].get("content", "")))
        assert body["identity_verified"] is True

    @pytest.mark.asyncio
    async def test_rejects_disallowed_provider(self) -> None:
        handler = create_onboarding_handler(make_config(allowed_providers=["anthropic", "google"]))
        result = await handler.handle_register(make_request(), "1.2.3.4")
        assert result.status == 403
        assert result.body["code"] == "provider_not_allowed"

    @pytest.mark.asyncio
    async def test_allows_provider_case_insensitive(self) -> None:
        handler = create_onboarding_handler(make_config(allowed_providers=["OpenAI"]))
        mock_post = _mock_httpx_post(PROVISIONED_RESPONSE)

        with patch("agent_layer.agent_onboarding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await handler.handle_register(make_request(), "1.2.3.4")

        assert result.status == 200

    @pytest.mark.asyncio
    async def test_rate_limits_per_ip(self) -> None:
        handler = create_onboarding_handler(
            make_config(rate_limit_max=2, rate_limit_window_ms=60_000)
        )
        mock_post = _mock_httpx_post(PROVISIONED_RESPONSE)

        with patch("agent_layer.agent_onboarding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            r1 = await handler.handle_register(make_request(), "1.2.3.4")
            r2 = await handler.handle_register(make_request(), "1.2.3.4")
            r3 = await handler.handle_register(make_request(), "1.2.3.4")

        assert r1.status == 200
        assert r2.status == 200
        assert r3.status == 429
        assert r3.body["code"] == "rate_limit_exceeded"

    @pytest.mark.asyncio
    async def test_rate_limits_per_ip_independently(self) -> None:
        handler = create_onboarding_handler(
            make_config(rate_limit_max=1, rate_limit_window_ms=60_000)
        )
        mock_post = _mock_httpx_post(PROVISIONED_RESPONSE)

        with patch("agent_layer.agent_onboarding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            r1 = await handler.handle_register(make_request(), "1.2.3.4")
            r2 = await handler.handle_register(make_request(), "5.6.7.8")

        assert r1.status == 200
        assert r2.status == 200

    @pytest.mark.asyncio
    async def test_returns_403_for_rejected(self) -> None:
        handler = create_onboarding_handler(make_config())
        mock_post = _mock_httpx_post(REJECTED_RESPONSE)

        with patch("agent_layer.agent_onboarding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await handler.handle_register(make_request(), "1.2.3.4")

        assert result.status == 403
        assert result.body == REJECTED_RESPONSE

    @pytest.mark.asyncio
    async def test_returns_502_when_webhook_fails(self) -> None:
        handler = create_onboarding_handler(make_config())
        mock_post = _mock_httpx_post({"error": "Internal"}, status_code=500)

        with patch("agent_layer.agent_onboarding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await handler.handle_register(make_request(), "1.2.3.4")

        assert result.status == 502
        assert result.body["code"] == "webhook_error"

    @pytest.mark.asyncio
    async def test_returns_502_when_webhook_throws(self) -> None:
        handler = create_onboarding_handler(make_config())

        with patch("agent_layer.agent_onboarding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=RuntimeError("network error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await handler.handle_register(make_request(), "1.2.3.4")

        assert result.status == 502
        assert result.body["code"] == "webhook_error"


class TestShouldReturn401:
    def setup_method(self) -> None:
        self.handler = create_onboarding_handler(make_config())

    def test_true_for_unauthenticated_regular_path(self) -> None:
        assert self.handler.should_return_401("/api/data", {}) is True

    def test_false_with_authorization_header(self) -> None:
        assert (
            self.handler.should_return_401("/api/data", {"authorization": "Bearer token"}) is False
        )

    def test_false_with_api_key_header(self) -> None:
        assert self.handler.should_return_401("/api/data", {"x-api-key": "key123"}) is False

    def test_false_for_well_known(self) -> None:
        assert self.handler.should_return_401("/.well-known/agent.json", {}) is False

    def test_false_for_llms_txt(self) -> None:
        assert self.handler.should_return_401("/llms.txt", {}) is False

    def test_false_for_llms_full_txt(self) -> None:
        assert self.handler.should_return_401("/llms-full.txt", {}) is False

    def test_false_for_agents_txt(self) -> None:
        assert self.handler.should_return_401("/agents.txt", {}) is False

    def test_false_for_robots_txt(self) -> None:
        assert self.handler.should_return_401("/robots.txt", {}) is False

    def test_false_for_agent_register(self) -> None:
        assert self.handler.should_return_401("/agent/register", {}) is False


class TestGetAuthRequiredResponse:
    def test_returns_standard_response(self) -> None:
        handler = create_onboarding_handler(make_config(auth_docs="https://docs.example.com/auth"))
        resp = handler.get_auth_required_response()

        assert resp["error"] == "auth_required"
        assert resp["register_url"] == "/agent/register"
        assert resp["auth_docs"] == "https://docs.example.com/auth"
        assert resp["supported_credential_types"] == [
            "api_key",
            "oauth2_client_credentials",
            "bearer",
        ]


class TestWebhookSignature:
    def test_produces_valid_hex_signature(self) -> None:
        sig = sign_webhook_payload('{"test":true}', "secret")
        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)

    def test_verifies_valid_signature(self) -> None:
        body = '{"agent_id":"test"}'
        secret = "my-secret"
        sig = f"sha256={sign_webhook_payload(body, secret)}"
        assert verify_webhook_signature(body, secret, sig) is True

    def test_rejects_invalid_signature(self) -> None:
        assert verify_webhook_signature('{"test":true}', "secret", "sha256=bad") is False

    def test_rejects_wrong_prefix(self) -> None:
        body = '{"test":true}'
        sig = sign_webhook_payload(body, "secret")
        assert verify_webhook_signature(body, "secret", sig) is False
