"""Tests for Flask adapter."""

import pytest
from flask import Flask

from agent_layer.core.a2a import A2AAgentCard, A2AConfig, A2ASkill
from agent_layer.core.agents_txt import AgentsTxtConfig, AgentsTxtRule, Permission
from agent_layer.core.discovery import AIManifest, DiscoveryConfig
from agent_layer.core.llms_txt import LlmsTxtConfig
from agent_layer.flask import AgentLayer


def _make_app(**kwargs):
    app = Flask(__name__)
    app.config["TESTING"] = True
    agent = AgentLayer(**kwargs)
    agent.install(app)

    @app.route("/hello")
    def hello():
        return {"message": "hello"}

    return app.test_client()


class TestAgentsTxtRoute:
    def test_serves_agents_txt(self):
        client = _make_app(
            agents_txt=AgentsTxtConfig(
                rules=[AgentsTxtRule(agent="*", permission=Permission.ALLOW, paths=["/"])]
            )
        )
        resp = client.get("/agents.txt")
        assert resp.status_code == 200
        assert b"User-agent: *" in resp.data


class TestLlmsTxtRoutes:
    def test_serves_llms_txt(self):
        client = _make_app(
            llms_txt=LlmsTxtConfig(title="Test API", description="A test")
        )
        resp = client.get("/llms.txt")
        assert resp.status_code == 200
        assert b"# Test API" in resp.data

    def test_serves_llms_full_txt(self):
        client = _make_app(llms_txt=LlmsTxtConfig(title="Test API"))
        resp = client.get("/llms-full.txt")
        assert resp.status_code == 200
        assert b"# Test API" in resp.data


class TestDiscoveryRoutes:
    def test_well_known_ai(self):
        client = _make_app(
            discovery=DiscoveryConfig(manifest=AIManifest(name="Test API"))
        )
        resp = client.get("/.well-known/ai")
        assert resp.status_code == 200
        assert resp.json["name"] == "Test API"

    def test_json_ld(self):
        client = _make_app(
            discovery=DiscoveryConfig(manifest=AIManifest(name="Test API"))
        )
        resp = client.get("/.well-known/ai/json-ld")
        assert resp.status_code == 200
        assert resp.json["@type"] == "WebAPI"


class TestA2ARoute:
    def test_agent_card(self):
        client = _make_app(
            a2a=A2AConfig(
                card=A2AAgentCard(
                    name="TestAgent",
                    url="https://agent.example.com",
                    skills=[A2ASkill(id="s1", name="Skill 1")],
                )
            )
        )
        resp = client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        assert resp.json["name"] == "TestAgent"


class TestErrorHandling:
    def test_agent_error_caught(self):
        from agent_layer.core.errors import AgentError, AgentErrorOptions

        app = Flask(__name__)
        agent = AgentLayer(errors=True)
        agent.install(app)

        @app.route("/fail")
        def fail():
            raise AgentError(
                AgentErrorOptions(code="test_fail", message="It broke", status=400)
            )

        client = app.test_client()
        resp = client.get("/fail")
        assert resp.status_code == 400
        assert resp.json["error"]["code"] == "test_fail"


class TestMcpServer:
    def test_mcp_initialize(self):
        from agent_layer.core.mcp import McpServerConfig
        client = _make_app(mcp=McpServerConfig(name="test-api"))
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
        }, content_type="application/json")
        assert resp.status_code == 200
        assert resp.json["result"]["serverInfo"]["name"] == "test-api"

    def test_mcp_sse(self):
        from agent_layer.core.mcp import McpServerConfig
        client = _make_app(mcp=McpServerConfig(name="test"))
        resp = client.get("/mcp")
        assert resp.status_code == 200

    def test_mcp_delete(self):
        from agent_layer.core.mcp import McpServerConfig
        client = _make_app(mcp=McpServerConfig(name="test"))
        resp = client.delete("/mcp")
        assert resp.status_code == 200


class TestFullIntegration:
    def test_all_features(self):
        from agent_layer.core.mcp import McpServerConfig
        client = _make_app(
            agents_txt=AgentsTxtConfig(
                rules=[AgentsTxtRule(agent="*", permission=Permission.ALLOW)]
            ),
            llms_txt=LlmsTxtConfig(title="Full API"),
            discovery=DiscoveryConfig(manifest=AIManifest(name="Full API")),
            a2a=A2AConfig(
                card=A2AAgentCard(name="FullAgent", url="https://agent.example.com")
            ),
            mcp=McpServerConfig(name="Full API"),
        )
        assert client.get("/agents.txt").status_code == 200
        assert client.get("/llms.txt").status_code == 200
        assert client.get("/llms-full.txt").status_code == 200
        assert client.get("/.well-known/ai").status_code == 200
        assert client.get("/.well-known/agent.json").status_code == 200
        assert client.get("/hello").status_code == 200
        # MCP
        resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                          content_type="application/json")
        assert resp.status_code == 200
