"""Django middleware that sets security headers on every response."""

from __future__ import annotations

from typing import Any, Callable

from django.http import HttpRequest, HttpResponse

from agent_layer.security_headers import SecurityHeadersConfig, generate_security_headers


class SecurityHeadersMiddleware:
    """Django middleware that sets security headers on every response.

    Usage in settings.py::

        MIDDLEWARE = [
            "agent_layer.django.security_headers.SecurityHeadersMiddleware",
            ...
        ]
        AGENT_LAYER_SECURITY_HEADERS = SecurityHeadersConfig(hsts_max_age=31536000)

    Or create programmatically::

        from agent_layer.django.security_headers import security_headers_middleware_class
        MySecurityHeaders = security_headers_middleware_class(SecurityHeadersConfig())
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self._headers = generate_security_headers(SecurityHeadersConfig())

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        for key, value in self._headers.items():
            response[key] = value
        return response


def security_headers_middleware_class(
    config: SecurityHeadersConfig | None = None,
) -> type[Any]:
    """Create a Django middleware class with the given security headers config."""
    headers = generate_security_headers(config)

    class _ConfiguredSecurityHeaders:
        def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
            self.get_response = get_response

        def __call__(self, request: HttpRequest) -> HttpResponse:
            response = self.get_response(request)
            for key, value in headers.items():
                response[key] = value
            return response

    return _ConfiguredSecurityHeaders
