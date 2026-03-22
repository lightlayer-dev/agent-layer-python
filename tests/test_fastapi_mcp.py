"""Tests for the FastAPI MCP server middleware."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_layer.fastapi.mcp import mcp_routes
from agent_layer.mcp import McpServerConfig
from agent_layer.types import RouteMetadata, RouteParameter


@pytest.fixture
def app():
    """Create a FastAPI app with MCP routes."""
    app = FastAPI()
    config = McpServerConfig(
        name="test-api",
        version="1.0.0",
        instructions="Test API tools",
        routes=[
            RouteMetadata(
                method="GET",
                path="/api/users",
                summary="List users",
                parameters=[
                    RouteParameter(name="limit", location="query", description="Max results"),
                ],
            ),
            RouteMetadata(
                method="POST",
                path="/api/users",
                summary="Create user",
                parameters=[
                    RouteParameter(name="name", location="body", required=True),
                ],
            ),
            RouteMetadata(
                method="GET",
                path="/api/users/:id",
                summary="Get user by ID",
            ),
        ],
    )
    app.include_router(mcp_routes(config), prefix="/mcp")
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestMcpPost:
    def test_initialize(self, client):
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["serverInfo"]["name"] == "test-api"
        assert data["result"]["protocolVersion"] == "2025-03-26"
        assert data["result"]["instructions"] == "Test API tools"

    def test_tools_list(self, client):
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list"
        })
        assert resp.status_code == 200
        tools = resp.json()["result"]["tools"]
        assert len(tools) == 3
        names = [t["name"] for t in tools]
        assert "get_api_users" in names
        assert "post_api_users" in names
        assert "get_api_users_by_id" in names

    def test_tools_call(self, client):
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "get_api_users", "arguments": {"limit": "10"}}
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["content"][0]["type"] == "text"
        import json
        content = json.loads(data["result"]["content"][0]["text"])
        assert content["method"] == "GET"
        assert "limit=10" in content["url"]

    def test_ping(self, client):
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 4, "method": "ping"
        })
        assert resp.status_code == 200
        assert resp.json()["result"] == {}

    def test_notification_202(self, client):
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "method": "notifications/initialized"
        })
        assert resp.status_code == 202

    def test_invalid_jsonrpc(self, client):
        resp = client.post("/mcp", json={
            "jsonrpc": "1.0", "id": 5, "method": "ping"
        })
        assert resp.status_code == 400

    def test_bad_json(self, client):
        resp = client.post("/mcp", content=b"not json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 400


class TestMcpGet:
    def test_sse_stream(self, client):
        resp = client.get("/mcp")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]


class TestMcpDelete:
    def test_end_session(self, client):
        resp = client.delete("/mcp")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestCustomToolCallHandler:
    def test_custom_handler(self):
        app = FastAPI()
        config = McpServerConfig(
            name="custom",
            routes=[
                RouteMetadata(method="GET", path="/api/items", summary="List items"),
            ],
        )

        async def custom_handler(name, args):
            return {"content": [{"type": "text", "text": f"Custom: {name}"}]}

        app.include_router(mcp_routes(config, tool_call_handler=custom_handler), prefix="/mcp")
        client = TestClient(app)

        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_api_items", "arguments": {}}
        })
        assert resp.status_code == 200
        assert "Custom: get_api_items" in resp.json()["result"]["content"][0]["text"]
