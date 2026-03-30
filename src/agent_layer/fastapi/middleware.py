"""
FastAPI middleware and route handlers for agent-layer.

Provides a one-liner to install all agent-layer features on a FastAPI app:
    - agents.txt endpoint
    - llms.txt / llms-full.txt endpoints
    - /.well-known/ai discovery endpoint
    - /.well-known/agent.json A2A endpoint
    - Rate limiting middleware
    - Structured error handling
    - MCP server (JSON-RPC 2.0)
    - Analytics (agent detection)
    - API key validation
    - x402 payments
    - Agent identity verification
    - Unified discovery
    - AG-UI streaming
    - OAuth2 token validation
    - Agent meta (HTML transforms)
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from agent_layer.core.a2a import A2AConfig, generate_agent_card
from agent_layer.core.agents_txt import AgentsTxtConfig, generate_agents_txt, is_agent_allowed
from agent_layer.core.ag_ui import AG_UI_HEADERS, AgUiEmitter, create_ag_ui_emitter
from agent_layer.core.agent_identity import AgentIdentityConfig, AuthzContext, handle_require_identity
from agent_layer.core.agent_meta import AgentMetaConfig, transform_html
from agent_layer.core.analytics import AnalyticsConfig, AgentEvent, create_analytics
from agent_layer.core.api_keys import ApiKeyConfig, MemoryApiKeyStore, validate_api_key, has_scope
from agent_layer.core.discovery import DiscoveryConfig, generate_ai_manifest, generate_json_ld
from agent_layer.core.errors import AgentError, format_error, AgentErrorOptions
from agent_layer.core.llms_txt import LlmsTxtConfig, generate_llms_txt, generate_llms_full_txt
from agent_layer.core.mcp import (
    McpServerConfig, generate_server_info, generate_tool_definitions, handle_json_rpc,
)
from agent_layer.core.oauth2 import OAuth2MiddlewareConfig, handle_oauth2
from agent_layer.core.rate_limit import RateLimitConfig, create_rate_limiter
from agent_layer.core.unified_discovery import UnifiedDiscoveryConfig, generate_all_discovery
from agent_layer.core.x402 import X402Config, handle_x402, HEADER_PAYMENT_SIGNATURE


class _RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces rate limiting on all requests."""

    def __init__(self, app: Any, check_rate_limit: Any) -> None:
        super().__init__(app)
        self._check = check_rate_limit

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        result = await self._check(request)

        if not result.allowed:
            error = format_error(
                AgentErrorOptions(
                    code="rate_limit_exceeded",
                    message="Too many requests. Please retry after the specified time.",
                    status=429,
                    is_retriable=True,
                    retry_after=result.retry_after,
                )
            )
            return JSONResponse(
                status_code=429,
                content={"error": error.to_dict()},
                headers={
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(result.reset_ms),
                    "Retry-After": str(result.retry_after),
                },
            )

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_ms)

        return response


class _ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware that catches AgentError exceptions and returns structured responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except AgentError as e:
            return JSONResponse(
                status_code=e.status,
                content=e.to_json(),
            )


class _AnalyticsMiddleware(BaseHTTPMiddleware):
    """Middleware that records analytics events for agent requests."""

    def __init__(self, app: Any, analytics: dict[str, Any]) -> None:
        super().__init__(app)
        self._analytics = analytics

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        ua = request.headers.get("user-agent", "")
        agent = self._analytics["detect"](ua)

        if agent or self._analytics["config"].track_all:
            event = AgentEvent(
                agent=agent or "unknown",
                user_agent=ua,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                timestamp=datetime.now(timezone.utc).isoformat(),
                content_type=response.headers.get("content-type"),
            )
            self._analytics["record"](event)

        return response


class _X402Middleware(BaseHTTPMiddleware):
    """Middleware that enforces x402 payment requirements."""

    def __init__(self, app: Any, config: X402Config) -> None:
        super().__init__(app)
        self._config = config

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        payment_header = request.headers.get(HEADER_PAYMENT_SIGNATURE)
        url = str(request.url)
        result = await handle_x402(
            request.method, request.url.path, url, payment_header, self._config
        )

        if result["action"] == "skip":
            return await call_next(request)

        if result["action"] == "payment_required":
            headers = result.get("headers", {})
            return JSONResponse(status_code=402, content=result["body"], headers=headers)

        if result["action"] == "error":
            return JSONResponse(
                status_code=result["status"],
                content={"error": result["error"]},
            )

        # success — set headers and continue
        response = await call_next(request)
        for k, v in result.get("headers", {}).items():
            response.headers[k] = v
        return response


