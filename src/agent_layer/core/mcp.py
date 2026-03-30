"""
MCP (Model Context Protocol) — Tool definition generation.

Converts RouteMetadata into MCP-compatible tool definitions,
and implements a lightweight MCP-compatible JSON-RPC server without
external SDK dependencies — handles initialize, tools/list, and
tools/call per the MCP specification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class McpToolDefinition:
    """A single MCP tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})


@dataclass
class McpServerInfo:
    """Server info returned during MCP initialize."""

    name: str
    version: str
    instructions: str | None = None


@dataclass
class McpServerConfig:
    """Configuration for the MCP server middleware."""

    name: str
    version: str = "1.0.0"
    instructions: str | None = None
    tools: list[McpToolDefinition] | None = None
    routes: list[Any] | None = None  # list[RouteMetadata]


@dataclass
class JsonRpcRequest:
    """JSON-RPC 2.0 request."""

    jsonrpc: str
    method: str
    id: str | int | None = None
    params: dict[str, Any] | None = None


@dataclass
class JsonRpcResponse:
    """JSON-RPC 2.0 response."""

    jsonrpc: str = "2.0"
    id: str | int | None = None
    result: Any = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d


ToolCallHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


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


def build_input_schema(params: list[Any] | None = None) -> dict[str, Any]:
    """Build a JSON Schema object from route parameters."""
    schema: dict[str, Any] = {"type": "object", "properties": {}}
    if not params:
        return schema

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in params:
        prop: dict[str, Any] = {"type": "string"}
        desc = getattr(param, "description", None)
        if desc:
            prop["description"] = desc
        properties[param.name] = prop
        if getattr(param, "required", False):
            required.append(param.name)

    schema["properties"] = properties
    if required:
        schema["required"] = required
    return schema


def generate_tool_definitions(routes: list[Any]) -> list[McpToolDefinition]:
    """Generate MCP tool definitions from route metadata."""
    tools = []
    for route in routes:
        tools.append(McpToolDefinition(
            name=format_tool_name(route.method, route.path),
            description=getattr(route, "summary", None)
            or getattr(route, "description", None)
            or f"{route.method.upper()} {route.path}",
            input_schema=build_input_schema(getattr(route, "parameters", None)),
        ))
    return tools


def generate_server_info(config: McpServerConfig) -> McpServerInfo:
    """Generate MCP server info from config."""
    return McpServerInfo(
        name=config.name,
        version=config.version or "1.0.0",
        instructions=config.instructions,
    )


def parse_tool_name(tool_name: str) -> dict[str, str]:
    """Parse a tool name back into HTTP method and path."""
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


async def handle_json_rpc(
    request: dict[str, Any],
    server_info: McpServerInfo,
    tools: list[McpToolDefinition],
    tool_call_handler: ToolCallHandler | None = None,
) -> dict[str, Any] | None:
    """Handle a JSON-RPC request per the MCP protocol.

    Supports: initialize, notifications/initialized, tools/list, tools/call, ping.
    """
    req_id = request.get("id")

    # Notifications (no id) — acknowledge silently
    if req_id is None:
        return None

    method = request.get("method", "")

    if method == "initialize":
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
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.input_schema,
                    }
                    for t in tools
                ],
            },
        }

    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        if not name:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": "Invalid params: tool name is required"},
            }

        tool = next((t for t in tools if t.name == name), None)
        if not tool:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Unknown tool: {name}"},
            }

        if not tool_call_handler:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": "Tool call handler not configured"},
            }

        try:
            result = await tool_call_handler(name, params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)},
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }
