"""Tests for Django adapter modules — auth, meta, unified_discovery, mcp, identity."""

import base64
import json
import time

import django
from django.conf import settings

# Minimal Django config — must include settings & routes for both test files
# since whichever runs first sets ROOT_URLCONF for the process.
if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        ROOT_URLCONF="tests.test_django_adapters",
        MIDDLEWARE=[
            "agent_layer.django.errors.AgentErrorsMiddleware",
            "agent_layer.django.rate_limits.RateLimitsMiddleware",
        ],
        AGENT_LAYER_RATE_LIMIT={"max": 5},
        AGENT_IDENTITY={
            "trusted_issuers": ["https://auth.example.com"],
            "audience": ["https://api.example.com"],
        },
        SECRET_KEY="test-secret",
    )
    django.setup()

from django.http import JsonResponse
from django.test import RequestFactory, TestCase
from django.urls import path

from agent_layer.errors import AgentError
from agent_layer.mcp import McpServerConfig
from agent_layer.types import (
    AgentAuthConfig,
    AgentErrorOptions,
    AIManifest,
    DiscoveryConfig,
    LlmsTxtConfig,
    RouteMetadata,
)
from agent_layer.unified_discovery import UnifiedDiscoveryConfig


def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    return f"{header.decode()}.{body.decode()}.sig"


# ── Shared views ──────────────────────────────────────────────────────

from agent_layer.django.auth import agent_auth_urlpatterns  # noqa: E402
from agent_layer.django.unified_discovery import unified_discovery_urlpatterns  # noqa: E402
from agent_layer.django.mcp import mcp_urlpatterns  # noqa: E402
from agent_layer.django.views import discovery_urlpatterns, llms_txt_urlpatterns  # noqa: E402

_auth_config = AgentAuthConfig(
    issuer="https://auth.example.com",
    token_url="https://auth.example.com/token",
    scopes={"read": "Read access"},
)

_discovery_config = UnifiedDiscoveryConfig(
    name="Test API",
    description="A test",
    url="https://api.example.com",
)

_mcp_config = McpServerConfig(
    name="test-api",
    routes=[RouteMetadata(method="GET", path="/api/items", summary="List items")],
)

# Shared views for test_django_integration compatibility
_llms_config = LlmsTxtConfig(title="Test API", description="For testing")
_basic_discovery_config = DiscoveryConfig(manifest=AIManifest(name="Test API"))


def ok_view(request):
    return JsonResponse({"status": "ok"})


def fail_view(request):
    raise AgentError(AgentErrorOptions(code="broken", message="It broke", status=500))


urlpatterns = [
    path("ok", ok_view),
    path("fail", fail_view),
    # Basic discovery/llms (for test_django_integration compatibility)
    *llms_txt_urlpatterns(_llms_config),
    *discovery_urlpatterns(_basic_discovery_config),
    # Extended modules
    *agent_auth_urlpatterns(_auth_config),
    *unified_discovery_urlpatterns(_discovery_config),
    *mcp_urlpatterns(_mcp_config),
]


# ── Tests ─────────────────────────────────────────────────────────────


class TestDjangoAuth(TestCase):
    def test_oauth_metadata(self):
        resp = self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["issuer"], "https://auth.example.com")
        self.assertIn("read", data["scopes_supported"])


class TestDjangoMeta(TestCase):
    def test_meta_headers(self):
        from agent_layer.django.meta import AgentMetaMiddleware

        middleware = AgentMetaMiddleware(lambda r: JsonResponse({"ok": True}))
        factory = RequestFactory()
        resp = middleware(factory.get("/ok"))
        self.assertEqual(resp["X-Agent-Meta"], "true")
        self.assertEqual(resp["X-Agent-Id-Attribute"], "data-agent-id")


class TestDjangoUnifiedDiscovery(TestCase):
    def test_well_known_ai_unified(self):
        """Test the unified discovery well-known/ai endpoint."""
        # unified_discovery registers as 'unified_well_known_ai'
        from django.urls import reverse

        resp = self.client.get(reverse("unified_well_known_ai"))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["name"], "Test API")

    def test_agents_txt(self):
        resp = self.client.get("/agents.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Test API", resp.content)

    def test_llms_txt_unified(self):
        """Test the unified llms.txt (registered under unified_ name)."""
        from django.urls import reverse

        resp = self.client.get(reverse("unified_llms_txt"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"# Test API", resp.content)


class TestDjangoMcp(TestCase):
    def test_initialize(self):
        resp = self.client.post(
            "/",
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["result"]["serverInfo"]["name"], "test-api")

    def test_tools_list(self):
        resp = self.client.post(
            "/",
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        tools = json.loads(resp.content)["result"]["tools"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "get_api_items")

    def test_delete_session(self):
        resp = self.client.delete("/")
        self.assertEqual(resp.status_code, 200)


class TestDjangoAgentIdentity(TestCase):
    def test_rejects_without_token(self):
        from agent_layer.django.agent_identity import AgentIdentityMiddleware

        middleware = AgentIdentityMiddleware(lambda r: JsonResponse({"ok": True}))
        factory = RequestFactory()
        resp = middleware(factory.get("/protected"))
        self.assertEqual(resp.status_code, 401)

    def test_accepts_valid_token(self):
        from agent_layer.django.agent_identity import AgentIdentityMiddleware

        now = int(time.time())
        token = _make_jwt({
            "iss": "https://auth.example.com",
            "sub": "agent-1",
            "aud": "https://api.example.com",
            "exp": now + 3600,
            "iat": now,
        })

        middleware = AgentIdentityMiddleware(lambda r: JsonResponse({"ok": True}))
        factory = RequestFactory()
        request = factory.get("/protected", HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = middleware(request)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(request.agent_identity.agent_id, "agent-1")
