"""Tests for OAuth2/PKCE module."""

from __future__ import annotations

import base64
import json
import time


from agent_layer.oauth2 import (
    OAuth2Config,
    OAuth2TokenError,
    PKCEPair,
    build_authorization_url,
    build_oauth2_metadata,
    compute_code_challenge,
    extract_bearer_token,
    generate_code_verifier,
    generate_pkce,
    validate_access_token,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_jwt(payload: dict) -> str:
    """Create an unsigned JWT with the given payload."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.signature"


def _config(**overrides) -> OAuth2Config:
    defaults = {
        "client_id": "test-client",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "redirect_uri": "https://app.example.com/callback",
    }
    defaults.update(overrides)
    return OAuth2Config(**defaults)


# ── Tests: PKCE ──────────────────────────────────────────────────────────


class TestPKCE:
    def test_generate_code_verifier_default_length(self):
        verifier = generate_code_verifier()
        assert len(verifier) == 64

    def test_generate_code_verifier_custom_length(self):
        verifier = generate_code_verifier(128)
        assert len(verifier) == 128

    def test_verifier_uses_unreserved_chars(self):
        unreserved = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
        verifier = generate_code_verifier()
        assert all(c in unreserved for c in verifier)

    def test_compute_code_challenge_deterministic(self):
        challenge1 = compute_code_challenge("test_verifier")
        challenge2 = compute_code_challenge("test_verifier")
        assert challenge1 == challenge2

    def test_compute_code_challenge_is_base64url(self):
        challenge = compute_code_challenge("test_verifier")
        # base64url: no +, /, or = padding
        assert "+" not in challenge
        assert "/" not in challenge
        assert not challenge.endswith("=")

    def test_generate_pkce_returns_pair(self):
        pair = generate_pkce()
        assert isinstance(pair, PKCEPair)
        assert len(pair.code_verifier) == 64
        assert len(pair.code_challenge) > 0

    def test_pkce_challenge_matches_verifier(self):
        pair = generate_pkce()
        expected = compute_code_challenge(pair.code_verifier)
        assert pair.code_challenge == expected


# ── Tests: build_authorization_url ───────────────────────────────────────


class TestBuildAuthorizationUrl:
    def test_basic_url(self):
        config = _config()
        url = build_authorization_url(config, "state123", "challenge456")
        assert "response_type=code" in url
        assert "client_id=test-client" in url
        assert "state=state123" in url
        assert "code_challenge=challenge456" in url
        assert "code_challenge_method=S256" in url

    def test_includes_redirect_uri(self):
        config = _config()
        url = build_authorization_url(config, "s", "c")
        assert "redirect_uri=" in url

    def test_explicit_scopes(self):
        config = _config()
        url = build_authorization_url(config, "s", "c", scopes=["read", "write"])
        assert "scope=read+write" in url or "scope=read%20write" in url

    def test_scopes_from_config(self):
        config = _config(scopes={"read": "Read access", "write": "Write access"})
        url = build_authorization_url(config, "s", "c")
        assert "scope=" in url


# ── Tests: validate_access_token ─────────────────────────────────────────


class TestValidateAccessToken:
    def test_valid_token(self):
        config = _config()
        token = _make_jwt({"sub": "user1", "exp": int(time.time()) + 3600})
        result = validate_access_token(token, config)
        assert result.valid is True
        assert result.token is not None
        assert result.token.sub == "user1"

    def test_expired_token(self):
        config = _config()
        token = _make_jwt({"sub": "user1", "exp": int(time.time()) - 3600})
        result = validate_access_token(token, config)
        assert result.valid is False
        assert result.error == "token_expired"

    def test_malformed_token(self):
        config = _config()
        result = validate_access_token("not.a.valid.jwt.token", config)
        assert result.valid is False
        assert result.error == "malformed_token"

    def test_invalid_issuer(self):
        config = _config(issuer="https://expected.example.com")
        token = _make_jwt({"sub": "u", "exp": int(time.time()) + 3600, "iss": "https://wrong.com"})
        result = validate_access_token(token, config)
        assert result.valid is False
        assert result.error == "invalid_issuer"

    def test_valid_issuer(self):
        config = _config(issuer="https://auth.example.com")
        token = _make_jwt({"sub": "u", "exp": int(time.time()) + 3600, "iss": "https://auth.example.com"})
        result = validate_access_token(token, config)
        assert result.valid is True

    def test_invalid_audience(self):
        config = _config(audience="my-api")
        token = _make_jwt({"sub": "u", "exp": int(time.time()) + 3600, "aud": "other-api"})
        result = validate_access_token(token, config)
        assert result.valid is False
        assert result.error == "invalid_audience"

    def test_valid_audience_in_list(self):
        config = _config(audience="my-api")
        token = _make_jwt({"sub": "u", "exp": int(time.time()) + 3600, "aud": ["my-api", "other"]})
        result = validate_access_token(token, config)
        assert result.valid is True

    def test_missing_scopes(self):
        config = _config()
        token = _make_jwt({"sub": "u", "exp": int(time.time()) + 3600, "scope": "read"})
        result = validate_access_token(token, config, required_scopes=["read", "write"])
        assert result.valid is False
        assert "missing_scopes" in (result.error or "")
        assert "write" in (result.error or "")

    def test_scopes_extracted_from_scope_string(self):
        config = _config()
        token = _make_jwt({"sub": "u", "exp": int(time.time()) + 3600, "scope": "read write"})
        result = validate_access_token(token, config, required_scopes=["read", "write"])
        assert result.valid is True

    def test_scopes_extracted_from_scp_array(self):
        config = _config()
        token = _make_jwt({"sub": "u", "exp": int(time.time()) + 3600, "scp": ["read", "write"]})
        result = validate_access_token(token, config, required_scopes=["read"])
        assert result.valid is True

    def test_clock_skew_tolerance(self):
        config = _config()
        # Token expired 10 seconds ago, but with 30s skew tolerance
        token = _make_jwt({"sub": "u", "exp": int(time.time()) - 10})
        result = validate_access_token(token, config, clock_skew_seconds=30)
        assert result.valid is True


# ── Tests: extract_bearer_token ──────────────────────────────────────────


class TestExtractBearerToken:
    def test_extracts_token(self):
        assert extract_bearer_token("Bearer abc123") == "abc123"

    def test_case_insensitive(self):
        assert extract_bearer_token("bearer abc123") == "abc123"

    def test_none_header(self):
        assert extract_bearer_token(None) is None

    def test_empty_header(self):
        assert extract_bearer_token("") is None

    def test_non_bearer(self):
        assert extract_bearer_token("Basic abc123") is None

    def test_malformed(self):
        assert extract_bearer_token("Bearer") is None


# ── Tests: build_oauth2_metadata ─────────────────────────────────────────


class TestBuildOAuth2Metadata:
    def test_basic_metadata(self):
        config = _config()
        meta = build_oauth2_metadata(config)
        assert meta["authorization_endpoint"] == config.authorization_endpoint
        assert meta["token_endpoint"] == config.token_endpoint
        assert "code" in meta["response_types_supported"]
        assert "S256" in meta["code_challenge_methods_supported"]

    def test_public_client(self):
        config = _config()
        meta = build_oauth2_metadata(config)
        assert "none" in meta["token_endpoint_auth_methods_supported"]

    def test_confidential_client(self):
        config = _config(client_secret="secret")
        meta = build_oauth2_metadata(config)
        assert "client_secret_post" in meta["token_endpoint_auth_methods_supported"]

    def test_issuer_included(self):
        config = _config(issuer="https://auth.example.com")
        meta = build_oauth2_metadata(config)
        assert meta["issuer"] == "https://auth.example.com"

    def test_scopes_included(self):
        config = _config(scopes={"read": "Read", "write": "Write"})
        meta = build_oauth2_metadata(config)
        assert set(meta["scopes_supported"]) == {"read", "write"}


# ── Tests: OAuth2TokenError ──────────────────────────────────────────────


class TestOAuth2TokenError:
    def test_error_attributes(self):
        err = OAuth2TokenError("bad token", "invalid_grant", 400)
        assert str(err) == "bad token"
        assert err.error_code == "invalid_grant"
        assert err.status_code == 400
