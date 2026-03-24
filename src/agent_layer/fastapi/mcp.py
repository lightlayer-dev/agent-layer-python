"""FastAPI MCP server middleware.

Creates FastAPI routes that serve an MCP-compatible JSON-RPC server.
Uses Streamable HTTP transport per the MCP spec.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

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


def mcp_routes(config: McpServerConfig, tool_call_handler: ToolCallHandler | None = None) -> APIRouter:
    """Create a FastAPI router that serves an MCP-compatible server.

    Args:
        config: MCP server configuration with routes and/or manual tools.
        tool_call_handler: Optional async function to handle tool calls.
            If not provided, a default handler that returns route dispatch info is used.

    Returns:
        FastAPI APIRouter to mount at a prefix (e.g., /mcp).
    """
    router = APIRouter()
    server_info = generate_server_info(config)

    # Merge auto-generated tools from routes with manually defined tools
    auto_tools = generate_tool_definitions(config.routes) if config.routes else []
    manual_tools = config.tools or []
    all_tools: list[McpToolDefinition] = [*auto_tools, *manual_tools]

    tool_route_map = build_tool_route_map(config.routes, auto_tools)
    handler = tool_call_handler or make_default_tool_call_handler(tool_route_map)

    @router.post("")
    @router.post("/")
    async def mcp_post(request: Request) -> Response:
        """Receive JSON-RPC messages from MCP clients."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                },
            )

        rpc_request = JsonRpcRequest(**body)

        if rpc_request.jsonrpc != "2.0":
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Invalid JSON-RPC request"},
                },
            )

        result = await handle_json_rpc(rpc_request, server_info, all_tools, handler)

        if result is None:
            return Response(status_code=202)

        return JSONResponse(
            content=result.model_dump(exclude_none=True),
            headers={"Content-Type": "application/json"},
        )

    @router.get("")
    @router.get("/")
    async def mcp_sse(request: Request) -> StreamingResponse:
        """SSE stream for server-initiated messages."""
        session_id = request.headers.get("mcp-session-id", str(uuid.uuid4()))

        async def event_stream():
            # Keep connection alive — send initial comment
            yield f": session {session_id}\n\n"
            # In a full implementation, this would yield server-initiated events

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Mcp-Session-Id": session_id,
            },
        )

    @router.delete("")
    @router.delete("/")
    async def mcp_delete(request: Request) -> JSONResponse:
        """End MCP session."""
        return JSONResponse(content={"ok": True})

    return router
