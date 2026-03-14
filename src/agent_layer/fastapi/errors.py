"""Agent-friendly error handling middleware for FastAPI."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from agent_layer.errors import AgentError, format_error, not_found_error
from agent_layer.types import AgentErrorOptions


class AgentErrorsMiddleware(BaseHTTPMiddleware):
    """Catches exceptions and returns agent-friendly error envelopes."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        try:
            response = await call_next(request)
            return response
        except AgentError as e:
            return JSONResponse(
                status_code=e.status,
                content=e.to_dict(),
            )
        except Exception as e:
            envelope = format_error(
                AgentErrorOptions(
                    code="internal_error",
                    message=str(e) or "An unexpected error occurred.",
                    status=500,
                )
            )
            return JSONResponse(
                status_code=500,
                content={"error": envelope.model_dump(exclude_none=True)},
            )


def agent_errors_middleware(app: FastAPI) -> None:
    """Add agent-friendly error handling to a FastAPI app."""
    app.add_middleware(AgentErrorsMiddleware)


async def not_found_handler(request: Request):
    """404 handler that returns an agent-friendly error envelope."""
    envelope = not_found_error(f"No route found for {request.method} {request.url.path}")
    return JSONResponse(
        status_code=404,
        content={"error": envelope.model_dump(exclude_none=True)},
    )
