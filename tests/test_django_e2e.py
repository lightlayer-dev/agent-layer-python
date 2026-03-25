"""End-to-end tests for Django agent-layer integration.

Verifies all discovery endpoints, rate limiting, error envelopes,
user routes, and cross-feature composition via configure_agent_layer.
"""

from __future__ import annotations

import json

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        ROOT_URLCONF="tests.test_django_e2e",
        MIDDLEWARE=[
            "agent_layer.django.errors.AgentErrorsMiddleware",
            "agent_layer.django.rate_limits.RateLimitsMiddleware",
        ],
        AGENT_LAYER_RATE_LIMIT={"max": 50},
        SECRET_KEY="e2e-test-secret",
    )
    django.setup()

from django.http import JsonResponse
from django.test import TestCase, override_settings, RequestFactory
from django.urls import path

from agent_layer.errors import AgentError
from agent_layer.types import (
    AgentErrorOptions,
    AgentLayerConfig,
    AIManifest,
    DiscoveryConfig,
    LlmsTxtConfig,
    RateLimitConfig,
)
from agent_layer.django import configure_agent_layer
from agent_layer.django.rate_limits import RateLimitsMiddleware
from agent_layer.unified_discovery import UnifiedDiscoveryConfig
from agent_layer.django.unified_discovery import unified_discovery_urlpatterns


# ── Views ────────────────────────────────────────────────────────────────


def ok_view(request):
    return JsonResponse({"status": "ok"})


def fail_view(request):
    raise AgentError(
        AgentErrorOptions(code="test_error", message="Intentional failure", status=500)
    )


# ── URL Configuration ────────────────────────────────────────────────────

_config = AgentLayerConfig(
    errors=True,
    rate_limit=RateLimitConfig(max=50),
    llms_txt=LlmsTxtConfig(title="E2E Test API", description="Django E2E"),
    discovery=DiscoveryConfig(manifest=AIManifest(name="E2E Test API")),
)

_unified_config = UnifiedDiscoveryConfig(
    name="E2E Test API",
    description="Django E2E unified discovery",
    url="https://api.example.com",
)

urlpatterns = [
    path("ok", ok_view),
    path("fail", fail_view),
]
urlpatterns = configure_agent_layer(urlpatterns, _config)
urlpatterns.extend(unified_discovery_urlpatterns(_unified_config))


# ── Discovery Endpoints ─────────────────────────────────────────────────


@override_settings(ROOT_URLCONF="tests.test_django_e2e", AGENT_LAYER_RATE_LIMIT={"max": 50})
class TestDiscoveryEndpoints(TestCase):
    def test_well_known_ai(self):
        resp = self.client.get("/.well-known/ai")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["name"], "E2E Test API")

    def test_llms_txt(self):
        resp = self.client.get("/llms.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"# E2E Test API", resp.content)

    def test_agents_txt(self):
        resp = self.client.get("/agents.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"E2E Test API", resp.content)

    def test_well_known_agent_json(self):
        resp = self.client.get("/.well-known/agent.json")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["name"], "E2E Test API")
        self.assertEqual(resp["Cache-Control"], "public, max-age=3600")

    def test_json_ld(self):
        resp = self.client.get("/json-ld")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["@type"], "WebAPI")


# ── Rate Limiting ────────────────────────────────────────────────────────


@override_settings(ROOT_URLCONF="tests.test_django_e2e", AGENT_LAYER_RATE_LIMIT={"max": 50})
class TestRateLimiting(TestCase):
    def test_rate_limit_headers_present(self):
        resp = self.client.get("/ok")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("X-RateLimit-Limit", resp)
        self.assertEqual(resp["X-RateLimit-Limit"], "50")

    def test_rate_limit_429_after_exhaustion(self):
        factory = RequestFactory()
        middleware = RateLimitsMiddleware(lambda r: JsonResponse({"ok": True}))
        # First two requests should succeed, third should be rate limited
        with override_settings(AGENT_LAYER_RATE_LIMIT={"max": 2}):
            small_middleware = RateLimitsMiddleware(lambda r: JsonResponse({"ok": True}))
            small_middleware(factory.get("/ok"))
            small_middleware(factory.get("/ok"))
            resp = small_middleware(factory.get("/ok"))
            self.assertEqual(resp.status_code, 429)
            self.assertIn("Retry-After", resp)


# ── Structured Error Responses ───────────────────────────────────────────


@override_settings(ROOT_URLCONF="tests.test_django_e2e", AGENT_LAYER_RATE_LIMIT={"max": 50})
class TestStructuredErrors(TestCase):
    def test_agent_error_returns_envelope(self):
        resp = self.client.get("/fail")
        self.assertEqual(resp.status_code, 500)
        data = json.loads(resp.content)
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "test_error")
        self.assertEqual(data["error"]["message"], "Intentional failure")
        self.assertIsInstance(data["error"]["is_retriable"], bool)
        self.assertEqual(data["error"]["type"], "api_error")

    def test_error_envelope_has_required_fields(self):
        resp = self.client.get("/fail")
        error = json.loads(resp.content)["error"]
        for field in ("type", "code", "message", "status", "is_retriable"):
            self.assertIn(field, error, f"Missing field: {field}")


# ── User Routes Unaffected ───────────────────────────────────────────────


@override_settings(ROOT_URLCONF="tests.test_django_e2e", AGENT_LAYER_RATE_LIMIT={"max": 50})
class TestUserRoutes(TestCase):
    def test_user_route_returns_normally(self):
        resp = self.client.get("/ok")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data, {"status": "ok"})


# ── Cross-Feature Composition ───────────────────────────────────────────


@override_settings(ROOT_URLCONF="tests.test_django_e2e", AGENT_LAYER_RATE_LIMIT={"max": 50})
class TestCrossFeatureComposition(TestCase):
    def test_rate_limit_headers_on_discovery(self):
        resp = self.client.get("/.well-known/ai")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("X-RateLimit-Limit", resp)

    def test_rate_limit_headers_on_llms_txt(self):
        resp = self.client.get("/llms.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("X-RateLimit-Limit", resp)

    def test_error_middleware_with_rate_limits(self):
        resp = self.client.get("/fail")
        self.assertEqual(resp.status_code, 500)
        data = json.loads(resp.content)
        self.assertEqual(data["error"]["code"], "test_error")
        self.assertIn("X-RateLimit-Limit", resp)


# ── Bare App (Control Group) ────────────────────────────────────────────


class TestBareApp(TestCase):
    """Test a bare Django setup without agent-layer middleware.

    Uses RequestFactory to bypass the middleware stack configured in settings.
    """

    def test_bare_view_no_rate_limit_headers(self):
        factory = RequestFactory()
        resp = ok_view(factory.get("/ok"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("X-RateLimit-Limit", resp)

    def test_bare_view_returns_normally(self):
        factory = RequestFactory()
        resp = ok_view(factory.get("/ok"))
        data = json.loads(resp.content)
        self.assertEqual(data, {"status": "ok"})