class AgentLayer:
    """One-liner agent-layer integration for FastAPI.

    Usage:
        app = FastAPI()
        agent = AgentLayer(
            agents_txt=AgentsTxtConfig(rules=[...]),
            llms_txt=LlmsTxtConfig(title="My API"),
            discovery=DiscoveryConfig(manifest=AIManifest(name="My API")),
            a2a=A2AConfig(card=A2AAgentCard(name="My Agent", url="https://...")),
        )
        agent.install(app)
    """

    def __init__(
        self,
        *,
        agents_txt: AgentsTxtConfig | None = None,
        llms_txt: LlmsTxtConfig | None = None,
        discovery: DiscoveryConfig | None = None,
        a2a: A2AConfig | None = None,
        rate_limit: RateLimitConfig | None = None,
        errors: bool = True,
        mcp: McpServerConfig | None = None,
        analytics: AnalyticsConfig | None = None,
        api_keys: ApiKeyConfig | None = None,
        x402: X402Config | None = None,
        agent_identity: AgentIdentityConfig | None = None,
        unified_discovery: UnifiedDiscoveryConfig | None = None,
        ag_ui: bool = False,
        oauth2: OAuth2MiddlewareConfig | None = None,
        agent_meta: AgentMetaConfig | None = None,
    ) -> None:
        self.agents_txt = agents_txt
        self.llms_txt = llms_txt
        self.discovery = discovery
        self.a2a = a2a
        self.rate_limit = rate_limit
        self.errors = errors
        self.mcp = mcp
        self.analytics = analytics
        self.api_keys = api_keys
        self.x402 = x402
        self.agent_identity = agent_identity
        self.unified_discovery = unified_discovery
        self.ag_ui = ag_ui
        self.oauth2 = oauth2
        self.agent_meta = agent_meta

    def install(self, app: FastAPI) -> None:
        """Register all agent-layer routes and middleware on the FastAPI app."""

        # Error handling middleware (outermost)
        if self.errors:
            app.add_middleware(_ErrorHandlerMiddleware)

        # Rate limiting middleware
        if self.rate_limit:
            check = create_rate_limiter(self.rate_limit)
            app.add_middleware(_RateLimitMiddleware, check_rate_limit=check)

        # Analytics middleware
        if self.analytics:
            analytics_inst = create_analytics(self.analytics)
            app.add_middleware(_AnalyticsMiddleware, analytics=analytics_inst)

        # x402 payment middleware
        if self.x402:
            app.add_middleware(_X402Middleware, config=self.x402)

        # agents.txt route
        if self.agents_txt:
            config = self.agents_txt

            @app.get("/agents.txt", include_in_schema=False)
            async def agents_txt_route() -> PlainTextResponse:
                return PlainTextResponse(
                    generate_agents_txt(config),
                    media_type="text/plain",
                )

        # llms.txt routes
        if self.llms_txt:
            config_llms = self.llms_txt

            @app.get("/llms.txt", include_in_schema=False)
            async def llms_txt_route() -> PlainTextResponse:
                return PlainTextResponse(
                    generate_llms_txt(config_llms),
                    media_type="text/plain",
                )

            @app.get("/llms-full.txt", include_in_schema=False)
            async def llms_full_txt_route() -> PlainTextResponse:
                return PlainTextResponse(
                    generate_llms_full_txt(config_llms),
                    media_type="text/plain",
                )

        # Discovery routes
        if self.discovery:
            config_disc = self.discovery

            @app.get("/.well-known/ai", include_in_schema=False)
            async def well_known_ai_route() -> JSONResponse:
                return JSONResponse(generate_ai_manifest(config_disc))

            @app.get("/.well-known/ai/json-ld", include_in_schema=False)
            async def json_ld_route() -> JSONResponse:
                return JSONResponse(generate_json_ld(config_disc))

        # A2A Agent Card
        if self.a2a:
            config_a2a = self.a2a

            @app.get("/.well-known/agent.json", include_in_schema=False)
            async def agent_card_route() -> JSONResponse:
                return JSONResponse(generate_agent_card(config_a2a))

        # MCP server
        if self.mcp:
            mcp_config = self.mcp
            server_info = generate_server_info(mcp_config)
            auto_tools = generate_tool_definitions(mcp_config.routes or [])
            manual_tools = mcp_config.tools or []
            all_tools = auto_tools + manual_tools

            @app.post("/mcp", include_in_schema=False)
            async def mcp_post(request: Request) -> Response:
                body = await request.json()
                if not body or body.get("jsonrpc") != "2.0":
                    return JSONResponse(
                        status_code=400,
                        content={
                            "jsonrpc": "2.0", "id": None,
                            "error": {"code": -32600, "message": "Invalid JSON-RPC request"},
                        },
                    )
                result = await handle_json_rpc(body, server_info, all_tools)
                if result is None:
                    return Response(status_code=202)
                return JSONResponse(content=result)

            @app.get("/mcp", include_in_schema=False)
            async def mcp_sse(request: Request) -> Response:
                session_id = request.headers.get("mcp-session-id", str(uuid.uuid4()))
                return Response(
                    content="",
                    headers={
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Mcp-Session-Id": session_id,
                    },
                )

            @app.delete("/mcp", include_in_schema=False)
            async def mcp_delete() -> JSONResponse:
                return JSONResponse(content={"ok": True})

        # Unified discovery
        if self.unified_discovery:
            docs = generate_all_discovery(self.unified_discovery)
            for path, content in docs.items():
                if isinstance(content, dict):
                    _json_content = content

                    @app.get(path, include_in_schema=False)
                    async def _unified_json(c=_json_content) -> JSONResponse:
                        return JSONResponse(c)
                else:
                    _text_content = content

                    @app.get(path, include_in_schema=False)
                    async def _unified_text(c=_text_content) -> PlainTextResponse:
                        return PlainTextResponse(c, media_type="text/plain")

        # OAuth2 metadata
        if self.oauth2:
            oauth2_config = self.oauth2

            @app.get("/.well-known/oauth-authorization-server", include_in_schema=False)
            async def oauth2_metadata() -> JSONResponse:
                from agent_layer.core.oauth2 import build_oauth2_metadata
                return JSONResponse(build_oauth2_metadata(
                    issuer=oauth2_config.oauth2.issuer or "",
                    authorization_endpoint=oauth2_config.oauth2.authorization_endpoint,
                    token_endpoint=oauth2_config.oauth2.token_endpoint,
                    scopes=oauth2_config.oauth2.scopes or None,
                ))
