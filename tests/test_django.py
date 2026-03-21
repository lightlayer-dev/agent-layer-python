"""Tests for Django adapter."""

import django
from django.conf import settings

# Configure Django settings before importing anything else
if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={},
        ROOT_URLCONF="tests.test_django",
        MIDDLEWARE=["agent_layer.django.AgentLayerMiddleware"],
        AGENT_LAYER={},
        SECRET_KEY="test-secret-key",
    )
    django.setup()

import pytest
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.test import RequestFactory

from agent_layer.core.a2a import A2AAgentCard, A2AConfig, A2ASkill
from agent_layer.core.agents_txt import AgentsTxtConfig, AgentsTxtRule, Permission
from agent_layer.core.discovery import AIManifest, DiscoveryConfig
from agent_layer.core.errors import AgentError, AgentErrorOptions
from agent_layer.core.llms_txt import LlmsTxtConfig
from agent_layer.django.middleware import AgentLayerMiddleware


def _make_middleware(**agent_layer_config) -> AgentLayerMiddleware:
    """Create middleware with a passthrough get_response."""
    settings.AGENT_LAYER = agent_layer_config

    def get_response(request: HttpRequest) -> HttpResponse:
        return HttpResponse("OK")

    return AgentLayerMiddleware(get_response)


class TestAgentsTxt:
    def test_serves_agents_txt(self):
        middleware = _make_middleware(
            agents_txt=AgentsTxtConfig(
                rules=[AgentsTxtRule(agent="*", permission=Permission.ALLOW, paths=["/"])]
            )
        )
        factory = RequestFactory()
        request = factory.get("/agents.txt")
        response = middleware(request)
        assert response.status_code == 200
        assert b"User-agent: *" in response.content
        assert response["Content-Type"] == "text/plain"


class TestLlmsTxt:
    def test_serves_llms_txt(self):
        middleware = _make_middleware(
            llms_txt=LlmsTxtConfig(title="Test API", description="A test")
        )
        factory = RequestFactory()
        response = middleware(factory.get("/llms.txt"))
        assert response.status_code == 200
        assert b"# Test API" in response.content

    def test_serves_llms_full_txt(self):
        middleware = _make_middleware(llms_txt=LlmsTxtConfig(title="Test API"))
        factory = RequestFactory()
        response = middleware(factory.get("/llms-full.txt"))
        assert response.status_code == 200
        assert b"# Test API" in response.content


class TestDiscovery:
    def test_well_known_ai(self):
        middleware = _make_middleware(
            discovery=DiscoveryConfig(manifest=AIManifest(name="Test API"))
        )
        factory = RequestFactory()
        response = middleware(factory.get("/.well-known/ai"))
        assert response.status_code == 200
        import json
        data = json.loads(response.content)
        assert data["name"] == "Test API"

    def test_json_ld(self):
        middleware = _make_middleware(
            discovery=DiscoveryConfig(manifest=AIManifest(name="Test API"))
        )
        factory = RequestFactory()
        response = middleware(factory.get("/.well-known/ai/json-ld"))
        assert response.status_code == 200
        import json
        data = json.loads(response.content)
        assert data["@type"] == "WebAPI"


class TestA2A:
    def test_agent_card(self):
        middleware = _make_middleware(
            a2a=A2AConfig(
                card=A2AAgentCard(
                    name="TestAgent",
                    url="https://agent.example.com",
                    skills=[A2ASkill(id="s1", name="Skill 1")],
                )
            )
        )
        factory = RequestFactory()
        response = middleware(factory.get("/.well-known/agent.json"))
        assert response.status_code == 200
        import json
        data = json.loads(response.content)
        assert data["name"] == "TestAgent"


class TestErrorHandling:
    def test_agent_error_caught(self):
        def get_response(request: HttpRequest) -> HttpResponse:
            raise AgentError(
                AgentErrorOptions(code="test_fail", message="It broke", status=400)
            )

        settings.AGENT_LAYER = {}
        middleware = AgentLayerMiddleware(get_response)
        factory = RequestFactory()
        response = middleware(factory.get("/anything"))
        assert response.status_code == 400
        import json
        data = json.loads(response.content)
        assert data["error"]["code"] == "test_fail"


class TestPassthrough:
    def test_unmatched_routes_pass_through(self):
        middleware = _make_middleware(
            llms_txt=LlmsTxtConfig(title="Test")
        )
        factory = RequestFactory()
        response = middleware(factory.get("/hello"))
        assert response.status_code == 200
        assert response.content == b"OK"

    def test_no_config_passes_through(self):
        middleware = _make_middleware()
        factory = RequestFactory()
        response = middleware(factory.get("/agents.txt"))
        assert response.status_code == 200
        assert response.content == b"OK"
