"""
FastAPI middleware and route handlers for agent-layer.

Provides a one-liner to install all agent-layer features on a FastAPI app:
    - agents.txt endpoint
    - llms.txt / llms-full.txt endpoints
    - /.well-known/ai discovery endpoint
    - /.well-known/agent.json A2A endpoint
    - Rate limiting middleware
    - Structured error handling
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from agent_layer.core.a2a import A2AConfig, generate_agent_card
from agent_layer.core.agents_txt import AgentsTxtConfig, generate_agents_txt, is_agent_allowed
from agent_layer.core.discovery import DiscoveryConfig, generate_ai_manifest, generate_json_ld
from agent_layer.core.errors import AgentError, format_error, AgentErrorOptions
from agent_layer.core.llms_txt import LlmsTxtConfig, generate_llms_txt, generate_llms_full_txt
from agent_layer.core.rate_limit import RateLimitConfig, create_rate_limiter


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
    ) -> None:
        self.agents_txt = agents_txt
        self.llms_txt = llms_txt
        self.discovery = discovery
        self.a2a = a2a
        self.rate_limit = rate_limit
        self.errors = errors

    def install(self, app: FastAPI) -> None:
        """Register all agent-layer routes and middleware on the FastAPI app."""

        # Error handling middleware (outermost)
        if self.errors:
            app.add_middleware(_ErrorHandlerMiddleware)

        # Rate limiting middleware
        if self.rate_limit:
            check = create_rate_limiter(self.rate_limit)
            app.add_middleware(_RateLimitMiddleware, check_rate_limit=check)

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
