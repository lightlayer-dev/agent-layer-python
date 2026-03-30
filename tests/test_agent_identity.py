"""Tests for agent identity module."""

import base64
import json
import time

import pytest

from agent_layer.core.agent_identity import (
    AgentAuthzPolicy,
    AgentIdentityConfig,
    AuthzContext,
    build_audit_event,
    decode_jwt_claims,
    evaluate_authz,
    extract_claims,
    handle_optional_identity,
    handle_require_identity,
    is_spiffe_trusted,
    parse_spiffe_id,
    validate_claims,
)


def _make_jwt(payload: dict) -> str:
    """Create an unsigned JWT for testing."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.sig"


class TestParseSpiffeId:
    def test_valid(self):
        sid = parse_spiffe_id("spiffe://example.com/agent/weather")
        assert sid is not None
        assert sid.trust_domain == "example.com"
        assert sid.path == "/agent/weather"

    def test_valid_no_path(self):
        sid = parse_spiffe_id("spiffe://example.com")
        assert sid is not None
        assert sid.trust_domain == "example.com"
        assert sid.path == ""

    def test_invalid(self):
        assert parse_spiffe_id("https://example.com") is None
        assert parse_spiffe_id("not-a-uri") is None


class TestIsSpiffeTrusted:
    def test_trusted(self):
        sid = parse_spiffe_id("spiffe://example.com/agent")
        assert sid is not None
        assert is_spiffe_trusted(sid, ["example.com"]) is True

    def test_untrusted(self):
        sid = parse_spiffe_id("spiffe://evil.com/agent")
        assert sid is not None
        assert is_spiffe_trusted(sid, ["example.com"]) is False


class TestDecodeJwtClaims:
    def test_valid(self):
        token = _make_jwt({"sub": "agent-1", "iss": "auth.example.com"})
        claims = decode_jwt_claims(token)
        assert claims is not None
        assert claims["sub"] == "agent-1"

    def test_invalid(self):
        assert decode_jwt_claims("not.a.jwt") is None
        assert decode_jwt_claims("only-one-part") is None


class TestExtractClaims:
    def test_basic(self):
        payload = {"sub": "agent-1", "iss": "auth.example.com", "scope": "read write"}
        claims = extract_claims(payload)
        assert claims.agent_id == "agent-1"
        assert claims.issuer == "auth.example.com"
        assert claims.scopes == ["read", "write"]

    def test_agent_id_preferred(self):
        payload = {"sub": "fallback", "agent_id": "preferred"}
        claims = extract_claims(payload)
        assert claims.agent_id == "preferred"

    def test_scopes_array(self):
        payload = {"sub": "a", "scopes": ["read", "write"]}
        claims = extract_claims(payload)
        assert claims.scopes == ["read", "write"]

    def test_scp_array(self):
        payload = {"sub": "a", "scp": ["read"]}
        claims = extract_claims(payload)
        assert claims.scopes == ["read"]

    def test_delegation(self):
        payload = {"sub": "a", "act": {"sub": "delegator"}}
        claims = extract_claims(payload)
        assert claims.delegated is True
        assert claims.delegated_by == "delegator"

    def test_spiffe_id(self):
        payload = {"agent_id": "spiffe://example.com/agent/weather"}
        claims = extract_claims(payload)
        assert claims.spiffe_id is not None
        assert claims.spiffe_id.trust_domain == "example.com"

    def test_custom_claims(self):
        payload = {"sub": "a", "iss": "x", "custom_field": "value"}
        claims = extract_claims(payload)
        assert "custom_field" in claims.custom_claims
        assert "iss" not in claims.custom_claims


class TestValidateClaims:
    def test_valid(self):
        claims = extract_claims({
            "sub": "agent-1", "iss": "auth.example.com",
            "aud": "api.example.com",
            "exp": time.time() + 3600, "iat": time.time(),
        })
        config = AgentIdentityConfig(
            trusted_issuers=["auth.example.com"],
            audience=["api.example.com"],
        )
        assert validate_claims(claims, config) is None

    def test_untrusted_issuer(self):
        claims = extract_claims({"sub": "a", "iss": "evil.com"})
        config = AgentIdentityConfig(trusted_issuers=["good.com"])
        err = validate_claims(claims, config)
        assert err is not None
        assert err.code == "untrusted_issuer"

    def test_invalid_audience(self):
        claims = extract_claims({"sub": "a", "aud": "wrong"})
        config = AgentIdentityConfig(audience=["correct"])
        err = validate_claims(claims, config)
        assert err is not None
        assert err.code == "invalid_audience"

    def test_expired(self):
        claims = extract_claims({"sub": "a", "exp": time.time() - 100})
        config = AgentIdentityConfig(clock_skew_seconds=30)
        err = validate_claims(claims, config)
        assert err is not None
        assert err.code == "expired_token"

    def test_too_long_lived(self):
        claims = extract_claims({"sub": "a", "iat": time.time(), "exp": time.time() + 999999})
        config = AgentIdentityConfig(max_lifetime_seconds=3600)
        err = validate_claims(claims, config)
        assert err is not None
        assert err.code == "token_too_long_lived"

    def test_untrusted_domain(self):
        claims = extract_claims({"agent_id": "spiffe://evil.com/agent"})
        config = AgentIdentityConfig(trusted_domains=["good.com"])
        err = validate_claims(claims, config)
        assert err is not None
        assert err.code == "untrusted_domain"


class TestEvaluateAuthz:
    def test_allow_policy(self):
        claims = extract_claims({"sub": "agent-1", "scope": "read"})
        ctx = AuthzContext(method="GET", path="/api/data")
        policies = [AgentAuthzPolicy(name="allow-all", effect="allow")]
        result = evaluate_authz(claims, ctx, policies)
        assert result.allowed is True

    def test_deny_policy(self):
        claims = extract_claims({"sub": "agent-1"})
        ctx = AuthzContext(method="GET", path="/api/data")
        policies = [AgentAuthzPolicy(name="deny-all", effect="deny")]
        result = evaluate_authz(claims, ctx, policies)
        assert result.allowed is False

    def test_default_deny(self):
        claims = extract_claims({"sub": "agent-1"})
        ctx = AuthzContext(method="GET", path="/api/data")
        result = evaluate_authz(claims, ctx, [], default_policy="deny")
        assert result.allowed is False

    def test_default_allow(self):
        claims = extract_claims({"sub": "agent-1"})
        ctx = AuthzContext(method="GET", path="/api/data")
        result = evaluate_authz(claims, ctx, [], default_policy="allow")
        assert result.allowed is True

    def test_method_matching(self):
        claims = extract_claims({"sub": "a"})
        ctx = AuthzContext(method="POST", path="/api")
        policies = [AgentAuthzPolicy(name="get-only", methods=["GET"], effect="allow")]
        result = evaluate_authz(claims, ctx, policies, default_policy="deny")
        assert result.allowed is False

    def test_path_matching(self):
        claims = extract_claims({"sub": "a"})
        ctx = AuthzContext(method="GET", path="/api/weather/today")
        policies = [AgentAuthzPolicy(name="weather", paths=["/api/weather/*"], effect="allow")]
        result = evaluate_authz(claims, ctx, policies, default_policy="deny")
        assert result.allowed is True

    def test_required_scopes(self):
        claims = extract_claims({"sub": "a", "scope": "read"})
        ctx = AuthzContext(method="GET", path="/api")
        policies = [AgentAuthzPolicy(name="need-write", required_scopes=["write"], effect="allow")]
        result = evaluate_authz(claims, ctx, policies, default_policy="deny")
        assert result.allowed is False

    def test_delegation(self):
        claims = extract_claims({"sub": "a", "act": {"sub": "delegator"}})
        ctx = AuthzContext(method="GET", path="/api")
        policies = [AgentAuthzPolicy(name="no-delegation", allow_delegated=False, effect="allow")]
        result = evaluate_authz(claims, ctx, policies, default_policy="deny")
        assert result.allowed is False


class TestBuildAuditEvent:
    def test_generates_event(self):
        claims = extract_claims({"sub": "agent-1", "iss": "auth.example.com"})
        ctx = AuthzContext(method="GET", path="/api/data")
        authz = evaluate_authz(claims, ctx, [], default_policy="allow")
        event = build_audit_event(claims, ctx, authz)
        assert event.type == "agent_identity"
        assert event.agent_id == "agent-1"
        assert event.method == "GET"
        assert event.timestamp != ""


class TestHandleRequireIdentity:
    @pytest.mark.asyncio
    async def test_missing_header(self):
        config = AgentIdentityConfig()
        ctx = AuthzContext(method="GET", path="/api")
        result = await handle_require_identity(None, config, ctx)
        assert "error" in result
        assert result["error"]["status"] == 401

    @pytest.mark.asyncio
    async def test_valid_token(self):
        token = _make_jwt({
            "sub": "agent-1", "iss": "auth.example.com",
            "exp": time.time() + 3600, "iat": time.time(),
        })
        config = AgentIdentityConfig(
            trusted_issuers=["auth.example.com"],
            default_policy="allow",
        )
        ctx = AuthzContext(method="GET", path="/api")
        result = await handle_require_identity(f"Bearer {token}", config, ctx)
        assert "claims" in result
        assert result["claims"].agent_id == "agent-1"


class TestHandleOptionalIdentity:
    @pytest.mark.asyncio
    async def test_missing_returns_none(self):
        config = AgentIdentityConfig()
        result = await handle_optional_identity(None, config)
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_returns_claims(self):
        token = _make_jwt({"sub": "agent-1", "exp": time.time() + 3600, "iat": time.time()})
        config = AgentIdentityConfig()
        result = await handle_optional_identity(f"Bearer {token}", config)
        assert result is not None
        assert result.agent_id == "agent-1"
