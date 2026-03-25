"""Flask middleware that sets security headers on every response."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_layer.security_headers import SecurityHeadersConfig, generate_security_headers

if TYPE_CHECKING:
    from flask import Flask


def security_headers_middleware(app: Flask, config: SecurityHeadersConfig | None = None) -> None:
    """Register an after_request hook that sets security headers."""
    headers = generate_security_headers(config)

    @app.after_request
    def _set_security_headers(response):  # type: ignore[no-untyped-def]
        for key, value in headers.items():
            response.headers[key] = value
        return response
