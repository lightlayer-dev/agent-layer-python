"""MCP (Model Context Protocol) — Tool definition generation.

Converts RouteMetadata into MCP-compatible tool definitions,
enabling AI agents to discover and call API endpoints via the
Model Context Protocol (https://modelcontextprotocol.io).

Implements a lightweight MCP-compatible JSON-RPC server without
external SDK dependencies — handles initialize, tools/list, and
tools/call per the MCP specification.
"""

from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from agent_layer.types import RouteMetadata, RouteParameter

# ── MCP Types ───────────────────────────────────────────────────────────


class McpToolDefinition(BaseModel):
    """A single MCP tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class McpServerInfo(BaseModel):
    """Server info returned during MCP initialize."""

    name: str
    version: str = "1.0.0"
    instructions: str | None = None


class McpServerConfig(BaseModel):
    """Configuration for the MCP server middleware."""

    name: str
    version: str = "1.0.0"
    instructions: str | None = None
    routes: list[RouteMetadata] = Field(default_factory=list)
    tools: list[McpToolDefinition] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


# ── JSON-RPC Types ──────────────────────────────────────────────────────


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: Any = None
    error: dict[str, Any] | None = None


# ── Tool Call Handler Protocol ──────────────────────────────────────────

ToolCallHandler = Callable[
    [str, dict[str, Any]],
    Awaitable[dict[str, Any]],
]


# ── Tool Name Formatting ────────────────────────────────────────────────


def format_tool_name(method: str, path: str) -> str:
    """Convert HTTP method + path into a snake_case tool name.

    Examples:
        GET  /api/users        → get_api_users
        POST /api/users/create → post_api_users_create
        GET  /api/users/:id    → get_api_users_by_id
    """
    clean = path.strip("/")
    clean = re.sub(r":(\w+)", r"by_\1", clean)
    clean = re.sub(r"\{(\w+)\}", r"by_\1", clean)
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", clean)
    clean = re.sub(r"_+", "_", clean)
    clean = clean.strip("_")
    return f"{method.lower()}_{clean}".lower()


def parse_tool_name(tool_name: str) -> dict[str, str]:
    """Parse a tool name back into HTTP method and path.

    Reverses format_tool_name: get_api_users → {"method": "GET", "path": "/api/users"}
    """
    parts = tool_name.split("_")
    method = (parts[0] if parts else "get").upper()
    path_parts = parts[1:]

    segments: list[str] = []
    i = 0
    while i < len(path_parts):
        if path_parts[i] == "by" and i + 1 < len(path_parts):
            segments.append(f":{path_parts[i + 1]}")
            i += 2
        else:
            segments.append(path_parts[i])
            i += 1

    return {"method": method, "path": "/" + "/".join(segments)}


# ── JSON Schema Generation ──────────────────────────────────────────────


def build_input_schema(params: list[RouteParameter] | None = None) -> dict[str, Any]:
    """Build a JSON Schema object from route parameters."""
    schema: dict[str, Any] = {"type": "object", "properties": {}}

    if not params:
        return schema

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in params:
        prop: dict[str, Any] = {"type": "string"}
        if param.description:
            prop["description"] = param.description
        properties[param.name] = prop
        if param.required:
            required.append(param.name)

    schema["properties"] = properties
    if required:
        schema["required"] = required

    return schema


# ── Tool Generation ─────────────────────────────────────────────────────


def generate_tool_definitions(routes: list[RouteMetadata]) -> list[McpToolDefinition]:
    """Generate MCP tool definitions from route metadata."""
    return [
        McpToolDefinition(
            name=format_tool_name(route.method, route.path),
            description=route.summary or route.description or f"{route.method.upper()} {route.path}",
            input_schema=build_input_schema(route.parameters),
        )
        for route in routes
    ]


# ── Server Info ─────────────────────────────────────────────────────────


def generate_server_info(config: McpServerConfig) -> McpServerInfo:
    """Generate MCP server info from config."""
    return McpServerInfo(
        name=config.name,
        version=config.version,
        instructions=config.instructions,
    )


# ── JSON-RPC Handler ────────────────────────────────────────────────────


async def handle_json_rpc(
    request: JsonRpcRequest,
    server_info: McpServerInfo,
    tools: list[McpToolDefinition],
    tool_call_handler: ToolCallHandler | None = None,
) -> JsonRpcResponse | None:
    """Handle a JSON-RPC request per the MCP protocol.

    Supports: initialize, notifications/initialized, tools/list, tools/call, ping.
    """
    # Notifications (no id) — acknowledge silently
    if request.id is None:
        return None

    if request.method == "initialize":
        result: dict[str, Any] = {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": server_info.name,
                "version": server_info.version,
            },
        }
        if server_info.instructions:
            result["instructions"] = server_info.instructions
        return JsonRpcResponse(id=request.id, result=result)

    if request.method == "ping":
        return JsonRpcResponse(id=request.id, result={})

    if request.method == "tools/list":
        return JsonRpcResponse(
            id=request.id,
            result={
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.input_schema,
                    }
                    for t in tools
                ],
            },
        )

    if request.method == "tools/call":
        params = request.params or {}
        tool_name = params.get("name")
        if not tool_name:
            return JsonRpcResponse(
                id=request.id,
                error={"code": -32602, "message": "Invalid params: tool name is required"},
            )

        tool = next((t for t in tools if t.name == tool_name), None)
        if not tool:
            return JsonRpcResponse(
                id=request.id,
                error={"code": -32602, "message": f"Unknown tool: {tool_name}"},
            )

        if not tool_call_handler:
            return JsonRpcResponse(
                id=request.id,
                error={"code": -32603, "message": "Tool call handler not configured"},
            )

        try:
            result = await tool_call_handler(tool_name, params.get("arguments", {}))
            return JsonRpcResponse(id=request.id, result=result)
        except Exception as e:
            return JsonRpcResponse(
                id=request.id,
                error={"code": -32603, "message": str(e)},
            )

    return JsonRpcResponse(
        id=request.id,
        error={"code": -32601, "message": f"Method not found: {request.method}"},
    )


# ── Shared adapter helpers ─────────────────────────────────────────────


def build_tool_route_map(
    routes: list[RouteMetadata] | None,
    auto_tools: list[McpToolDefinition],
) -> dict[str, dict[str, str]]:
    """Build a mapping from tool names to their original route info."""
    tool_route_map: dict[str, dict[str, str]] = {}
    if routes:
        for i, route in enumerate(routes):
            if i < len(auto_tools):
                tool_route_map[auto_tools[i].name] = {
                    "method": route.method.upper(),
                    "path": route.path,
                }
    return tool_route_map


def make_default_tool_call_handler(
    tool_route_map: dict[str, dict[str, str]],
) -> ToolCallHandler:
    """Create the default tool-call handler that returns route dispatch info."""

    async def default_tool_call_handler(
        tool_name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        route_info = tool_route_map.get(tool_name)
        if not route_info:
            parsed = parse_tool_name(tool_name)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"error": f"No route handler for tool: {tool_name}", "parsed": parsed}
                        ),
                    }
                ]
            }

        resolved_path = route_info["path"]
        query_params: dict[str, str] = {}
        body_params: dict[str, Any] = {}

        for key, value in args.items():
            param_pattern = f":{key}"
            if param_pattern in resolved_path:
                resolved_path = resolved_path.replace(param_pattern, str(value))
            elif route_info["method"] in ("GET", "DELETE"):
                query_params[key] = str(value)
            else:
                body_params[key] = value

        qs = "&".join(f"{k}={v}" for k, v in query_params.items())
        url = f"{resolved_path}?{qs}" if qs else resolved_path

        result: dict[str, Any] = {
            "tool": tool_name,
            "method": route_info["method"],
            "url": url,
        }
        if body_params:
            result["body"] = body_params

        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    return default_tool_call_handler
