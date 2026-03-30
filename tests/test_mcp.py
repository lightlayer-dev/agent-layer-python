"""Tests for MCP (Model Context Protocol) module."""

import pytest

from agent_layer.core.mcp import (
    McpServerConfig,
    McpToolDefinition,
    build_input_schema,
    format_tool_name,
    generate_server_info,
    generate_tool_definitions,
    handle_json_rpc,
    parse_tool_name,
)
from agent_layer.core.llms_txt import RouteMetadata, RouteParameter


class TestFormatToolName:
    def test_basic_path(self):
        assert format_tool_name("GET", "/api/users") == "get_api_users"

    def test_post_path(self):
        assert format_tool_name("POST", "/api/users/create") == "post_api_users_create"

    def test_path_param_colon(self):
        assert format_tool_name("GET", "/api/users/:id") == "get_api_users_by_id"

    def test_path_param_braces(self):
        assert format_tool_name("GET", "/api/users/{id}") == "get_api_users_by_id"

    def test_strips_slashes(self):
        assert format_tool_name("GET", "/api/users/") == "get_api_users"


class TestBuildInputSchema:
    def test_empty_params(self):
        schema = build_input_schema()
        assert schema == {"type": "object", "properties": {}}

    def test_with_params(self):
        params = [
            RouteParameter(name="limit", location="query", description="Max results"),
            RouteParameter(name="id", location="path", required=True),
        ]
        schema = build_input_schema(params)
        assert "limit" in schema["properties"]
        assert schema["properties"]["limit"]["description"] == "Max results"
        assert schema["required"] == ["id"]


class TestGenerateToolDefinitions:
    def test_generates_from_routes(self):
        routes = [
            RouteMetadata(
                method="GET",
                path="/api/users",
                summary="List all users",
                parameters=[RouteParameter(name="limit", location="query")],
            ),
            RouteMetadata(method="POST", path="/api/users", summary="Create a user"),
        ]
        tools = generate_tool_definitions(routes)
        assert len(tools) == 2
        assert tools[0].name == "get_api_users"
        assert tools[0].description == "List all users"
        assert tools[1].name == "post_api_users"


class TestParseToolName:
    def test_parse_basic(self):
        result = parse_tool_name("get_api_users")
        assert result["method"] == "GET"
        assert result["path"] == "/api/users"

    def test_parse_with_param(self):
        result = parse_tool_name("get_api_users_by_id")
        assert result["method"] == "GET"
        assert result["path"] == "/api/users/:id"


class TestGenerateServerInfo:
    def test_basic(self):
        config = McpServerConfig(name="test-api", version="1.0.0")
        info = generate_server_info(config)
        assert info.name == "test-api"
        assert info.version == "1.0.0"
        assert info.instructions is None

    def test_with_instructions(self):
        config = McpServerConfig(name="test", instructions="Use these tools")
        info = generate_server_info(config)
        assert info.instructions == "Use these tools"


class TestHandleJsonRpc:
    @pytest.mark.asyncio
    async def test_initialize(self):
        info = generate_server_info(McpServerConfig(name="test-api"))
        result = await handle_json_rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, info, []
        )
        assert result is not None
        assert result["result"]["serverInfo"]["name"] == "test-api"
        assert result["result"]["protocolVersion"] == "2025-03-26"

    @pytest.mark.asyncio
    async def test_ping(self):
        info = generate_server_info(McpServerConfig(name="test"))
        result = await handle_json_rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "ping"}, info, []
        )
        assert result is not None
        assert result["result"] == {}

    @pytest.mark.asyncio
    async def test_tools_list(self):
        info = generate_server_info(McpServerConfig(name="test"))
        tools = [McpToolDefinition(name="get_users", description="Get users")]
        result = await handle_json_rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, info, tools
        )
        assert result is not None
        assert len(result["result"]["tools"]) == 1
        assert result["result"]["tools"][0]["name"] == "get_users"

    @pytest.mark.asyncio
    async def test_tools_call(self):
        info = generate_server_info(McpServerConfig(name="test"))
        tools = [McpToolDefinition(name="get_users", description="Get users")]

        async def handler(name, args):
            return {"content": [{"type": "text", "text": "result"}]}

        result = await handle_json_rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_users"}},
            info, tools, handler,
        )
        assert result is not None
        assert result["result"]["content"][0]["text"] == "result"

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        info = generate_server_info(McpServerConfig(name="test"))
        result = await handle_json_rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "missing"}},
            info, [],
        )
        assert result is not None
        assert result["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_method_not_found(self):
        info = generate_server_info(McpServerConfig(name="test"))
        result = await handle_json_rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "unknown/method"}, info, []
        )
        assert result is not None
        assert result["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_notification_returns_none(self):
        info = generate_server_info(McpServerConfig(name="test"))
        result = await handle_json_rpc(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}, info, []
        )
        assert result is None
