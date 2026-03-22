"""Flask MCP server middleware.

Creates Flask routes that serve an MCP-compatible JSON-RPC server.
Uses Streamable HTTP transport per the MCP spec.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from flask import Blueprint, Response, jsonify, request

from agent_layer.async_utils import run_async_in_sync
from agent_layer.mcp import (
    JsonRpcRequest,
    McpServerConfig,
    McpToolDefinition,
    ToolCallHandler,
    generate_server_info,
    generate_tool_definitions,
    handle_json_rpc,
    parse_tool_name,
)


def mcp_blueprint(
    config: McpServerConfig, tool_call_handler: ToolCallHandler | None = None
) -> Blueprint:
    """Create a Flask blueprint that serves an MCP-compatible server.

    Args:
        config: MCP server configuration with routes and/or manual tools.
        tool_call_handler: Optional async function to handle tool calls.

    Returns:
        Flask Blueprint to register (e.g., at prefix /mcp).
    """
    bp = Blueprint("mcp", __name__)
    server_info = generate_server_info(config)

    # Merge auto-generated tools from routes with manually defined tools
    auto_tools = generate_tool_definitions(config.routes) if config.routes else []
    manual_tools = config.tools or []
    all_tools: list[McpToolDefinition] = [*auto_tools, *manual_tools]

    # Map tool names to their original route info for internal dispatch
    tool_route_map: dict[str, dict[str, str]] = {}
    if config.routes:
        for i, route in enumerate(config.routes):
            if i < len(auto_tools):
                tool_route_map[auto_tools[i].name] = {
                    "method": route.method.upper(),
                    "path": route.path,
                }

    async def default_tool_call_handler(
        tool_name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Default tool call handler — returns route dispatch info."""
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

    handler = tool_call_handler or default_tool_call_handler

    @bp.route("", methods=["POST"])
    @bp.route("/", methods=["POST"])
    def mcp_post():
        """Receive JSON-RPC messages from MCP clients."""
        try:
            body = request.get_json(force=True)
        except Exception:
            return (
                jsonify(
                    jsonrpc="2.0",
                    id=None,
                    error={"code": -32700, "message": "Parse error"},
                ),
                400,
            )

        rpc_request = JsonRpcRequest(**body)

        if rpc_request.jsonrpc != "2.0":
            return (
                jsonify(
                    jsonrpc="2.0",
                    id=None,
                    error={"code": -32600, "message": "Invalid JSON-RPC request"},
                ),
                400,
            )

        result = run_async_in_sync(
            handle_json_rpc(rpc_request, server_info, all_tools, handler)
        )

        if result is None:
            return "", 202

        return jsonify(result.model_dump(exclude_none=True))

    @bp.route("", methods=["GET"])
    @bp.route("/", methods=["GET"])
    def mcp_sse():
        """SSE stream for server-initiated messages."""
        session_id = request.headers.get("mcp-session-id", str(uuid.uuid4()))

        def event_stream():
            yield f": session {session_id}\n\n"

        return Response(
            event_stream(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Mcp-Session-Id": session_id,
            },
        )

    @bp.route("", methods=["DELETE"])
    @bp.route("/", methods=["DELETE"])
    def mcp_delete():
        """End MCP session."""
        return jsonify(ok=True)

    return bp
