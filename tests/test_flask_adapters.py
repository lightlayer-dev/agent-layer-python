"""Tests for Flask adapter modules — auth, meta, unified_discovery, mcp, identity, x402."""

import base64
import json
import time

import pytest
from flask import Flask

from agent_layer.a2a import A2AAgentCard, A2AConfig
from agent_layer.agent_identity import AgentIdentityConfig
from agent_layer.analytics import AnalyticsConfig, AgentEvent
from agent_layer.mcp import McpServerConfig
from agent_layer.types import AgentAuthConfig, AgentMetaConfig, RouteMetadata
from agent_layer.unified_discovery import UnifiedDiscoveryConfig


def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    return f"{header.decode()}.{body.decode()}.sig"


class TestFlaskAuth:
    def test_oauth_metadata(self):
        from agent_layer.flask.auth import agent_auth_blueprint

        app = Flask(__name__)
        config = AgentAuthConfig(
            issuer="https://auth.example.com",
            token_url="https://auth.example.com/token",
            scopes={"read": "Read access"},
        )
        app.register_blueprint(agent_auth_blueprint(config))

        with app.test_client() as client:
            resp = client.get("/.well-known/oauth-authorization-server")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["issuer"] == "https://auth.example.com"
            assert data["token_endpoint"] == "https://auth.example.com/token"
            assert "read" in data["scopes_supported"]


class TestFlaskMeta:
    def test_meta_headers(self):
        from agent_layer.flask.meta import agent_meta_middleware

        app = Flask(__name__)
        agent_meta_middleware(app, AgentMetaConfig())

        @app.route("/test")
        def test_route():
            return {"ok": True}

        with app.test_client() as client:
            resp = client.get("/test")
            assert resp.headers["X-Agent-Meta"] == "true"
            assert resp.headers["X-Agent-Id-Attribute"] == "data-agent-id"


class TestFlaskUnifiedDiscovery:
    def test_all_formats(self):
        from agent_layer.flask.unified_discovery import unified_discovery_blueprint

        app = Flask(__name__)
        config = UnifiedDiscoveryConfig(
            name="Test API",
            description="A test",
            url="https://api.example.com",
        )
        app.register_blueprint(unified_discovery_blueprint(config))

        with app.test_client() as client:
            resp = client.get("/.well-known/ai")
            assert resp.status_code == 200
            assert resp.get_json()["name"] == "Test API"

            resp = client.get("/.well-known/agent.json")
            assert resp.status_code == 200
            assert resp.get_json()["name"] == "Test API"

            resp = client.get("/agents.txt")
            assert resp.status_code == 200
            assert b"Test API" in resp.data

            resp = client.get("/llms.txt")
            assert resp.status_code == 200
            assert b"# Test API" in resp.data

            resp = client.get("/llms-full.txt")
            assert resp.status_code == 200


class TestFlaskMcp:
    def test_initialize(self):
        from agent_layer.flask.mcp import mcp_blueprint

        app = Flask(__name__)
        config = McpServerConfig(
            name="test-api",
            routes=[RouteMetadata(method="GET", path="/api/items", summary="List items")],
        )
        app.register_blueprint(mcp_blueprint(config), url_prefix="/mcp")

        with app.test_client() as client:
            resp = client.post(
                "/mcp/",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["result"]["serverInfo"]["name"] == "test-api"

    def test_tools_list(self):
        from agent_layer.flask.mcp import mcp_blueprint

        app = Flask(__name__)
        config = McpServerConfig(
            name="test-api",
            routes=[RouteMetadata(method="GET", path="/api/items", summary="List items")],
        )
        app.register_blueprint(mcp_blueprint(config), url_prefix="/mcp")

        with app.test_client() as client:
            resp = client.post(
                "/mcp/",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            )
            assert resp.status_code == 200
            tools = resp.get_json()["result"]["tools"]
            assert len(tools) == 1
            assert tools[0]["name"] == "get_api_items"

    def test_sse_endpoint(self):
        from agent_layer.flask.mcp import mcp_blueprint

        app = Flask(__name__)
        config = McpServerConfig(name="test-api")
        app.register_blueprint(mcp_blueprint(config), url_prefix="/mcp")

        with app.test_client() as client:
            resp = client.get("/mcp/")
            assert resp.status_code == 200
            assert "text/event-stream" in resp.content_type

    def test_delete_session(self):
        from agent_layer.flask.mcp import mcp_blueprint

        app = Flask(__name__)
        config = McpServerConfig(name="test-api")
        app.register_blueprint(mcp_blueprint(config), url_prefix="/mcp")

        with app.test_client() as client:
            resp = client.delete("/mcp/")
            assert resp.status_code == 200
            assert resp.get_json()["ok"] is True


class TestFlaskAgentIdentity:
    def test_rejects_without_token(self):
        from agent_layer.flask.agent_identity import agent_identity_middleware

        app = Flask(__name__)
        app.config["TESTING"] = True
        config = AgentIdentityConfig(
            trusted_issuers=["https://auth.example.com"],
            audience=["https://api.example.com"],
        )
        agent_identity_middleware(app, config)

        @app.route("/protected")
        def protected():
            return {"ok": True}

        with app.test_client() as client:
            resp = client.get("/protected")
            assert resp.status_code == 401

    def test_accepts_valid_token(self):
        from agent_layer.flask.agent_identity import agent_identity_middleware

        app = Flask(__name__)
        app.config["TESTING"] = True
        config = AgentIdentityConfig(
            trusted_issuers=["https://auth.example.com"],
            audience=["https://api.example.com"],
        )
        agent_identity_middleware(app, config)

        @app.route("/protected")
        def protected():
            from flask import g
            return {"agent": g.agent_identity.agent_id}

        now = int(time.time())
        token = _make_jwt({
            "iss": "https://auth.example.com",
            "sub": "agent-1",
            "aud": "https://api.example.com",
            "exp": now + 3600,
            "iat": now,
        })

        with app.test_client() as client:
            resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            assert resp.get_json()["agent"] == "agent-1"

    def test_optional_allows_without_token(self):
        from agent_layer.flask.agent_identity import agent_identity_middleware

        app = Flask(__name__)
        app.config["TESTING"] = True
        config = AgentIdentityConfig(
            trusted_issuers=["https://auth.example.com"],
            audience=["https://api.example.com"],
        )
        agent_identity_middleware(app, config, optional=True)

        @app.route("/public")
        def public():
            return {"ok": True}

        with app.test_client() as client:
            resp = client.get("/public")
            assert resp.status_code == 200


class TestFlaskA2A:
    def test_agent_card(self):
        from agent_layer.flask.a2a import a2a_blueprint

        app = Flask(__name__)
        config = A2AConfig(
            card=A2AAgentCard(name="Test Agent", url="https://agent.example.com"),
        )
        app.register_blueprint(a2a_blueprint(config))

        with app.test_client() as client:
            resp = client.get("/.well-known/agent.json")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["name"] == "Test Agent"
            assert resp.headers["Cache-Control"] == "public, max-age=3600"
