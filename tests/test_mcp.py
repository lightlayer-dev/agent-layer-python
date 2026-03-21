"""Tests for the MCP (Model Context Protocol) core module."""

from __future__ import annotations

import pytest

from agent_layer.mcp import (
    JsonRpcRequest,
    McpServerConfig,
    McpToolDefinition,
    build_input_schema,
    format_tool_name,
    generate_server_info,
    generate_tool_definitions,
    handle_json_rpc,
    parse_tool_name,
)
from agent_layer.types import RouteMetadata, RouteParameter


# ── format_tool_name ────────────────────────────────────────────────────


class TestFormatToolName:
    def test_simple_path(self):
        assert format_tool_name("GET", "/api/users") == "get_api_users"

    def test_nested_path(self):
        assert format_tool_name("POST", "/api/users/create") == "post_api_users_create"

    def test_colon_param(self):
        assert format_tool_name("GET", "/api/users/:id") == "get_api_users_by_id"

    def test_brace_param(self):
        assert format_tool_name("GET", "/api/users/{id}") == "get_api_users_by_id"

    def test_strips_slashes(self):
        assert format_tool_name("DELETE", "/api/items/") == "delete_api_items"

    def test_method_lowercased(self):
        assert format_tool_name("PATCH", "/api/data") == "patch_api_data"


# ── parse_tool_name ─────────────────────────────────────────────────────


class TestParseToolName:
    def test_simple(self):
        result = parse_tool_name("get_api_users")
        assert result == {"method": "GET", "path": "/api/users"}

    def test_with_param(self):
        result = parse_tool_name("get_api_users_by_id")
        assert result == {"method": "GET", "path": "/api/users/:id"}


# ── build_input_schema ──────────────────────────────────────────────────


class TestBuildInputSchema:
    def test_no_params(self):
        schema = build_input_schema(None)
        assert schema == {"type": "object", "properties": {}}

    def test_empty_params(self):
        schema = build_input_schema([])
        assert schema == {"type": "object", "properties": {}}

    def test_with_params(self):
        params = [
            RouteParameter(name="limit", location="query", description="Max results"),
            RouteParameter(name="name", location="body", required=True),
        ]
        schema = build_input_schema(params)
        assert schema["properties"]["limit"] == {"type": "string", "description": "Max results"}
        assert schema["properties"]["name"] == {"type": "string"}
        assert schema["required"] == ["name"]


# ── generate_tool_definitions ────────────────────────────────────────────


class TestGenerateToolDefinitions:
    def test_generates_from_routes(self):
        routes = [
            RouteMetadata(method="GET", path="/api/users", summary="List users"),
            RouteMetadata(method="POST", path="/api/users", summary="Create user"),
        ]
        tools = generate_tool_definitions(routes)
        assert len(tools) == 2
        assert tools[0].name == "get_api_users"
        assert tools[0].description == "List users"
        assert tools[1].name == "post_api_users"

    def test_fallback_description(self):
        routes = [RouteMetadata(method="GET", path="/api/health")]
        tools = generate_tool_definitions(routes)
        assert tools[0].description == "GET /api/health"


# ── generate_server_info ────────────────────────────────────────────────


class TestGenerateServerInfo:
    def test_basic(self):
        config = McpServerConfig(name="test-server", version="2.0.0")
        info = generate_server_info(config)
        assert info.name == "test-server"
        assert info.version == "2.0.0"
        assert info.instructions is None

    def test_with_instructions(self):
        config = McpServerConfig(name="test", instructions="Use these tools carefully")
        info = generate_server_info(config)
        assert info.instructions == "Use these tools carefully"


# ── handle_json_rpc ─────────────────────────────────────────────────────


class TestHandleJsonRpc:
    @pytest.fixture
    def server_info(self):
        return generate_server_info(McpServerConfig(name="test-api", version="1.0.0"))

    @pytest.fixture
    def tools(self):
        return [
            McpToolDefinition(
                name="get_api_users",
                description="List users",
                input_schema={"type": "object", "properties": {}},
            ),
        ]

    @pytest.mark.asyncio
    async def test_notification_returns_none(self, server_info, tools):
        req = JsonRpcRequest(method="notifications/initialized")
        result = await handle_json_rpc(req, server_info, tools)
        assert result is None

    @pytest.mark.asyncio
    async def test_initialize(self, server_info, tools):
        req = JsonRpcRequest(id=1, method="initialize")
        result = await handle_json_rpc(req, server_info, tools)
        assert result is not None
        assert result.id == 1
        assert result.result["protocolVersion"] == "2025-03-26"
        assert result.result["serverInfo"]["name"] == "test-api"

    @pytest.mark.asyncio
    async def test_ping(self, server_info, tools):
        req = JsonRpcRequest(id=2, method="ping")
        result = await handle_json_rpc(req, server_info, tools)
        assert result is not None
        assert result.result == {}

    @pytest.mark.asyncio
    async def test_tools_list(self, server_info, tools):
        req = JsonRpcRequest(id=3, method="tools/list")
        result = await handle_json_rpc(req, server_info, tools)
        assert result is not None
        tool_list = result.result["tools"]
        assert len(tool_list) == 1
        assert tool_list[0]["name"] == "get_api_users"

    @pytest.mark.asyncio
    async def test_tools_call_no_handler(self, server_info, tools):
        req = JsonRpcRequest(id=4, method="tools/call", params={"name": "get_api_users"})
        result = await handle_json_rpc(req, server_info, tools)
        assert result is not None
        assert result.error is not None
        assert result.error["code"] == -32603

    @pytest.mark.asyncio
    async def test_tools_call_with_handler(self, server_info, tools):
        async def handler(name, args):
            return {"content": [{"type": "text", "text": f"Called {name}"}]}

        req = JsonRpcRequest(id=5, method="tools/call", params={"name": "get_api_users"})
        result = await handle_json_rpc(req, server_info, tools, handler)
        assert result is not None
        assert result.result["content"][0]["text"] == "Called get_api_users"

    @pytest.mark.asyncio
    async def test_tools_call_unknown_tool(self, server_info, tools):
        req = JsonRpcRequest(id=6, method="tools/call", params={"name": "unknown"})
        result = await handle_json_rpc(req, server_info, tools)
        assert result is not None
        assert result.error is not None
        assert "Unknown tool" in result.error["message"]

    @pytest.mark.asyncio
    async def test_tools_call_missing_name(self, server_info, tools):
        req = JsonRpcRequest(id=7, method="tools/call", params={})
        result = await handle_json_rpc(req, server_info, tools)
        assert result is not None
        assert result.error is not None
        assert result.error["code"] == -32602

    @pytest.mark.asyncio
    async def test_unknown_method(self, server_info, tools):
        req = JsonRpcRequest(id=8, method="unknown/method")
        result = await handle_json_rpc(req, server_info, tools)
        assert result is not None
        assert result.error is not None
        assert result.error["code"] == -32601

    @pytest.mark.asyncio
    async def test_tools_call_handler_error(self, server_info, tools):
        async def bad_handler(name, args):
            raise RuntimeError("something broke")

        req = JsonRpcRequest(id=9, method="tools/call", params={"name": "get_api_users"})
        result = await handle_json_rpc(req, server_info, tools, bad_handler)
        assert result is not None
        assert result.error is not None
        assert "something broke" in result.error["message"]
