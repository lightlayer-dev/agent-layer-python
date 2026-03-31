"""Tests for Flask agent identity middleware."""

from __future__ import annotations

import base64
import json
import time

from flask import Flask, g, jsonify

from agent_layer.agent_identity import AgentIdentityConfig
from agent_layer.flask.agent_identity import agent_identity_middleware


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


def _make_app(config: AgentIdentityConfig | None = None, optional: bool = False) -> Flask:
    app = Flask(__name__)
    cfg = config or _BASE_CONFIG
    agent_identity_middleware(app, cfg, optional=optional)

    @app.route("/test")
    def test_endpoint():
        identity = getattr(g, "agent_identity", None)
        return jsonify({
            "agent_id": identity.agent_id if identity else None,
            "scopes": identity.scopes if identity else None,
            "delegated": identity.delegated if identity else None,
        })

    return app


# ── Tests ────────────────────────────────────────────────────────────────


def test_accepts_valid_token():
    client = _make_app().test_client()
    token = _make_jwt(_VALID_PAYLOAD)
    res = client.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["agent_id"] == "spiffe://example.com/agent/test-bot"
    assert "read:data" in body["scopes"]
    assert "write:data" in body["scopes"]


def test_rejects_missing_token():
    client = _make_app().test_client()
    res = client.get("/test")
    assert res.status_code == 401


def test_rejects_untrusted_issuer():
    client = _make_app().test_client()
    token = _make_jwt({**_VALID_PAYLOAD, "iss": "https://evil.com"})
    res = client.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_rejects_expired_token():
    client = _make_app().test_client()
    token = _make_jwt({**_VALID_PAYLOAD, "exp": _NOW - 600})
    res = client.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code in (401, 403)


def test_rejects_wrong_audience():
    client = _make_app().test_client()
    token = _make_jwt({**_VALID_PAYLOAD, "aud": "https://wrong.example.com"})
    res = client.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_rejects_malformed_token():
    client = _make_app().test_client()
    res = client.get("/test", headers={"Authorization": "Bearer not.a.jwt"})
    assert res.status_code in (401, 403)


def test_optional_allows_unauthenticated():
    client = _make_app(optional=True).test_client()
    res = client.get("/test")
    assert res.status_code == 200
    body = res.get_json()
    assert body["agent_id"] is None


def test_optional_attaches_claims_when_present():
    client = _make_app(optional=True).test_client()
    token = _make_jwt(_VALID_PAYLOAD)
    res = client.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["agent_id"] == "spiffe://example.com/agent/test-bot"


def test_optional_ignores_invalid_token():
    client = _make_app(optional=True).test_client()
    token = _make_jwt({**_VALID_PAYLOAD, "iss": "https://evil.com"})
    res = client.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["agent_id"] is None


def test_delegation_flag():
    client = _make_app().test_client()
    payload = {**_VALID_PAYLOAD, "act": {"sub": "human@example.com"}}
    token = _make_jwt(payload)
    res = client.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["delegated"] is True


def test_no_delegation_flag():
    client = _make_app().test_client()
    token = _make_jwt(_VALID_PAYLOAD)
    res = client.get("/test", headers={"Authorization": f"Bearer {token}"})
    body = res.get_json()
    assert body["delegated"] is False
