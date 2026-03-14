"""Integration tests for FastAPI middleware."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_layer.errors import AgentError
from agent_layer.types import (
    AgentErrorOptions,
    AgentLayerConfig,
    AIManifest,
    DiscoveryConfig,
    LlmsTxtConfig,
    RateLimitConfig,
)
from agent_layer.fastapi import configure_agent_layer


def _create_app(config: AgentLayerConfig) -> FastAPI:
    app = FastAPI()
    configure_agent_layer(app, config)

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.get("/fail")
    async def fail():
        raise AgentError(AgentErrorOptions(code="broken", message="It broke", status=500))

    return app


class TestErrorHandling:
    def test_agent_error_returns_envelope(self):
        app = _create_app(AgentLayerConfig())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/fail")
        assert resp.status_code == 500
        data = resp.json()
        assert data["error"]["code"] == "broken"
        assert data["error"]["is_retriable"] is True


class TestRateLimiting:
    def test_rate_limit_headers(self):
        app = _create_app(AgentLayerConfig(rate_limit=RateLimitConfig(max=5)))
        client = TestClient(app)
        resp = client.get("/ok")
        assert resp.headers["x-ratelimit-limit"] == "5"
        assert resp.headers["x-ratelimit-remaining"] == "4"

    def test_rate_limit_429(self):
        app = _create_app(AgentLayerConfig(rate_limit=RateLimitConfig(max=1)))
        client = TestClient(app)
        client.get("/ok")  # Use up the limit
        resp = client.get("/ok")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers


class TestLlmsTxt:
    def test_llms_txt_route(self):
        app = _create_app(AgentLayerConfig(
            llms_txt=LlmsTxtConfig(title="Test API", description="For testing"),
        ))
        client = TestClient(app)
        resp = client.get("/llms.txt")
        assert resp.status_code == 200
        assert "# Test API" in resp.text


class TestDiscovery:
    def test_well_known_ai(self):
        app = _create_app(AgentLayerConfig(
            discovery=DiscoveryConfig(manifest=AIManifest(name="Test API")),
        ))
        client = TestClient(app)
        resp = client.get("/.well-known/ai")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test API"

    def test_json_ld(self):
        app = _create_app(AgentLayerConfig(
            discovery=DiscoveryConfig(manifest=AIManifest(name="Test API")),
        ))
        client = TestClient(app)
        resp = client.get("/json-ld")
        assert resp.status_code == 200
        assert resp.json()["@type"] == "WebAPI"


class TestFullConfig:
    def test_all_features(self):
        app = _create_app(AgentLayerConfig(
            rate_limit=RateLimitConfig(max=100),
            llms_txt=LlmsTxtConfig(title="Full API"),
            discovery=DiscoveryConfig(manifest=AIManifest(name="Full API")),
        ))
        client = TestClient(app)

        assert client.get("/ok").status_code == 200
        assert client.get("/llms.txt").status_code == 200
        assert client.get("/.well-known/ai").status_code == 200
        assert client.get("/json-ld").status_code == 200
