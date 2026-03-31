"""Tests for Django A2A Agent Card URL patterns."""

from __future__ import annotations

import django
from django.conf import settings

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

from django.test import RequestFactory

from agent_layer.a2a import (
    A2AConfig,
    A2AAgentCard,
    A2ASkill,
    A2AProvider,
    A2ACapabilities,
    A2AAuthScheme,
)
import json as _json

from agent_layer.django.a2a import a2a_urlpatterns


def _parse(response):
    """Parse Django JsonResponse content."""
    return _json.loads(response.content)


def _config() -> A2AConfig:
    return A2AConfig(
        card=A2AAgentCard(
            name="test-agent",
            url="https://example.com/agent",
            description="A test agent for unit tests",
            provider=A2AProvider(organization="LightLayer", url="https://lightlayer.dev"),
            version="1.0.0",
            capabilities=A2ACapabilities(streaming=False, push_notifications=False),
            authentication=A2AAuthScheme(type="apiKey", in_="header", name="X-Agent-Key"),
            skills=[
                A2ASkill(
                    id="search",
                    name="Web Search",
                    description="Search the web for information",
                    tags=["search", "web"],
                    examples=["Search for AI agent protocols"],
                ),
                A2ASkill(
                    id="summarize",
                    name="Summarize",
                    description="Summarize a document or URL",
                    tags=["nlp", "summarization"],
                ),
            ],
        )
    )


def _get_view(config: A2AConfig | None = None):
    """Get the agent card view function from URL patterns."""
    patterns = a2a_urlpatterns(config or _config())
    # The first pattern is the agent card view
    return patterns[0].callback


factory = RequestFactory()


def test_serves_agent_card():
    view = _get_view()
    request = factory.get("/.well-known/agent.json")
    res = view(request)
    assert res.status_code == 200
    body = _parse(res)
    assert body["name"] == "test-agent"
    assert body["url"] == "https://example.com/agent"
    assert body["protocolVersion"] == "1.0.0"


def test_content_type_json():
    view = _get_view()
    request = factory.get("/.well-known/agent.json")
    res = view(request)
    assert "application/json" in res["Content-Type"]


def test_cache_control_header():
    view = _get_view()
    request = factory.get("/.well-known/agent.json")
    res = view(request)
    assert res["Cache-Control"] == "public, max-age=3600"


def test_includes_all_skills():
    view = _get_view()
    request = factory.get("/.well-known/agent.json")
    res = view(request)
    skills = _parse(res)["skills"]
    assert len(skills) == 2
    assert skills[0]["id"] == "search"
    assert skills[1]["id"] == "summarize"


def test_includes_provider_info():
    view = _get_view()
    request = factory.get("/.well-known/agent.json")
    res = view(request)
    provider = _parse(res)["provider"]
    assert provider["organization"] == "LightLayer"
    assert provider["url"] == "https://lightlayer.dev"


def test_includes_capabilities():
    view = _get_view()
    request = factory.get("/.well-known/agent.json")
    res = view(request)
    caps = _parse(res)["capabilities"]
    assert caps["streaming"] is False
    assert caps["pushNotifications"] is False


def test_includes_authentication():
    view = _get_view()
    request = factory.get("/.well-known/agent.json")
    res = view(request)
    auth = _parse(res)["authentication"]
    assert auth["type"] == "apiKey"


def test_default_input_output_modes():
    view = _get_view()
    request = factory.get("/.well-known/agent.json")
    res = view(request)
    body = _parse(res)
    assert body["defaultInputModes"] == ["text/plain"]
    assert body["defaultOutputModes"] == ["text/plain"]


def test_includes_description_and_version():
    view = _get_view()
    request = factory.get("/.well-known/agent.json")
    res = view(request)
    body = _parse(res)
    assert body["description"] == "A test agent for unit tests"
    assert body["version"] == "1.0.0"


def test_minimal_config():
    config = A2AConfig(
        card=A2AAgentCard(
            name="minimal",
            url="https://example.com",
            skills=[A2ASkill(id="s1", name="Skill", description="A skill")],
        )
    )
    view = _get_view(config)
    request = factory.get("/.well-known/agent.json")
    res = view(request)
    assert res.status_code == 200
    body = _parse(res)
    assert body["name"] == "minimal"
