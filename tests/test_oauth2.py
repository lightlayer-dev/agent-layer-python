"""Tests for OAuth2 module."""

import base64
import hashlib
import json
import time

import pytest

from agent_layer.core.oauth2 import (
    OAuth2Config,
    OAuth2MiddlewareConfig,
    build_authorization_url,
    build_oauth2_metadata,
    compute_code_challenge,
    extract_bearer_token,
    generate_code_verifier,
    generate_pkce,
    handle_oauth2,
    validate_access_token,
)


def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.sig"


class TestPKCE:
    def test_generate_verifier(self):
        v = generate_code_verifier()
        assert len(v) > 20

    def test_compute_challenge(self):
        v = "test_verifier"
        challenge = compute_code_challenge(v)
        # Verify it's base64url encoded SHA256
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(v.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        assert challenge == expected

    def test_generate_pkce_pair(self):
        pair = generate_pkce()
        assert pair.code_verifier
        assert pair.code_challenge
        # Verify the challenge matches the verifier
        assert pair.code_challenge == compute_code_challenge(pair.code_verifier)


class TestBuildAuthorizationUrl:
    def test_basic(self):
        config = OAuth2Config(
            client_id="client123",
            authorization_endpoint="https://auth.example.com/authorize",
        )
        url = build_authorization_url(config)
        assert "response_type=code" in url
        assert "client_id=client123" in url

    def test_with_pkce(self):
        config = OAuth2Config(
            client_id="c1",
            authorization_endpoint="https://auth.example.com/authorize",
        )
        pkce = generate_pkce()
        url = build_authorization_url(config, pkce=pkce)
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url

    def test_with_scopes(self):
        config = OAuth2Config(
            client_id="c1",
            authorization_endpoint="https://auth.example.com/authorize",
            scopes=["openid", "profile"],
        )
        url = build_authorization_url(config)
        assert "scope=openid+profile" in url

    def test_missing_endpoint_raises(self):
        config = OAuth2Config(client_id="c1")
        with pytest.raises(ValueError):
            build_authorization_url(config)


class TestExtractBearerToken:
    def test_valid(self):
        assert extract_bearer_token("Bearer abc123") == "abc123"

    def test_no_bearer(self):
        assert extract_bearer_token("Basic abc123") is None

    def test_none(self):
        assert extract_bearer_token(None) is None

    def test_empty(self):
        assert extract_bearer_token("") is None


class TestValidateAccessToken:
    def test_valid(self):
        token = _make_jwt({
            "sub": "user1", "iss": "auth.example.com",
            "aud": "api.example.com", "exp": time.time() + 3600,
            "scope": "read write",
        })
        config = OAuth2Config(
            client_id="c1", issuer="auth.example.com",
            audience="api.example.com",
        )
        result = validate_access_token(token, config)
        assert result.valid is True
        assert result.claims is not None
        assert result.claims.scopes == ["read", "write"]

    def test_expired(self):
        token = _make_jwt({"sub": "u", "exp": time.time() - 100})
        config = OAuth2Config(client_id="c1")
        result = validate_access_token(token, config)
        assert result.valid is False
        assert result.error == "token_expired"

    def test_invalid_issuer(self):
        token = _make_jwt({"sub": "u", "iss": "wrong", "exp": time.time() + 3600})
        config = OAuth2Config(client_id="c1", issuer="correct")
        result = validate_access_token(token, config)
        assert result.valid is False
        assert result.error == "invalid_issuer"

    def test_invalid_audience(self):
        token = _make_jwt({"sub": "u", "aud": "wrong", "exp": time.time() + 3600})
        config = OAuth2Config(client_id="c1", audience="correct")
        result = validate_access_token(token, config)
        assert result.valid is False
        assert result.error == "invalid_audience"

    def test_audience_array(self):
        token = _make_jwt({"sub": "u", "aud": ["api1", "api2"], "exp": time.time() + 3600})
        config = OAuth2Config(client_id="c1", audience="api1")
        result = validate_access_token(token, config)
        assert result.valid is True

    def test_scopes_array_format(self):
        token = _make_jwt({"sub": "u", "scopes": ["read", "write"], "exp": time.time() + 3600})
        config = OAuth2Config(client_id="c1")
        result = validate_access_token(token, config)
        assert result.valid is True
        assert result.claims.scopes == ["read", "write"]

    def test_scp_array_format(self):
        token = _make_jwt({"sub": "u", "scp": ["read"], "exp": time.time() + 3600})
        config = OAuth2Config(client_id="c1")
        result = validate_access_token(token, config)
        assert result.valid is True
        assert result.claims.scopes == ["read"]

    def test_malformed_token(self):
        config = OAuth2Config(client_id="c1")
        result = validate_access_token("not-a-jwt", config)
        assert result.valid is False
        assert result.error == "malformed_token"


class TestBuildOAuth2Metadata:
    def test_basic(self):
        metadata = build_oauth2_metadata(
            issuer="https://auth.example.com",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
        )
        assert metadata["issuer"] == "https://auth.example.com"
        assert metadata["authorization_endpoint"] == "https://auth.example.com/authorize"
        assert "S256" in metadata["code_challenge_methods_supported"]

    def test_with_scopes(self):
        metadata = build_oauth2_metadata(
            issuer="https://auth.example.com",
            scopes=["openid", "profile"],
        )
        assert metadata["scopes_supported"] == ["openid", "profile"]


class TestHandleOAuth2:
    @pytest.mark.asyncio
    async def test_missing_header(self):
        config = OAuth2MiddlewareConfig(oauth2=OAuth2Config(client_id="c1"))
        result = await handle_oauth2(None, config)
        assert result["valid"] is False
        assert result["status"] == 401

    @pytest.mark.asyncio
    async def test_valid_token(self):
        token = _make_jwt({
            "sub": "user1", "exp": time.time() + 3600,
            "scope": "read write",
        })
        config = OAuth2MiddlewareConfig(oauth2=OAuth2Config(client_id="c1"))
        result = await handle_oauth2(f"Bearer {token}", config)
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_expired_token(self):
        token = _make_jwt({"sub": "u", "exp": time.time() - 100})
        config = OAuth2MiddlewareConfig(oauth2=OAuth2Config(client_id="c1"))
        result = await handle_oauth2(f"Bearer {token}", config)
        assert result["valid"] is False
        assert result["status"] == 401

    @pytest.mark.asyncio
    async def test_insufficient_scopes(self):
        token = _make_jwt({"sub": "u", "exp": time.time() + 3600, "scope": "read"})
        config = OAuth2MiddlewareConfig(
            oauth2=OAuth2Config(client_id="c1"),
            required_scopes=["write"],
        )
        result = await handle_oauth2(f"Bearer {token}", config)
        assert result["valid"] is False
        assert result["status"] == 403
        assert result["error"] == "insufficient_scope"

    @pytest.mark.asyncio
    async def test_custom_validator(self):
        async def validator(token):
            return {"sub": "custom-user", "scope": "admin"}

        config = OAuth2MiddlewareConfig(
            oauth2=OAuth2Config(client_id="c1"),
            custom_validator=validator,
        )
        result = await handle_oauth2("Bearer some-token", config)
        assert result["valid"] is True
        assert result["claims"].sub == "custom-user"

    @pytest.mark.asyncio
    async def test_docs_url_in_www_authenticate(self):
        config = OAuth2MiddlewareConfig(
            oauth2=OAuth2Config(
                client_id="c1",
                authorization_endpoint="https://auth.example.com/authorize",
            ),
        )
        result = await handle_oauth2(None, config)
        assert "auth.example.com" in result["www_authenticate"]
