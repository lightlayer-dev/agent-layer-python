"""Tests for core identity check and token extraction utilities."""

import base64
import json
import time

import pytest

from agent_layer.agent_identity import (
    AgentIdentityConfig,
    AgentAuthzPolicyRuntime,
    check_identity,
    extract_token_from_header,
)


def _make_jwt(payload: dict) -> str:
    """Create an unsigned JWT for testing."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    return f"{header.decode()}.{body.decode()}.sig"


class TestExtractTokenFromHeader:
    def test_none_input(self):
        assert extract_token_from_header(None, "Bearer") is None

    def test_empty_string(self):
        assert extract_token_from_header("", "Bearer") is None

    def test_bearer_prefix(self):
        assert extract_token_from_header("Bearer abc123", "Bearer") == "abc123"

    def test_raw_token(self):
        assert extract_token_from_header("abc123", "Bearer") == "abc123"

    def test_custom_prefix(self):
        assert extract_token_from_header("Token xyz", "Token") == "xyz"


class TestCheckIdentity:
    @pytest.fixture
    def config(self):
        return AgentIdentityConfig(
            trusted_issuers=["https://auth.example.com"],
            audience=["https://api.example.com"],
        )

    def test_missing_token(self, config):
        result = check_identity(None, config)
        assert not result.ok
        assert result.error_status == 401
        assert "agent_identity_required" in json.dumps(result.error_body)

    def test_malformed_token(self, config):
        result = check_identity("not-a-jwt", config)
        assert not result.ok
        assert result.error_status == 401
        assert "malformed_token" in json.dumps(result.error_body)

    def test_valid_token(self, config):
        now = int(time.time())
        token = _make_jwt({
            "iss": "https://auth.example.com",
            "sub": "agent-1",
            "aud": "https://api.example.com",
            "exp": now + 3600,
            "iat": now,
        })
        result = check_identity(token, config)
        assert result.ok
        assert result.claims is not None
        assert result.claims.agent_id == "agent-1"

    def test_untrusted_issuer(self, config):
        now = int(time.time())
        token = _make_jwt({
            "iss": "https://evil.example.com",
            "sub": "agent-1",
            "aud": "https://api.example.com",
            "exp": now + 3600,
            "iat": now,
        })
        result = check_identity(token, config)
        assert not result.ok
        assert result.error_status == 403
        assert "untrusted_issuer" in json.dumps(result.error_body)

    def test_expired_token(self, config):
        token = _make_jwt({
            "iss": "https://auth.example.com",
            "sub": "agent-1",
            "aud": "https://api.example.com",
            "exp": 1000,
            "iat": 500,
        })
        result = check_identity(token, config)
        assert not result.ok
        assert result.error_status == 401

    def test_with_decoded_claims(self, config):
        from agent_layer.agent_identity import AgentIdentityClaims

        now = int(time.time())
        claims = AgentIdentityClaims(
            agent_id="pre-decoded",
            issuer="https://auth.example.com",
            subject="pre-decoded",
            audience=["https://api.example.com"],
            expires_at=now + 3600,
            issued_at=now,
            scopes=["read"],
            delegated=False,
        )
        result = check_identity("ignored", config, decoded_claims=claims)
        assert result.ok
        assert result.claims.agent_id == "pre-decoded"

    def test_authz_policy_denied(self, config):
        now = int(time.time())
        token = _make_jwt({
            "iss": "https://auth.example.com",
            "sub": "agent-1",
            "aud": "https://api.example.com",
            "exp": now + 3600,
            "iat": now,
            "scope": "read",
        })
        policies = [
            AgentAuthzPolicyRuntime(
                name="require-write",
                required_scopes=["write"],
            )
        ]
        result = check_identity(
            token, config,
            method="POST", path="/api/data",
            runtime_policies=policies,
        )
        assert not result.ok
        assert result.error_status == 403
        assert "agent_unauthorized" in json.dumps(result.error_body)
