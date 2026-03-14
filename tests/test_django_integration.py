"""Integration tests for Django middleware."""

import os
import django
from django.conf import settings

# Minimal Django config for testing
if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        ROOT_URLCONF="tests.test_django_integration",
        MIDDLEWARE=[
            "agent_layer.django.errors.AgentErrorsMiddleware",
            "agent_layer.django.rate_limits.RateLimitsMiddleware",
        ],
        AGENT_LAYER_RATE_LIMIT={"max": 5},
        SECRET_KEY="test-secret",
    )
    django.setup()

from django.http import JsonResponse
from django.test import RequestFactory, TestCase
from django.urls import path

from agent_layer.errors import AgentError
from agent_layer.types import (
    AgentErrorOptions,
    AIManifest,
    DiscoveryConfig,
    LlmsTxtConfig,
)
from agent_layer.django.errors import AgentErrorsMiddleware
from agent_layer.django.rate_limits import RateLimitsMiddleware
from agent_layer.django.views import llms_txt_urlpatterns, discovery_urlpatterns


# ── Test views ──────────────────────────────────────────────────────────

def ok_view(request):
    return JsonResponse({"status": "ok"})


def fail_view(request):
    raise AgentError(AgentErrorOptions(code="broken", message="It broke", status=500))


# URL patterns (used by ROOT_URLCONF)
_llms_config = LlmsTxtConfig(title="Test API", description="For testing")
_discovery_config = DiscoveryConfig(manifest=AIManifest(name="Test API"))

urlpatterns = [
    path("ok", ok_view),
    path("fail", fail_view),
    *llms_txt_urlpatterns(_llms_config),
    *discovery_urlpatterns(_discovery_config),
]


# ── Tests ───────────────────────────────────────────────────────────────

class TestAgentErrorsMiddleware(TestCase):
    def test_agent_error_returns_envelope(self):
        middleware = AgentErrorsMiddleware(lambda r: JsonResponse({}))
        factory = RequestFactory()
        request = factory.get("/fail")

        # Simulate process_exception
        resp = middleware.process_exception(request, AgentError(
            AgentErrorOptions(code="broken", message="It broke", status=500)
        ))
        self.assertEqual(resp.status_code, 500)
        import json
        data = json.loads(resp.content)
        self.assertEqual(data["error"]["code"], "broken")
        self.assertTrue(data["error"]["is_retriable"])

    def test_404_returns_envelope(self):
        from django.http import HttpResponseNotFound
        middleware = AgentErrorsMiddleware(lambda r: HttpResponseNotFound())
        factory = RequestFactory()
        request = factory.get("/nonexistent")

        resp = middleware(request)
        self.assertEqual(resp.status_code, 404)
        import json
        data = json.loads(resp.content)
        self.assertEqual(data["error"]["code"], "not_found")


class TestRateLimitsMiddleware(TestCase):
    def test_rate_limit_headers(self):
        middleware = RateLimitsMiddleware(lambda r: JsonResponse({"ok": True}))
        factory = RequestFactory()
        request = factory.get("/ok")

        resp = middleware(request)
        self.assertEqual(resp["X-RateLimit-Limit"], "5")

    def test_rate_limit_429(self):
        middleware = RateLimitsMiddleware(lambda r: JsonResponse({"ok": True}))
        factory = RequestFactory()

        # Exhaust the limit
        for _ in range(5):
            middleware(factory.get("/ok"))

        resp = middleware(factory.get("/ok"))
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Retry-After", resp)


class TestLlmsTxtViews(TestCase):
    def test_llms_txt(self):
        resp = self.client.get("/llms.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"# Test API", resp.content)


class TestDiscoveryViews(TestCase):
    def test_well_known_ai(self):
        resp = self.client.get("/.well-known/ai")
        self.assertEqual(resp.status_code, 200)
        import json
        data = json.loads(resp.content)
        self.assertEqual(data["name"], "Test API")

    def test_json_ld(self):
        resp = self.client.get("/json-ld")
        self.assertEqual(resp.status_code, 200)
        import json
        data = json.loads(resp.content)
        self.assertEqual(data["@type"], "WebAPI")
