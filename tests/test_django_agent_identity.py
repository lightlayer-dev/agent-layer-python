"""Tests for Django agent identity middleware."""

from __future__ import annotations

import base64
import json
import time

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        ROOT_URLCONF="tests.test_django_adapters",
        MIDDLEWARE=[
            "agent_layer.django.errors.AgentErrorsMiddleware",
            "agent_layer.django.rate_limits.RateLimitsMiddleware",
        ],
        AGENT_LAYER_RATE_LIMIT={"max": 5},
        AGENT_IDENTITY={
            "trusted_issuers": ["https://auth.example.com"],
            "audience": ["https://api.example.com"],
        },
        SECRET_KEY="test-secret",
    )
    django.setup()

from django.http import JsonResponse
from django.test import RequestFactory

from agent_layer.django.agent_identity import AgentIdentityMiddleware


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


def _dummy_view(request):
    """Downstream view that returns agent identity info."""
    identity = getattr(request, "agent_identity", None)
    return JsonResponse({
        "agent_id": identity.agent_id if identity else None,
        "scopes": identity.scopes if identity else None,
        "delegated": identity.delegated if identity else None,
    })


factory = RequestFactory()


def _get_middleware(optional: bool = False):
    """Create a Django AgentIdentityMiddleware instance."""
    # Override the optional flag via settings
    if optional:
        settings.AGENT_IDENTITY = {
            "trusted_issuers": ["https://auth.example.com"],
            "audience": ["https://api.example.com"],
            "optional": True,
        }
    else:
        settings.AGENT_IDENTITY = {
            "trusted_issuers": ["https://auth.example.com"],
            "audience": ["https://api.example.com"],
        }
    return AgentIdentityMiddleware(_dummy_view)


# ── Tests ────────────────────────────────────────────────────────────────


def test_accepts_valid_token():
    mw = _get_middleware()
    token = _make_jwt(_VALID_PAYLOAD)
    request = factory.get("/test", HTTP_AUTHORIZATION=f"Bearer {token}")
    res = mw(request)
    assert res.status_code == 200
    body = json.loads(res.content)
    assert body["agent_id"] == "spiffe://example.com/agent/test-bot"
    assert "read:data" in body["scopes"]
    assert "write:data" in body["scopes"]


def test_rejects_missing_token():
    mw = _get_middleware()
    request = factory.get("/test")
    res = mw(request)
    assert res.status_code == 401


def test_rejects_untrusted_issuer():
    mw = _get_middleware()
    token = _make_jwt({**_VALID_PAYLOAD, "iss": "https://evil.com"})
    request = factory.get("/test", HTTP_AUTHORIZATION=f"Bearer {token}")
    res = mw(request)
    assert res.status_code == 403


def test_rejects_expired_token():
    mw = _get_middleware()
    token = _make_jwt({**_VALID_PAYLOAD, "exp": _NOW - 600})
    request = factory.get("/test", HTTP_AUTHORIZATION=f"Bearer {token}")
    res = mw(request)
    assert res.status_code in (401, 403)


def test_rejects_wrong_audience():
    mw = _get_middleware()
    token = _make_jwt({**_VALID_PAYLOAD, "aud": "https://wrong.example.com"})
    request = factory.get("/test", HTTP_AUTHORIZATION=f"Bearer {token}")
    res = mw(request)
    assert res.status_code == 403


def test_rejects_malformed_token():
    mw = _get_middleware()
    request = factory.get("/test", HTTP_AUTHORIZATION="Bearer not.a.jwt")
    res = mw(request)
    assert res.status_code in (401, 403)


def test_optional_allows_unauthenticated():
    mw = _get_middleware(optional=True)
    request = factory.get("/test")
    res = mw(request)
    assert res.status_code == 200
    body = json.loads(res.content)
    assert body["agent_id"] is None


def test_optional_attaches_claims_when_present():
    mw = _get_middleware(optional=True)
    token = _make_jwt(_VALID_PAYLOAD)
    request = factory.get("/test", HTTP_AUTHORIZATION=f"Bearer {token}")
    res = mw(request)
    assert res.status_code == 200
    body = json.loads(res.content)
    assert body["agent_id"] == "spiffe://example.com/agent/test-bot"


def test_optional_ignores_invalid_token():
    mw = _get_middleware(optional=True)
    token = _make_jwt({**_VALID_PAYLOAD, "iss": "https://evil.com"})
    request = factory.get("/test", HTTP_AUTHORIZATION=f"Bearer {token}")
    res = mw(request)
    assert res.status_code == 200
    body = json.loads(res.content)
    assert body["agent_id"] is None


def test_delegation_flag():
    mw = _get_middleware()
    payload = {**_VALID_PAYLOAD, "act": {"sub": "human@example.com"}}
    token = _make_jwt(payload)
    request = factory.get("/test", HTTP_AUTHORIZATION=f"Bearer {token}")
    res = mw(request)
    assert res.status_code == 200
    body = json.loads(res.content)
    assert body["delegated"] is True


def test_no_delegation_flag():
    mw = _get_middleware()
    token = _make_jwt(_VALID_PAYLOAD)
    request = factory.get("/test", HTTP_AUTHORIZATION=f"Bearer {token}")
    res = mw(request)
    body = json.loads(res.content)
    assert body["delegated"] is False
