"""Tests for the framework-agnostic OAuth2 middleware handler."""

from __future__ import annotations

import base64
import json
import time

import pytest

from agent_layer.oauth2_handler import (
    OAuth2MiddlewareConfig,
    OAuth2ValidationFailure,
    OAuth2ValidationSuccess,
    handle_oauth2,
)
from agent_layer.oauth2 import OAuth2Config, DecodedAccessToken, TokenValidationResult


OAUTH2_CONFIG = OAuth2Config(
    client_id="test-client",
    authorization_endpoint="https://auth.example.com/authorize",
    token_endpoint="https://auth.example.com/token",
    redirect_uri="https://app.example.com/callback",
    issuer="https://auth.example.com",
    audience="https://api.example.com",
    scopes={"read:data": "Read data", "write:data": "Write data"},
)

MW_CONFIG = OAuth2MiddlewareConfig(
    oauth2=OAUTH2_CONFIG,
    required_scopes=["read:data"],
)


def _make_jwt(claims: dict) -> str:
    """Create a fake JWT (no signature verification in tests)."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.nosig"


NOW = int(time.time())


def _valid_token(scopes: str = "read:data write:data") -> str:
    return _make_jwt({
        "sub": "agent-123",
        "iss": "https://auth.example.com",
        "aud": "https://api.example.com",
        "exp": NOW + 600,
        "iat": NOW,
        "scope": scopes,
    })


@pytest.mark.asyncio
async def test_passes_with_valid_token():
    result = await handle_oauth2(f"Bearer {_valid_token()}", MW_CONFIG)
    assert isinstance(result, OAuth2ValidationSuccess)
    assert result.passed is True
    assert result.token.sub == "agent-123"


@pytest.mark.asyncio
async def test_returns_401_when_no_header():
    result = await handle_oauth2(None, MW_CONFIG)
    assert isinstance(result, OAuth2ValidationFailure)
    assert result.passed is False
    assert result.status == 401
    assert "Bearer" in result.www_authenticate
    assert result.envelope.code == "authentication_required"


@pytest.mark.asyncio
async def test_returns_401_for_expired_token():
    expired = _make_jwt({
        "sub": "agent-123",
        "iss": "https://auth.example.com",
        "aud": "https://api.example.com",
        "exp": NOW - 100,
    })
    result = await handle_oauth2(f"Bearer {expired}", MW_CONFIG)
    assert isinstance(result, OAuth2ValidationFailure)
    assert result.status == 401
    assert result.envelope.code == "invalid_token"


@pytest.mark.asyncio
async def test_returns_403_for_insufficient_scopes():
    config = OAuth2MiddlewareConfig(
        oauth2=OAUTH2_CONFIG,
        required_scopes=["admin"],
    )
    result = await handle_oauth2(f"Bearer {_valid_token('read:data')}", config)
    assert isinstance(result, OAuth2ValidationFailure)
    assert result.status == 403
    assert result.envelope.code == "insufficient_scope"
    assert "insufficient_scope" in result.www_authenticate


@pytest.mark.asyncio
async def test_returns_401_for_non_bearer():
    result = await handle_oauth2("Basic abc123", MW_CONFIG)
    assert isinstance(result, OAuth2ValidationFailure)
    assert result.status == 401


@pytest.mark.asyncio
async def test_custom_validator():
    async def custom_validator(token: str) -> TokenValidationResult:
        return TokenValidationResult(
            valid=True,
            token=DecodedAccessToken(
                sub="custom-agent",
                iss="https://auth.example.com",
                exp=NOW + 600,
                scopes=["read:data"],
                claims={},
            ),
        )

    config = OAuth2MiddlewareConfig(
        oauth2=OAUTH2_CONFIG,
        custom_validator=custom_validator,
    )
    result = await handle_oauth2("Bearer any-token", config)
    assert isinstance(result, OAuth2ValidationSuccess)
    assert result.token.sub == "custom-agent"


@pytest.mark.asyncio
async def test_includes_docs_url_on_401():
    result = await handle_oauth2(None, MW_CONFIG)
    assert isinstance(result, OAuth2ValidationFailure)
    assert result.envelope.docs_url == "https://auth.example.com/authorize"


@pytest.mark.asyncio
async def test_scope_in_www_authenticate():
    result = await handle_oauth2(None, MW_CONFIG)
    assert isinstance(result, OAuth2ValidationFailure)
    assert "read:data" in result.www_authenticate
