"""FastAPI middleware that sets security headers on every response."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from agent_layer.security_headers import SecurityHeadersConfig, generate_security_headers

if TYPE_CHECKING:
    from fastapi import FastAPI


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, headers: dict[str, str]) -> None:
        super().__init__(app)
        self._headers = headers

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for key, value in self._headers.items():
            response.headers[key] = value
        return response


def security_headers_middleware(app: FastAPI, config: SecurityHeadersConfig | None = None) -> None:
    """Add security headers middleware to a FastAPI app."""
    headers = generate_security_headers(config)
    app.add_middleware(_SecurityHeadersMiddleware, headers=headers)
