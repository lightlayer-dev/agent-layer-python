"""Agent meta middleware for FastAPI — injects agent-friendly HTML attributes."""

from __future__ import annotations

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from agent_layer.types import AgentMetaConfig


class AgentMetaMiddleware(BaseHTTPMiddleware):
    """Injects agent-related meta tags and headers into HTML responses."""

    def __init__(self, app, config: AgentMetaConfig) -> None:
        super().__init__(app)
        self.config = config

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        response = await call_next(request)

        # Add agent capability headers
        response.headers["X-Agent-Meta"] = "true"
        if self.config.agent_id_attribute:
            response.headers["X-Agent-Id-Attribute"] = self.config.agent_id_attribute

        return response


def agent_meta_middleware(app: FastAPI, config: AgentMetaConfig) -> None:
    """Add agent meta middleware to a FastAPI app."""
    app.add_middleware(AgentMetaMiddleware, config=config)
