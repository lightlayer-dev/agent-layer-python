"""Integration tests for Flask middleware."""

from flask import Flask

from agent_layer.errors import AgentError
from agent_layer.types import (
    AgentErrorOptions,
    AgentLayerConfig,
    AIManifest,
    DiscoveryConfig,
    LlmsTxtConfig,
    RateLimitConfig,
)
from agent_layer.flask import configure_agent_layer


def _create_app(config: AgentLayerConfig) -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    configure_agent_layer(app, config)

    @app.route("/ok")
    def ok():
        return {"status": "ok"}

    @app.route("/fail")
    def fail():
        raise AgentError(AgentErrorOptions(code="broken", message="It broke", status=500))

    return app


class TestErrorHandling:
    def test_agent_error_returns_envelope(self):
        app = _create_app(AgentLayerConfig())
        client = app.test_client()
        resp = client.get("/fail")
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["error"]["code"] == "broken"
        assert data["error"]["is_retriable"] is True

    def test_404_returns_envelope(self):
        app = _create_app(AgentLayerConfig())
        client = app.test_client()
        resp = client.get("/nonexistent")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error"]["code"] == "not_found"


class TestRateLimiting:
    def test_rate_limit_headers(self):
        app = _create_app(AgentLayerConfig(rate_limit=RateLimitConfig(max=5)))
        client = app.test_client()
        resp = client.get("/ok")
        assert resp.headers["X-RateLimit-Limit"] == "5"
        assert resp.headers["X-RateLimit-Remaining"] == "4"

    def test_rate_limit_429(self):
        app = _create_app(AgentLayerConfig(rate_limit=RateLimitConfig(max=1)))
        client = app.test_client()
        client.get("/ok")
        resp = client.get("/ok")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers


class TestLlmsTxt:
    def test_llms_txt_route(self):
        app = _create_app(
            AgentLayerConfig(
                llms_txt=LlmsTxtConfig(title="Test API", description="For testing"),
            )
        )
        client = app.test_client()
        resp = client.get("/llms.txt")
        assert resp.status_code == 200
        assert b"# Test API" in resp.data


class TestDiscovery:
    def test_well_known_ai(self):
        app = _create_app(
            AgentLayerConfig(
                discovery=DiscoveryConfig(manifest=AIManifest(name="Test API")),
            )
        )
        client = app.test_client()
        resp = client.get("/.well-known/ai")
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Test API"

    def test_json_ld(self):
        app = _create_app(
            AgentLayerConfig(
                discovery=DiscoveryConfig(manifest=AIManifest(name="Test API")),
            )
        )
        client = app.test_client()
        resp = client.get("/json-ld")
        assert resp.status_code == 200
        assert resp.get_json()["@type"] == "WebAPI"


class TestFullConfig:
    def test_all_features(self):
        app = _create_app(
            AgentLayerConfig(
                rate_limit=RateLimitConfig(max=100),
                llms_txt=LlmsTxtConfig(title="Full API"),
                discovery=DiscoveryConfig(manifest=AIManifest(name="Full API")),
            )
        )
        client = app.test_client()

        assert client.get("/ok").status_code == 200
        assert client.get("/llms.txt").status_code == 200
        assert client.get("/.well-known/ai").status_code == 200
        assert client.get("/json-ld").status_code == 200
