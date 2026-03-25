"""End-to-end tests for FastAPI agent-layer integration.

Verifies all discovery endpoints, rate limiting, error envelopes,
user routes, and cross-feature composition via configure_agent_layer.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_layer.errors import AgentError
from agent_layer.fastapi import configure_agent_layer
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
        llms_txt=LlmsTxtConfig(title="E2E Test API", description="FastAPI E2E"),
        discovery=DiscoveryConfig(manifest=AIManifest(name="E2E Test API")),
    )


def _unified_config() -> UnifiedDiscoveryConfig:
    return UnifiedDiscoveryConfig(
        name="E2E Test API",
        description="FastAPI E2E unified discovery",
        url="https://api.example.com",
    )


def _create_full_app() -> FastAPI:
    app = FastAPI()
    configure_agent_layer(app, _full_config())

    from agent_layer.fastapi.unified_discovery import unified_discovery_routes

    app.include_router(unified_discovery_routes(_unified_config()))

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.get("/fail")
    async def fail():
        raise AgentError(
            AgentErrorOptions(code="test_error", message="Intentional failure", status=500)
        )

    return app


def _create_bare_app() -> FastAPI:
    """Bare FastAPI app with no agent-layer — control group."""
    app = FastAPI()

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    return app


# ── Discovery Endpoints ─────────────────────────────────────────────────


class TestDiscoveryEndpoints:
    def test_well_known_ai(self):
        client = TestClient(_create_full_app())
        resp = client.get("/.well-known/ai")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "E2E Test API"

    def test_llms_txt(self):
        client = TestClient(_create_full_app())
        resp = client.get("/llms.txt")
        assert resp.status_code == 200
        assert "# E2E Test API" in resp.text

    def test_agents_txt(self):
        client = TestClient(_create_full_app())
        resp = client.get("/agents.txt")
        assert resp.status_code == 200
        assert "E2E Test API" in resp.text

    def test_well_known_agent_json(self):
        client = TestClient(_create_full_app())
        resp = client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "E2E Test API"
        assert resp.headers.get("cache-control") == "public, max-age=3600"

    def test_json_ld(self):
        client = TestClient(_create_full_app())
        resp = client.get("/json-ld")
        assert resp.status_code == 200
        assert resp.json()["@type"] == "WebAPI"


# ── Rate Limiting ────────────────────────────────────────────────────────


class TestRateLimiting:
    def test_rate_limit_headers_present(self):
        client = TestClient(_create_full_app())
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert "x-ratelimit-limit" in resp.headers
        assert resp.headers["x-ratelimit-limit"] == "50"
        assert "x-ratelimit-remaining" in resp.headers

    def test_rate_limit_429_after_exhaustion(self):
        app = FastAPI()
        configure_agent_layer(app, AgentLayerConfig(rate_limit=RateLimitConfig(max=2)))

        @app.get("/ok")
        async def ok():
            return {"status": "ok"}

        client = TestClient(app)
        client.get("/ok")
        client.get("/ok")
        resp = client.get("/ok")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers


# ── Structured Error Responses ───────────────────────────────────────────


class TestStructuredErrors:
    def test_agent_error_returns_envelope(self):
        client = TestClient(_create_full_app(), raise_server_exceptions=False)
        resp = client.get("/fail")
        assert resp.status_code == 500
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "test_error"
        assert data["error"]["message"] == "Intentional failure"
        assert isinstance(data["error"]["is_retriable"], bool)
        assert data["error"]["type"] == "api_error"

    def test_error_envelope_has_required_fields(self):
        client = TestClient(_create_full_app(), raise_server_exceptions=False)
        resp = client.get("/fail")
        error = resp.json()["error"]
        for field in ("type", "code", "message", "status", "is_retriable"):
            assert field in error, f"Missing field: {field}"


# ── User Routes Unaffected ───────────────────────────────────────────────


class TestUserRoutes:
    def test_user_route_returns_normally(self):
        client = TestClient(_create_full_app())
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_user_route_not_shadowed_by_middleware(self):
        """User route /ok should not be altered by agent-layer."""
        client = TestClient(_create_full_app())
        resp = client.get("/ok")
        assert resp.json()["status"] == "ok"


# ── Cross-Feature Composition ───────────────────────────────────────────


class TestCrossFeatureComposition:
    def test_rate_limit_headers_on_discovery(self):
        """Discovery endpoints should also carry rate-limit headers."""
        client = TestClient(_create_full_app())
        resp = client.get("/.well-known/ai")
        assert resp.status_code == 200
        assert "x-ratelimit-limit" in resp.headers

    def test_rate_limit_headers_on_llms_txt(self):
        client = TestClient(_create_full_app())
        resp = client.get("/llms.txt")
        assert resp.status_code == 200
        assert "x-ratelimit-limit" in resp.headers

    def test_error_middleware_with_rate_limits(self):
        """Error envelope should work even with rate limiting enabled."""
        client = TestClient(_create_full_app(), raise_server_exceptions=False)
        resp = client.get("/fail")
        assert resp.status_code == 500
        assert resp.json()["error"]["code"] == "test_error"
        assert "x-ratelimit-limit" in resp.headers


# ── Bare App (Control Group) ────────────────────────────────────────────


class TestBareApp:
    def test_bare_app_no_discovery(self):
        client = TestClient(_create_bare_app())
        resp = client.get("/.well-known/ai")
        assert resp.status_code == 404

    def test_bare_app_no_llms_txt(self):
        client = TestClient(_create_bare_app())
        resp = client.get("/llms.txt")
        assert resp.status_code == 404

    def test_bare_app_no_agents_txt(self):
        client = TestClient(_create_bare_app())
        resp = client.get("/agents.txt")
        assert resp.status_code == 404

    def test_bare_app_no_rate_limit_headers(self):
        client = TestClient(_create_bare_app())
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert "x-ratelimit-limit" not in resp.headers

    def test_bare_app_user_route_works(self):
        client = TestClient(_create_bare_app())
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
