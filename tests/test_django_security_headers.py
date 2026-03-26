"""Tests for Django security_headers middleware."""

from __future__ import annotations

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        ROOT_URLCONF=__name__,
        ALLOWED_HOSTS=["*"],
        SECRET_KEY="test-secret",
    )
    django.setup()

from django.http import HttpResponse
from django.test import RequestFactory

from agent_layer.django.security_headers import (
    SecurityHeadersMiddleware,
    security_headers_middleware_class,
)
from agent_layer.security_headers import SecurityHeadersConfig


def _dummy_response(request):  # type: ignore[no-untyped-def]
    return HttpResponse("ok")


def test_default_security_headers() -> None:
    middleware = SecurityHeadersMiddleware(_dummy_response)
    factory = RequestFactory()
    request = factory.get("/test")
    resp = middleware(request)
    assert resp["X-Content-Type-Options"] == "nosniff"
    assert resp["X-Frame-Options"] == "DENY"
    assert resp["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert resp["Content-Security-Policy"] == "default-src 'self'"


def test_custom_security_headers() -> None:
    config = SecurityHeadersConfig(frame_options="SAMEORIGIN", csp=False)
    cls = security_headers_middleware_class(config)
    middleware = cls(_dummy_response)
    factory = RequestFactory()
    request = factory.get("/test")
    resp = middleware(request)
    assert resp["X-Frame-Options"] == "SAMEORIGIN"
    assert resp.get("Content-Security-Policy") is None
