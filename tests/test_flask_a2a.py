"""Tests for Flask A2A Agent Card blueprint."""

from __future__ import annotations

from flask import Flask

from agent_layer.a2a import (
    A2AConfig,
    A2AAgentCard,
    A2ASkill,
    A2AProvider,
    A2ACapabilities,
    A2AAuthScheme,
)
from agent_layer.flask.a2a import a2a_blueprint


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


def _make_app(config: A2AConfig | None = None) -> Flask:
    app = Flask(__name__)
    bp = a2a_blueprint(config or _config())
    app.register_blueprint(bp)
    return app


def test_serves_agent_card():
    client = _make_app().test_client()
    res = client.get("/.well-known/agent.json")
    assert res.status_code == 200
    body = res.get_json()
    assert body["name"] == "test-agent"
    assert body["url"] == "https://example.com/agent"
    assert body["protocolVersion"] == "1.0.0"


def test_content_type_json():
    client = _make_app().test_client()
    res = client.get("/.well-known/agent.json")
    assert "application/json" in res.content_type


def test_cache_control_header():
    client = _make_app().test_client()
    res = client.get("/.well-known/agent.json")
    assert res.headers["Cache-Control"] == "public, max-age=3600"


def test_includes_all_skills():
    client = _make_app().test_client()
    res = client.get("/.well-known/agent.json")
    skills = res.get_json()["skills"]
    assert len(skills) == 2
    assert skills[0]["id"] == "search"
    assert skills[1]["id"] == "summarize"


def test_includes_provider_info():
    client = _make_app().test_client()
    res = client.get("/.well-known/agent.json")
    provider = res.get_json()["provider"]
    assert provider["organization"] == "LightLayer"
    assert provider["url"] == "https://lightlayer.dev"


def test_includes_capabilities():
    client = _make_app().test_client()
    res = client.get("/.well-known/agent.json")
    caps = res.get_json()["capabilities"]
    assert caps["streaming"] is False
    assert caps["pushNotifications"] is False


def test_includes_authentication():
    client = _make_app().test_client()
    res = client.get("/.well-known/agent.json")
    auth = res.get_json()["authentication"]
    assert auth["type"] == "apiKey"


def test_default_input_output_modes():
    client = _make_app().test_client()
    res = client.get("/.well-known/agent.json")
    body = res.get_json()
    assert body["defaultInputModes"] == ["text/plain"]
    assert body["defaultOutputModes"] == ["text/plain"]


def test_includes_description_and_version():
    client = _make_app().test_client()
    res = client.get("/.well-known/agent.json")
    body = res.get_json()
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
    client = _make_app(config).test_client()
    res = client.get("/.well-known/agent.json")
    assert res.status_code == 200
    body = res.get_json()
    assert body["name"] == "minimal"
