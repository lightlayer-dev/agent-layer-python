"""Tests for FastAPI adapter."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_layer.core.a2a import A2AAgentCard, A2AConfig, A2ASkill
from agent_layer.core.agents_txt import AgentsTxtConfig, AgentsTxtRule, Permission
from agent_layer.core.analytics import AnalyticsConfig
from agent_layer.core.discovery import AIManifest, DiscoveryConfig
from agent_layer.core.llms_txt import LlmsTxtConfig, LlmsTxtSection
from agent_layer.core.mcp import McpServerConfig, McpToolDefinition
from agent_layer.core.rate_limit import RateLimitConfig
from agent_layer.core.unified_discovery import UnifiedDiscoveryConfig, UnifiedSkill
from agent_layer.core.agent_meta import AgentMetaConfig
from agent_layer.core.oauth2 import OAuth2Config, OAuth2MiddlewareConfig
from agent_layer.fastapi import AgentLayer


def _make_app(**kwargs) -> TestClient:
    app = FastAPI()
    agent = AgentLayer(**kwargs)
    agent.install(app)

    @app.get("/hello")
    async def hello():
        return {"message": "hello"}

    return TestClient(app)


class TestAgentsTxtRoute:
    def test_serves_agents_txt(self):
        client = _make_app(
            agents_txt=AgentsTxtConfig(
                rules=[AgentsTxtRule(agent="*", permission=Permission.ALLOW, paths=["/"])]
            )
        )
        resp = client.get("/agents.txt")
        assert resp.status_code == 200
        assert "User-agent: *" in resp.text
        assert "text/plain" in resp.headers["content-type"]


class TestLlmsTxtRoutes:
    def test_serves_llms_txt(self):
        client = _make_app(
            llms_txt=LlmsTxtConfig(title="Test API", description="A test API")
        )
        resp = client.get("/llms.txt")
        assert resp.status_code == 200
        assert "# Test API" in resp.text
        assert "> A test API" in resp.text

    def test_serves_llms_full_txt(self):
        client = _make_app(
            llms_txt=LlmsTxtConfig(
                title="Test API",
                sections=[LlmsTxtSection(title="Auth", content="Use tokens.")],
            )
        )
        resp = client.get("/llms-full.txt")
        assert resp.status_code == 200
        assert "# Test API" in resp.text


class TestDiscoveryRoutes:
    def test_well_known_ai(self):
        client = _make_app(
            discovery=DiscoveryConfig(
                manifest=AIManifest(name="Test API", description="A test")
            )
        )
        resp = client.get("/.well-known/ai")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test API"

    def test_json_ld(self):
        client = _make_app(
            discovery=DiscoveryConfig(
                manifest=AIManifest(name="Test API")
            )
        )
        resp = client.get("/.well-known/ai/json-ld")
        assert resp.status_code == 200
        data = resp.json()
        assert data["@type"] == "WebAPI"


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
        data = resp.json()
        assert data["name"] == "TestAgent"
        assert len(data["skills"]) == 1


class TestRateLimiting:
    def test_allows_under_limit(self):
        client = _make_app(rate_limit=RateLimitConfig(max=5))
        resp = client.get("/hello")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers

    def test_blocks_over_limit(self):
        client = _make_app(rate_limit=RateLimitConfig(max=2))
        client.get("/hello")
        client.get("/hello")
        resp = client.get("/hello")
        assert resp.status_code == 429
        data = resp.json()
        assert data["error"]["code"] == "rate_limit_exceeded"
        assert "Retry-After" in resp.headers

    def test_rate_limit_headers(self):
        client = _make_app(rate_limit=RateLimitConfig(max=10))
        resp = client.get("/hello")
        assert resp.headers["X-RateLimit-Limit"] == "10"
        assert resp.headers["X-RateLimit-Remaining"] == "9"


class TestErrorHandling:
    def test_agent_error_caught(self):
        from agent_layer.core.errors import AgentError, AgentErrorOptions

        app = FastAPI()
        agent = AgentLayer(errors=True)
        agent.install(app)

        @app.get("/fail")
        async def fail():
            raise AgentError(
                AgentErrorOptions(code="test_fail", message="It broke", status=400)
            )

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/fail")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"]["code"] == "test_fail"


class TestMcpServer:
    def test_mcp_initialize(self):
        client = _make_app(mcp=McpServerConfig(name="test-api", version="1.0.0"))
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["serverInfo"]["name"] == "test-api"

    def test_mcp_tools_list(self):
        client = _make_app(mcp=McpServerConfig(
            name="test",
            tools=[McpToolDefinition(name="search", description="Search")],
        ))
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/list",
        })
        assert resp.status_code == 200
        tools = resp.json()["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "search"

    def test_mcp_sse(self):
        client = _make_app(mcp=McpServerConfig(name="test"))
        resp = client.get("/mcp")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_mcp_delete(self):
        client = _make_app(mcp=McpServerConfig(name="test"))
        resp = client.delete("/mcp")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_mcp_invalid_request(self):
        client = _make_app(mcp=McpServerConfig(name="test"))
        resp = client.post("/mcp", json={"not": "jsonrpc"})
        assert resp.status_code == 400


class TestAnalytics:
    def test_records_agent_events(self):
        events = []
        client = _make_app(
            analytics=AnalyticsConfig(on_event=lambda e: events.append(e))
        )
        client.get("/hello", headers={"User-Agent": "GPTBot/1.0"})
        assert len(events) == 1
        assert events[0].agent == "GPTBot"

    def test_ignores_non_agents(self):
        events = []
        client = _make_app(
            analytics=AnalyticsConfig(on_event=lambda e: events.append(e))
        )
        client.get("/hello", headers={"User-Agent": "Mozilla/5.0"})
        assert len(events) == 0


class TestUnifiedDiscovery:
    def test_serves_all_formats(self):
        client = _make_app(
            unified_discovery=UnifiedDiscoveryConfig(
                name="Test API",
                url="https://api.example.com",
                skills=[UnifiedSkill(id="s1", name="Skill 1")],
                agents_txt_rules=[AgentsTxtRule(agent="*", permission=Permission.ALLOW)],
            )
        )
        assert client.get("/.well-known/ai").status_code == 200
        assert client.get("/.well-known/agent.json").status_code == 200
        assert client.get("/agents.txt").status_code == 200
        assert client.get("/llms.txt").status_code == 200
        assert client.get("/llms-full.txt").status_code == 200


class TestOAuth2Metadata:
    def test_serves_metadata(self):
        client = _make_app(
            oauth2=OAuth2MiddlewareConfig(
                oauth2=OAuth2Config(
                    client_id="c1",
                    issuer="https://auth.example.com",
                    authorization_endpoint="https://auth.example.com/authorize",
                    token_endpoint="https://auth.example.com/token",
                )
            )
        )
        resp = client.get("/.well-known/oauth-authorization-server")
        assert resp.status_code == 200
        data = resp.json()
        assert data["issuer"] == "https://auth.example.com"


class TestFullIntegration:
    def test_all_features(self):
        client = _make_app(
            agents_txt=AgentsTxtConfig(
                rules=[AgentsTxtRule(agent="*", permission=Permission.ALLOW)]
            ),
            llms_txt=LlmsTxtConfig(title="Full API"),
            discovery=DiscoveryConfig(manifest=AIManifest(name="Full API")),
            a2a=A2AConfig(
                card=A2AAgentCard(
                    name="FullAgent",
                    url="https://agent.example.com",
                )
            ),
            mcp=McpServerConfig(name="Full API"),
        )
        assert client.get("/agents.txt").status_code == 200
        assert client.get("/llms.txt").status_code == 200
        assert client.get("/llms-full.txt").status_code == 200
        assert client.get("/.well-known/ai").status_code == 200
        assert client.get("/.well-known/ai/json-ld").status_code == 200
        assert client.get("/.well-known/agent.json").status_code == 200
        assert client.get("/hello").status_code == 200
        # MCP
        resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
        assert resp.status_code == 200
