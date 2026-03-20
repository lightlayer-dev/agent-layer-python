"""Tests for agent_identity module."""

import base64
import json
import time


from agent_layer.agent_identity import (
    AgentAuthzPolicyRuntime,
    AgentIdentityClaims,
    AgentIdentityConfig,
    AuthzContext,
    AuthzResult,
    SpiffeId,
    build_audit_event,
    decode_jwt_claims,
    evaluate_authz,
    extract_claims,
    is_spiffe_trusted,
    parse_spiffe_id,
    validate_claims,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.fakesig"


# ── SPIFFE ID Parsing ────────────────────────────────────────────────────


class TestParseSpiffeId:
    def test_valid_with_path(self):
        sid = parse_spiffe_id("spiffe://example.com/agent/weather-bot")
        assert sid is not None
        assert sid.trust_domain == "example.com"
        assert sid.path == "/agent/weather-bot"
        assert sid.raw == "spiffe://example.com/agent/weather-bot"

    def test_valid_without_path(self):
        sid = parse_spiffe_id("spiffe://example.com")
        assert sid is not None
        assert sid.trust_domain == "example.com"
        assert sid.path == "/"

    def test_invalid(self):
        assert parse_spiffe_id("https://example.com") is None
        assert parse_spiffe_id("not-a-uri") is None
        assert parse_spiffe_id("") is None


class TestIsSpiffeTrusted:
    def test_trusted(self):
        sid = parse_spiffe_id("spiffe://prod.example.com/bot")
        assert sid is not None
        assert is_spiffe_trusted(sid, ["prod.example.com", "staging.example.com"]) is True

    def test_untrusted(self):
        sid = parse_spiffe_id("spiffe://evil.com/bot")
        assert sid is not None
        assert is_spiffe_trusted(sid, ["prod.example.com"]) is False


# ── JWT Decoding ─────────────────────────────────────────────────────────


class TestDecodeJwtClaims:
    def test_valid(self):
        token = _make_jwt({"iss": "https://auth.example.com", "sub": "agent-1"})
        claims = decode_jwt_claims(token)
        assert claims == {"iss": "https://auth.example.com", "sub": "agent-1"}

    def test_invalid(self):
        assert decode_jwt_claims("not-a-jwt") is None
        assert decode_jwt_claims("a.b") is None
        assert decode_jwt_claims("") is None


# ── Claims Extraction ────────────────────────────────────────────────────


class TestExtractClaims:
    def test_standard_claims(self):
        claims = extract_claims({
            "iss": "https://auth.example.com",
            "sub": "spiffe://example.com/agent/bot",
            "aud": "https://api.example.com",
            "exp": 1700000000,
            "iat": 1699999000,
            "scope": "read:data write:data",
        })
        assert claims.agent_id == "spiffe://example.com/agent/bot"
        assert claims.spiffe_id is not None
        assert claims.spiffe_id.trust_domain == "example.com"
        assert claims.issuer == "https://auth.example.com"
        assert claims.audience == ["https://api.example.com"]
        assert claims.scopes == ["read:data", "write:data"]
        assert claims.delegated is False

    def test_delegation(self):
        claims = extract_claims({
            "iss": "https://auth.example.com",
            "sub": "agent-1",
            "aud": ["https://api.example.com"],
            "exp": 1700000000,
            "iat": 1699999000,
            "act": {"sub": "user@example.com"},
        })
        assert claims.delegated is True
        assert claims.delegated_by == "user@example.com"

    def test_scp_array(self):
        claims = extract_claims({"iss": "test", "sub": "agent", "scp": ["read", "write"]})
        assert claims.scopes == ["read", "write"]

    def test_custom_claims(self):
        claims = extract_claims({"iss": "test", "sub": "agent", "model": "gpt-4", "provider": "openai"})
        assert claims.custom_claims == {"model": "gpt-4", "provider": "openai"}

    def test_agent_id_over_sub(self):
        claims = extract_claims({
            "iss": "test",
            "sub": "service-account-123",
            "agent_id": "spiffe://example.com/my-agent",
        })
        assert claims.agent_id == "spiffe://example.com/my-agent"
        assert claims.spiffe_id is not None
        assert claims.spiffe_id.trust_domain == "example.com"


# ── Claims Validation ────────────────────────────────────────────────────


class TestValidateClaims:
    BASE_CONFIG = AgentIdentityConfig(
        trusted_issuers=["https://auth.example.com"],
        audience=["https://api.example.com"],
    )

    def _valid_claims(self) -> AgentIdentityClaims:
        now = int(time.time())
        return AgentIdentityClaims(
            agent_id="agent-1",
            issuer="https://auth.example.com",
            subject="agent-1",
            audience=["https://api.example.com"],
            expires_at=now + 600,
            issued_at=now - 10,
            scopes=["read"],
            delegated=False,
            custom_claims={},
        )

    def test_valid(self):
        assert validate_claims(self._valid_claims(), self.BASE_CONFIG) is None

    def test_untrusted_issuer(self):
        c = self._valid_claims()
        c.issuer = "https://evil.com"
        err = validate_claims(c, self.BASE_CONFIG)
        assert err is not None
        assert err.code == "untrusted_issuer"

    def test_invalid_audience(self):
        c = self._valid_claims()
        c.audience = ["https://other.com"]
        err = validate_claims(c, self.BASE_CONFIG)
        assert err is not None
        assert err.code == "invalid_audience"

    def test_expired(self):
        c = self._valid_claims()
        c.expires_at = int(time.time()) - 600
        err = validate_claims(c, self.BASE_CONFIG)
        assert err is not None
        assert err.code == "expired_token"

    def test_too_long_lived(self):
        now = int(time.time())
        c = self._valid_claims()
        c.issued_at = now
        c.expires_at = now + 7200
        config = AgentIdentityConfig(
            trusted_issuers=["https://auth.example.com"],
            audience=["https://api.example.com"],
            max_lifetime_seconds=3600,
        )
        err = validate_claims(c, config)
        assert err is not None
        assert err.code == "token_too_long_lived"

    def test_untrusted_domain(self):
        c = self._valid_claims()
        c.agent_id = "spiffe://evil.com/bot"
        c.spiffe_id = SpiffeId(trust_domain="evil.com", path="/bot", raw="spiffe://evil.com/bot")
        config = AgentIdentityConfig(
            trusted_issuers=["https://auth.example.com"],
            audience=["https://api.example.com"],
            trusted_domains=["example.com"],
        )
        err = validate_claims(c, config)
        assert err is not None
        assert err.code == "untrusted_domain"

    def test_clock_skew_tolerance(self):
        c = self._valid_claims()
        c.expires_at = int(time.time()) - 10
        config = AgentIdentityConfig(
            trusted_issuers=["https://auth.example.com"],
            audience=["https://api.example.com"],
            clock_skew_seconds=30,
        )
        assert validate_claims(c, config) is None


# ── Authorization ────────────────────────────────────────────────────────


class TestEvaluateAuthz:
    CLAIMS = AgentIdentityClaims(
        agent_id="spiffe://example.com/agent/weather-bot",
        spiffe_id=SpiffeId(
            trust_domain="example.com",
            path="/agent/weather-bot",
            raw="spiffe://example.com/agent/weather-bot",
        ),
        issuer="https://auth.example.com",
        subject="weather-bot",
        audience=["https://api.example.com"],
        expires_at=int(time.time()) + 600,
        issued_at=int(time.time()),
        scopes=["read:weather", "read:location"],
        delegated=False,
        custom_claims={},
    )

    CTX = AuthzContext(method="GET", path="/api/weather/forecast", headers={})

    def test_allows_matching_policy(self):
        policies = [
            AgentAuthzPolicyRuntime(
                name="weather-read",
                paths=["/api/weather/*"],
                methods=["GET"],
                required_scopes=["read:weather"],
            ),
        ]
        result = evaluate_authz(self.CLAIMS, self.CTX, policies)
        assert result.allowed is True
        assert result.matched_policy == "weather-read"

    def test_denies_missing_scopes(self):
        policies = [
            AgentAuthzPolicyRuntime(
                name="weather-write",
                paths=["/api/weather/*"],
                required_scopes=["write:weather"],
            ),
        ]
        result = evaluate_authz(self.CLAIMS, self.CTX, policies)
        assert result.allowed is False
        assert "write:weather" in (result.denied_reason or "")

    def test_denies_delegated(self):
        claims = AgentIdentityClaims(
            **{**self.CLAIMS.__dict__, "delegated": True, "delegated_by": "user@test.com"}
        )
        policies = [
            AgentAuthzPolicyRuntime(name="no-delegation", paths=["/api/*"], allow_delegated=False),
        ]
        result = evaluate_authz(claims, self.CTX, policies)
        assert result.allowed is False
        assert "Delegated" in (result.denied_reason or "")

    def test_default_deny(self):
        result = evaluate_authz(self.CLAIMS, self.CTX, [], "deny")
        assert result.allowed is False

    def test_default_allow(self):
        result = evaluate_authz(self.CLAIMS, self.CTX, [], "allow")
        assert result.allowed is True

    def test_filters_by_trust_domain(self):
        policies = [
            AgentAuthzPolicyRuntime(name="internal-only", trust_domains=["internal.example.com"]),
        ]
        result = evaluate_authz(self.CLAIMS, self.CTX, policies, "deny")
        assert result.allowed is False

    def test_filters_by_agent_pattern(self):
        policies = [
            AgentAuthzPolicyRuntime(name="weather-agents", agent_pattern="spiffe://example.com/agent/weather-*"),
        ]
        result = evaluate_authz(self.CLAIMS, self.CTX, policies)
        assert result.allowed is True

    def test_custom_evaluator(self):
        policies = [
            AgentAuthzPolicyRuntime(
                name="custom",
                evaluate=lambda c, _ctx: "admin" in c.scopes,
            ),
        ]
        result = evaluate_authz(self.CLAIMS, self.CTX, policies)
        assert result.allowed is False


# ── Audit Event ──────────────────────────────────────────────────────────


class TestBuildAuditEvent:
    def test_builds_complete_event(self):
        claims = AgentIdentityClaims(
            agent_id="spiffe://example.com/bot",
            spiffe_id=SpiffeId(trust_domain="example.com", path="/bot", raw="spiffe://example.com/bot"),
            issuer="https://auth.example.com",
            subject="bot",
            audience=["https://api.example.com"],
            expires_at=1700000000,
            issued_at=1699999000,
            scopes=["read"],
            delegated=True,
            delegated_by="user@example.com",
            custom_claims={},
        )
        event = build_audit_event(
            claims,
            AuthzContext(method="GET", path="/data", headers={}),
            AuthzResult(allowed=True, matched_policy="default"),
        )
        assert event.type == "agent_identity"
        assert event.agent_id == "spiffe://example.com/bot"
        assert event.spiffe_id == "spiffe://example.com/bot"
        assert event.delegated is True
        assert event.delegated_by == "user@example.com"
        assert event.authz_result.allowed is True
        assert event.timestamp
