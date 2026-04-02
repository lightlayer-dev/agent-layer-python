"""Tests for the framework-agnostic identity handler."""

from __future__ import annotations

import base64
import json
import time

import pytest

from agent_layer.agent_identity import AgentIdentityConfig, AuthzContext, AgentAuthzPolicy
from agent_layer.identity_handler import (
    IdentityError,
    IdentitySuccess,
    extract_and_verify_token,
    handle_optional_identity,
    handle_require_identity,
)


def _make_jwt(claims: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.nosig"


NOW = int(time.time())
VALID_CONFIG = AgentIdentityConfig(
    trusted_issuers=["https://auth.example.com"],
    audience=["https://api.example.com"],
)

VALID_TOKEN = _make_jwt({
    "sub": "agent-123",
    "iss": "https://auth.example.com",
    "aud": "https://api.example.com",
    "exp": NOW + 600,
    "iat": NOW,
})

CONTEXT = AuthzContext(method="GET", path="/api/data", headers={})


@pytest.mark.asyncio
async def test_extract_and_verify_returns_claims():
    claims = await extract_and_verify_token(f"Bearer {VALID_TOKEN}", VALID_CONFIG)
    assert claims is not None
    assert claims.subject == "agent-123"


@pytest.mark.asyncio
async def test_extract_and_verify_returns_none_for_missing():
    result = await extract_and_verify_token(None, VALID_CONFIG)
    assert result is None


@pytest.mark.asyncio
async def test_require_identity_success():
    result = await handle_require_identity(f"Bearer {VALID_TOKEN}", VALID_CONFIG, CONTEXT)
    assert isinstance(result, IdentitySuccess)
    assert result.claims.subject == "agent-123"


@pytest.mark.asyncio
async def test_require_identity_missing_header():
    result = await handle_require_identity(None, VALID_CONFIG, CONTEXT)
    assert isinstance(result, IdentityError)
    assert result.status == 401
    assert result.envelope.code == "agent_identity_required"


@pytest.mark.asyncio
async def test_require_identity_malformed():
    result = await handle_require_identity("Bearer not-valid-jwt", VALID_CONFIG, CONTEXT)
    assert isinstance(result, IdentityError)
    assert result.status == 401
    assert result.envelope.code == "malformed_token"


@pytest.mark.asyncio
async def test_require_identity_expired():
    expired = _make_jwt({
        "sub": "agent-123",
        "iss": "https://auth.example.com",
        "aud": "https://api.example.com",
        "exp": NOW - 3700,
        "iat": NOW - 4000,
    })
    result = await handle_require_identity(f"Bearer {expired}", VALID_CONFIG, CONTEXT)
    assert isinstance(result, IdentityError)
    assert result.status == 401


@pytest.mark.asyncio
async def test_optional_identity_returns_claims():
    claims = await handle_optional_identity(f"Bearer {VALID_TOKEN}", VALID_CONFIG)
    assert claims is not None
    assert claims.subject == "agent-123"


@pytest.mark.asyncio
async def test_optional_identity_returns_none_for_missing():
    claims = await handle_optional_identity(None, VALID_CONFIG)
    assert claims is None


@pytest.mark.asyncio
async def test_optional_identity_returns_none_for_invalid():
    claims = await handle_optional_identity("Bearer garbage", VALID_CONFIG)
    assert claims is None
