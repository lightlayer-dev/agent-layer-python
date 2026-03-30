"""Flask MCP server middleware.

Creates Flask routes that serve an MCP-compatible JSON-RPC server.
Uses Streamable HTTP transport per the MCP spec.
"""

from __future__ import annotations

import uuid

from flask import Blueprint, Response, jsonify, request

from agent_layer.async_utils import run_async_in_sync
from agent_layer.mcp import (
    JsonRpcRequest,
    McpServerConfig,
    McpToolDefinition,
    ToolCallHandler,
    build_tool_route_map,
    generate_server_info,
    generate_tool_definitions,
    handle_json_rpc,
    make_default_tool_call_handler,
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

    tool_route_map = build_tool_route_map(config.routes, auto_tools)
    handler = tool_call_handler or make_default_tool_call_handler(tool_route_map)

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

        result = run_async_in_sync(handle_json_rpc(rpc_request, server_info, all_tools, handler))

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
