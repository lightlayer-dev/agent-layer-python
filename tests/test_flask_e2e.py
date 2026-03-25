"""End-to-end tests for Flask agent-layer integration.

Verifies all discovery endpoints, rate limiting, error envelopes,
user routes, and cross-feature composition via configure_agent_layer.
"""

from __future__ import annotations

from flask import Flask, jsonify

from agent_layer.errors import AgentError
from agent_layer.flask import configure_agent_layer
from agent_layer.types import (
    AgentErrorOptions,
    AgentLayerConfig,
    AIManifest,
    DiscoveryConfig,
    LlmsTxtConfig,
    RateLimitConfig,
)
from agent_layer.unified_discovery import UnifiedDiscoveryConfig


# ── Helpers ──────────────────────────────────────────────────────────────


def _full_config() -> AgentLayerConfig:
    return AgentLayerConfig(
        errors=True,
        rate_limit=RateLimitConfig(max=50),
        llms_txt=LlmsTxtConfig(title="E2E Test API", description="Flask E2E"),
        discovery=DiscoveryConfig(manifest=AIManifest(name="E2E Test API")),
    )


def _unified_config() -> UnifiedDiscoveryConfig:
    return UnifiedDiscoveryConfig(
        name="E2E Test API",
        description="Flask E2E unified discovery",
        url="https://api.example.com",
    )


def _create_full_app() -> Flask:
    app = Flask(__name__)
    configure_agent_layer(app, _full_config())

    from agent_layer.flask.unified_discovery import unified_discovery_blueprint

    app.register_blueprint(unified_discovery_blueprint(_unified_config()))

    @app.route("/ok")
    def ok():
        return jsonify({"status": "ok"})

    @app.route("/fail")
    def fail():
        raise AgentError(
            AgentErrorOptions(code="test_error", message="Intentional failure", status=500)
        )

    return app


def _create_bare_app() -> Flask:
    """Bare Flask app with no agent-layer — control group."""
    app = Flask(__name__)

    @app.route("/ok")
    def ok():
        return jsonify({"status": "ok"})

    return app


# ── Discovery Endpoints ─────────────────────────────────────────────────


class TestDiscoveryEndpoints:
    def test_well_known_ai(self):
        client = _create_full_app().test_client()
        resp = client.get("/.well-known/ai")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "E2E Test API"

    def test_llms_txt(self):
        client = _create_full_app().test_client()
        resp = client.get("/llms.txt")
        assert resp.status_code == 200
        assert b"# E2E Test API" in resp.data

    def test_agents_txt(self):
        client = _create_full_app().test_client()
        resp = client.get("/agents.txt")
        assert resp.status_code == 200
        assert b"E2E Test API" in resp.data

    def test_well_known_agent_json(self):
        client = _create_full_app().test_client()
        resp = client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "E2E Test API"
        assert resp.headers.get("Cache-Control") == "public, max-age=3600"

    def test_json_ld(self):
        client = _create_full_app().test_client()
        resp = client.get("/json-ld")
        assert resp.status_code == 200
        assert resp.get_json()["@type"] == "WebAPI"


# ── Rate Limiting ────────────────────────────────────────────────────────


class TestRateLimiting:
    def test_rate_limit_headers_present(self):
        client = _create_full_app().test_client()
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers
        assert resp.headers["X-RateLimit-Limit"] == "50"
        assert "X-RateLimit-Remaining" in resp.headers

    def test_rate_limit_429_after_exhaustion(self):
        app = Flask(__name__)
        configure_agent_layer(app, AgentLayerConfig(rate_limit=RateLimitConfig(max=2)))

        @app.route("/ok")
        def ok():
            return jsonify({"status": "ok"})

        client = app.test_client()
        client.get("/ok")
        client.get("/ok")
        resp = client.get("/ok")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers


# ── Structured Error Responses ───────────────────────────────────────────


class TestStructuredErrors:
    def test_agent_error_returns_envelope(self):
        client = _create_full_app().test_client()
        resp = client.get("/fail")
        assert resp.status_code == 500
        data = resp.get_json()
        assert "error" in data
        assert data["error"]["code"] == "test_error"
        assert data["error"]["message"] == "Intentional failure"
        assert isinstance(data["error"]["is_retriable"], bool)
        assert data["error"]["type"] == "api_error"

    def test_error_envelope_has_required_fields(self):
        client = _create_full_app().test_client()
        resp = client.get("/fail")
        error = resp.get_json()["error"]
        for field in ("type", "code", "message", "status", "is_retriable"):
            assert field in error, f"Missing field: {field}"


# ── User Routes Unaffected ───────────────────────────────────────────────


class TestUserRoutes:
    def test_user_route_returns_normally(self):
        client = _create_full_app().test_client()
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}

    def test_user_route_not_shadowed_by_middleware(self):
        client = _create_full_app().test_client()
        resp = client.get("/ok")
        assert resp.get_json()["status"] == "ok"


# ── Cross-Feature Composition ───────────────────────────────────────────


class TestCrossFeatureComposition:
    def test_rate_limit_headers_on_discovery(self):
        client = _create_full_app().test_client()
        resp = client.get("/.well-known/ai")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers

    def test_rate_limit_headers_on_llms_txt(self):
        client = _create_full_app().test_client()
        resp = client.get("/llms.txt")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers

    def test_error_middleware_with_rate_limits(self):
        client = _create_full_app().test_client()
        resp = client.get("/fail")
        assert resp.status_code == 500
        assert resp.get_json()["error"]["code"] == "test_error"
        assert "X-RateLimit-Limit" in resp.headers


# ── Bare App (Control Group) ────────────────────────────────────────────


class TestBareApp:
    def test_bare_app_no_discovery(self):
        client = _create_bare_app().test_client()
        resp = client.get("/.well-known/ai")
        assert resp.status_code == 404

    def test_bare_app_no_llms_txt(self):
        client = _create_bare_app().test_client()
        resp = client.get("/llms.txt")
        assert resp.status_code == 404

    def test_bare_app_no_agents_txt(self):
        client = _create_bare_app().test_client()
        resp = client.get("/agents.txt")
        assert resp.status_code == 404

    def test_bare_app_no_rate_limit_headers(self):
        client = _create_bare_app().test_client()
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" not in resp.headers

    def test_bare_app_user_route_works(self):
        client = _create_bare_app().test_client()
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}
