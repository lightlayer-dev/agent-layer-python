"""Django MCP server URL patterns.

Creates Django URL patterns that serve an MCP-compatible JSON-RPC server.
Uses Streamable HTTP transport per the MCP spec.
"""

from __future__ import annotations

import json
import uuid

from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

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


def mcp_urlpatterns(
    config: McpServerConfig, tool_call_handler: ToolCallHandler | None = None
) -> list:
    """Create Django URL patterns that serve an MCP-compatible server.

    Args:
        config: MCP server configuration with routes and/or manual tools.
        tool_call_handler: Optional async function to handle tool calls.

    Returns:
        List of Django URL patterns to include.
    """
    server_info = generate_server_info(config)

    # Merge auto-generated tools from routes with manually defined tools
    auto_tools = generate_tool_definitions(config.routes) if config.routes else []
    manual_tools = config.tools or []
    all_tools: list[McpToolDefinition] = [*auto_tools, *manual_tools]

    tool_route_map = build_tool_route_map(config.routes, auto_tools)
    handler = tool_call_handler or make_default_tool_call_handler(tool_route_map)

    @csrf_exempt
    def mcp_view(request: HttpRequest) -> HttpResponse:
        """Handle MCP protocol requests (POST, GET, DELETE)."""
        if request.method == "POST":
            try:
                body = json.loads(request.body)
            except Exception:
                return JsonResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    },
                    status=400,
                )

            rpc_request = JsonRpcRequest(**body)

            if rpc_request.jsonrpc != "2.0":
                return JsonResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Invalid JSON-RPC request"},
                    },
                    status=400,
                )

            result = run_async_in_sync(
                handle_json_rpc(rpc_request, server_info, all_tools, handler)
            )

            if result is None:
                return HttpResponse(status=202)

            return JsonResponse(result.model_dump(exclude_none=True))

        if request.method == "GET":
            session_id = request.META.get("HTTP_MCP_SESSION_ID", str(uuid.uuid4()))

            def event_stream():
                yield f": session {session_id}\n\n"

            response = StreamingHttpResponse(
                event_stream(), content_type="text/event-stream"
            )
            response["Cache-Control"] = "no-cache"
            response["Connection"] = "keep-alive"
            response["Mcp-Session-Id"] = session_id
            return response

        if request.method == "DELETE":
            return JsonResponse({"ok": True})

        return HttpResponse(status=405)

    return [
        path("", mcp_view, name="mcp_endpoint"),
    ]
