"""Tests for FastAPI A2A Agent Card route handler."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from agent_layer.a2a import (
    A2AConfig,
    A2AAgentCard,
    A2ASkill,
    A2AProvider,
    A2ACapabilities,
    A2AAuthScheme,
)
from agent_layer.fastapi.a2a import a2a_routes


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


def _make_app(config: A2AConfig | None = None) -> FastAPI:
    app = FastAPI()
    router = a2a_routes(config or _config())
    app.include_router(router)
    return app


@pytest.fixture
def config():
    return _config()


@pytest.mark.asyncio
async def test_serves_agent_card():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/.well-known/agent.json")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "test-agent"
    assert body["url"] == "https://example.com/agent"
    assert body["protocolVersion"] == "1.0.0"


@pytest.mark.asyncio
async def test_content_type_json():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/.well-known/agent.json")
    assert "application/json" in res.headers["content-type"]


@pytest.mark.asyncio
async def test_cache_control_header():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/.well-known/agent.json")
    assert res.headers["cache-control"] == "public, max-age=3600"


@pytest.mark.asyncio
async def test_includes_all_skills():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/.well-known/agent.json")
    skills = res.json()["skills"]
    assert len(skills) == 2
    assert skills[0]["id"] == "search"
    assert skills[1]["id"] == "summarize"


@pytest.mark.asyncio
async def test_includes_provider_info():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/.well-known/agent.json")
    provider = res.json()["provider"]
    assert provider["organization"] == "LightLayer"
    assert provider["url"] == "https://lightlayer.dev"


@pytest.mark.asyncio
async def test_includes_capabilities():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/.well-known/agent.json")
    caps = res.json()["capabilities"]
    assert caps["streaming"] is False
    assert caps["pushNotifications"] is False


@pytest.mark.asyncio
async def test_includes_authentication():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/.well-known/agent.json")
    auth = res.json()["authentication"]
    assert auth["type"] == "apiKey"


@pytest.mark.asyncio
async def test_default_input_output_modes():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/.well-known/agent.json")
    body = res.json()
    assert body["defaultInputModes"] == ["text/plain"]
    assert body["defaultOutputModes"] == ["text/plain"]


@pytest.mark.asyncio
async def test_includes_description_and_version():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/.well-known/agent.json")
    body = res.json()
    assert body["description"] == "A test agent for unit tests"
    assert body["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_minimal_config():
    """Minimal config with only required fields."""
    config = A2AConfig(
        card=A2AAgentCard(
            name="minimal",
            url="https://example.com",
            skills=[A2ASkill(id="s1", name="Skill", description="A skill")],
        )
    )
    app = _make_app(config)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/.well-known/agent.json")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "minimal"
    assert "provider" not in body or body.get("provider") is None
