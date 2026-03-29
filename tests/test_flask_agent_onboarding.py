"""Tests for Flask agent-onboarding blueprint and auth middleware."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from flask import Flask

from agent_layer.agent_onboarding import OnboardingConfig
from agent_layer.flask.agent_onboarding import (
    agent_onboarding_auth_middleware,
    agent_onboarding_blueprint,
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


@pytest.fixture
def app(config: OnboardingConfig) -> Flask:
    fa = Flask(__name__)
    fa.register_blueprint(agent_onboarding_blueprint(config))
    return fa


@pytest.fixture
def app_with_auth(config: OnboardingConfig) -> Flask:
    fa = Flask(__name__)
    fa.register_blueprint(agent_onboarding_blueprint(config))
    fa.before_request(agent_onboarding_auth_middleware(config))

    @fa.route("/protected")
    def protected():
        return {"ok": True}

    @fa.route("/llms.txt")
    def llms_txt():
        return "llms"

    return fa


def test_register_success(app: Flask) -> None:
    mock_resp = _mock_webhook_response({"api_key": "key-abc", "status": "provisioned"})

    with patch("agent_layer.agent_onboarding.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        with app.test_client() as client:
            resp = client.post("/agent/register", json=_registration_body())

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "provisioned"


def test_register_missing_fields(app: Flask) -> None:
    with app.test_client() as client:
        resp = client.post("/agent/register", json={"agent_id": ""})
    assert resp.status_code == 400


def test_auth_middleware_blocks_unauthenticated(app_with_auth: Flask) -> None:
    with app_with_auth.test_client() as client:
        resp = client.get("/protected")
    assert resp.status_code == 401


def test_auth_middleware_passes_with_auth_header(app_with_auth: Flask) -> None:
    with app_with_auth.test_client() as client:
        resp = client.get("/protected", headers={"Authorization": "Bearer tok-123"})
    assert resp.status_code == 200


def test_auth_middleware_passes_with_api_key(app_with_auth: Flask) -> None:
    with app_with_auth.test_client() as client:
        resp = client.get("/protected", headers={"X-API-Key": "key-123"})
    assert resp.status_code == 200


def test_auth_middleware_allows_exempt_paths(app_with_auth: Flask) -> None:
    with app_with_auth.test_client() as client:
        resp = client.get("/llms.txt")
        assert resp.status_code == 200


def test_register_blocked_provider() -> None:
    config = make_config(allowed_providers=["allowed-provider"])
    fa = Flask(__name__)
    fa.register_blueprint(agent_onboarding_blueprint(config))

    body = _registration_body()
    body["agent_provider"] = "blocked-provider"

    with fa.test_client() as client:
        resp = client.post("/agent/register", json=body)
    assert resp.status_code == 403
