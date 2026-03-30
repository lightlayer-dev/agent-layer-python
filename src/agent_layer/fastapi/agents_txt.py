"""agents.txt route handler and enforcement middleware for FastAPI."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from agent_layer.agents_txt import AgentsTxtConfig, generate_agents_txt, is_agent_allowed


def agents_txt_routes(config: AgentsTxtConfig) -> APIRouter:
    """Create a router serving /agents.txt."""
    router = APIRouter()
    content = generate_agents_txt(config)

    @router.get("/agents.txt")
    async def agents_txt():
        return PlainTextResponse(
            content=content,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    return router


class AgentsTxtEnforceMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces agents.txt rules — denies non-matching agents."""

    def __init__(self, app, config: AgentsTxtConfig):
        super().__init__(app)
        self.config = config

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.config.enforce:
            return await call_next(request)

        user_agent = request.headers.get("user-agent", "")
        path = request.url.path
        allowed = is_agent_allowed(self.config, user_agent, path)

        if allowed is False:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "type": "forbidden_error",
                        "code": "agent_denied",
                        "message": (
                            f'Access denied for agent "{user_agent}" on path "{path}". '
                            "See /agents.txt for access policy."
                        ),
                        "status": 403,
                        "is_retriable": False,
                        "docs_url": "/agents.txt",
                    }
                },
            )

        return await call_next(request)
