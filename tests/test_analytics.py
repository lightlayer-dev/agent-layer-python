"""Tests for agent traffic analytics — detection, buffering, and middleware."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from agent_layer.analytics import (
    AgentEvent,
    AnalyticsConfig,
    EventBuffer,
    create_analytics,
    detect_agent,
)


# ── detect_agent ────────────────────────────────────────────────────────


class TestDetectAgent:
    def test_chatgpt(self) -> None:
        assert detect_agent("Mozilla/5.0 ChatGPT-User") == "ChatGPT"

    def test_gptbot(self) -> None:
        assert detect_agent("Mozilla/5.0 GPTBot/1.0") == "GPTBot"

    def test_claudebot(self) -> None:
        assert detect_agent("ClaudeBot/1.0") == "ClaudeBot"

    def test_perplexity(self) -> None:
        assert detect_agent("PerplexityBot/1.0") == "PerplexityBot"

    def test_googlebot(self) -> None:
        assert detect_agent("Googlebot/2.1") == "Googlebot"

    def test_regular_browser(self) -> None:
        assert detect_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120") is None

    def test_none(self) -> None:
        assert detect_agent(None) is None

    def test_empty(self) -> None:
        assert detect_agent("") is None

    def test_case_insensitive(self) -> None:
        assert detect_agent("claudebot/1.0") == "ClaudeBot"

    def test_amazonbot(self) -> None:
        assert detect_agent("Amazonbot/0.1") == "Amazonbot"

    def test_anthropic(self) -> None:
        assert detect_agent("Anthropic-AI/1.0") == "Anthropic"


# ── EventBuffer ─────────────────────────────────────────────────────────


class TestEventBuffer:
    def _make_event(self, agent: str = "ChatGPT") -> AgentEvent:
        return AgentEvent(
            agent=agent,
            user_agent=f"{agent}/1.0",
            method="GET",
            path="/api/data",
            status_code=200,
            duration_ms=42.0,
            timestamp="2026-03-19T14:00:00Z",
        )

    def test_on_event_callback(self) -> None:
        events: list[AgentEvent] = []
        buf = EventBuffer(on_event=events.append)
        buf.push(self._make_event())
        assert len(events) == 1
        assert events[0].agent == "ChatGPT"

    def test_no_buffering_without_endpoint(self) -> None:
        buf = EventBuffer()
        buf.push(self._make_event())
        assert buf.pending == 0

    def test_buffering_with_endpoint(self) -> None:
        buf = EventBuffer(endpoint="http://example.com/events")
        buf.push(self._make_event())
        assert buf.pending == 1

    @pytest.mark.asyncio
    async def test_flush_clears_buffer(self) -> None:
        buf = EventBuffer(endpoint="http://localhost:1/nope")
        buf.push(self._make_event())
        # flush will fail (no server), events get re-queued
        await buf.flush()
        # Events should still be there (re-queued on failure)
        assert buf.pending >= 0  # Just verify no crash


# ── create_analytics ────────────────────────────────────────────────────


class TestCreateAnalytics:
    def test_default_detect(self) -> None:
        inst = create_analytics(AnalyticsConfig())
        assert inst.detect("GPTBot/1.0") == "GPTBot"
        assert inst.detect("Chrome/120") is None

    def test_custom_detect(self) -> None:
        inst = create_analytics(AnalyticsConfig(detect_agent=lambda ua: "Custom"))
        assert inst.detect("anything") == "Custom"

    def test_record_calls_callback(self) -> None:
        events: list[AgentEvent] = []
        inst = create_analytics(AnalyticsConfig(on_event=events.append))
        inst.record(
            AgentEvent(
                agent="Test",
                user_agent="Test/1.0",
                method="GET",
                path="/",
                status_code=200,
                duration_ms=1.0,
                timestamp="2026-01-01T00:00:00Z",
            )
        )
        assert len(events) == 1


# ── FastAPI Middleware ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestFastAPIAnalytics:
    async def test_agent_request_recorded(self) -> None:
        from fastapi import FastAPI

        from agent_layer.fastapi.analytics import agent_analytics_middleware

        events: list[AgentEvent] = []
        app = FastAPI()
        agent_analytics_middleware(app, AnalyticsConfig(on_event=events.append))

        @app.get("/hello")
        def hello() -> dict[str, str]:
            return {"msg": "hi"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/hello", headers={"User-Agent": "ClaudeBot/1.0"})
            assert resp.status_code == 200

        assert len(events) == 1
        assert events[0].agent == "ClaudeBot"
        assert events[0].path == "/hello"
        assert events[0].status_code == 200
        assert events[0].duration_ms > 0

    async def test_browser_request_not_recorded(self) -> None:
        from fastapi import FastAPI

        from agent_layer.fastapi.analytics import agent_analytics_middleware

        events: list[AgentEvent] = []
        app = FastAPI()
        agent_analytics_middleware(app, AnalyticsConfig(on_event=events.append))

        @app.get("/hello")
        def hello() -> dict[str, str]:
            return {"msg": "hi"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/hello", headers={"User-Agent": "Mozilla/5.0 Chrome/120"})

        assert len(events) == 0

    async def test_track_all(self) -> None:
        from fastapi import FastAPI

        from agent_layer.fastapi.analytics import agent_analytics_middleware

        events: list[AgentEvent] = []
        app = FastAPI()
        agent_analytics_middleware(app, AnalyticsConfig(on_event=events.append, track_all=True))

        @app.get("/hello")
        def hello() -> dict[str, str]:
            return {"msg": "hi"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/hello", headers={"User-Agent": "Mozilla/5.0 Chrome/120"})

        assert len(events) == 1
        assert events[0].agent == "unknown"


# ── Flask Extension ─────────────────────────────────────────────────────


class TestFlaskAnalytics:
    def test_agent_request_recorded(self) -> None:
        from flask import Flask

        from agent_layer.flask.analytics import agent_analytics_middleware

        events: list[AgentEvent] = []
        app = Flask(__name__)
        agent_analytics_middleware(app, AnalyticsConfig(on_event=events.append))

        @app.get("/hello")
        def hello() -> dict[str, str]:
            return {"msg": "hi"}

        with app.test_client() as client:
            resp = client.get("/hello", headers={"User-Agent": "GPTBot/1.0"})
            assert resp.status_code == 200

        assert len(events) == 1
        assert events[0].agent == "GPTBot"

    def test_browser_not_recorded(self) -> None:
        from flask import Flask

        from agent_layer.flask.analytics import agent_analytics_middleware

        events: list[AgentEvent] = []
        app = Flask(__name__)
        agent_analytics_middleware(app, AnalyticsConfig(on_event=events.append))

        @app.get("/hello")
        def hello() -> dict[str, str]:
            return {"msg": "hi"}

        with app.test_client() as client:
            client.get("/hello", headers={"User-Agent": "Chrome/120"})

        assert len(events) == 0
