"""Tests for auth handler helpers."""

from __future__ import annotations

from agent_layer.auth_handler import (
    build_oauth_discovery_document,
    build_www_authenticate,
    check_require_auth,
)
from agent_layer.types import AgentAuthConfig


# ── Tests: build_oauth_discovery_document ────────────────────────────────


class TestBuildOauthDiscoveryDocument:
    def test_full_config(self):
        config = AgentAuthConfig(
            issuer="https://auth.example.com",
            authorization_url="https://auth.example.com/authorize",
            token_url="https://auth.example.com/token",
            scopes={"read": "Read access", "write": "Write access"},
        )
        doc = build_oauth_discovery_document(config)
        assert doc["issuer"] == "https://auth.example.com"
        assert doc["authorization_endpoint"] == "https://auth.example.com/authorize"
        assert doc["token_endpoint"] == "https://auth.example.com/token"
        assert set(doc["scopes_supported"]) == {"read", "write"}

    def test_empty_config(self):
        config = AgentAuthConfig()
        doc = build_oauth_discovery_document(config)
        assert doc == {}

    def test_partial_config(self):
        config = AgentAuthConfig(issuer="https://auth.example.com")
        doc = build_oauth_discovery_document(config)
        assert doc == {"issuer": "https://auth.example.com"}

    def test_empty_scopes_omitted(self):
        config = AgentAuthConfig(
            issuer="https://auth.example.com",
            scopes={},
        )
        doc = build_oauth_discovery_document(config)
        assert "scopes_supported" not in doc


# ── Tests: build_www_authenticate ────────────────────────────────────────


class TestBuildWwwAuthenticate:
    def test_realm_only(self):
        result = build_www_authenticate("api")
        assert result == 'Bearer realm="api"'

    def test_with_scopes(self):
        result = build_www_authenticate(
            "api", {"read": "Read access", "write": "Write access"}
        )
        assert 'Bearer realm="api"' in result
        assert "scope=" in result
        assert "read" in result
        assert "write" in result


# ── Tests: check_require_auth ────────────────────────────────────────────


class TestCheckRequireAuth:
    def test_passes_with_authorization_header(self):
        config = AgentAuthConfig()
        result = check_require_auth(config, "Bearer some-token")
        assert result.passed is True
        assert result.www_authenticate is None
        assert result.envelope is None

    def test_fails_without_authorization_header(self):
        config = AgentAuthConfig(
            realm="my-api",
            scopes={"read": "Read access"},
        )
        result = check_require_auth(config, None)
        assert result.passed is False
        assert result.www_authenticate is not None
        assert "my-api" in result.www_authenticate
        assert result.envelope is not None
        assert result.envelope.status == 401
        assert result.envelope.code == "authentication_required"

    def test_fails_with_empty_header(self):
        config = AgentAuthConfig()
        result = check_require_auth(config, "")
        assert result.passed is False

    def test_default_realm(self):
        config = AgentAuthConfig()
        result = check_require_auth(config, None)
        assert result.www_authenticate is not None
        assert "agent-layer" in result.www_authenticate

    def test_envelope_has_docs_url(self):
        config = AgentAuthConfig(
            authorization_url="https://auth.example.com/authorize"
        )
        result = check_require_auth(config, None)
        assert result.envelope is not None
        assert result.envelope.docs_url == "https://auth.example.com/authorize"
