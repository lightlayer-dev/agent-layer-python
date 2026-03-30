"""Tests for analytics module."""

from agent_layer.core.analytics import (
    AgentEvent,
    AnalyticsConfig,
    EventBuffer,
    create_analytics,
    detect_agent,
)


class TestDetectAgent:
    def test_chatgpt(self):
        assert detect_agent("Mozilla/5.0 ChatGPT-User") == "ChatGPT"

    def test_gptbot(self):
        assert detect_agent("GPTBot/1.0") == "GPTBot"

    def test_claudebot(self):
        assert detect_agent("ClaudeBot/1.0") == "ClaudeBot"

    def test_anthropic(self):
        assert detect_agent("Anthropic-AI/1.0") == "Anthropic"

    def test_perplexity(self):
        assert detect_agent("PerplexityBot/1.0") == "PerplexityBot"

    def test_bingbot(self):
        assert detect_agent("Bingbot/2.0") == "Bingbot"

    def test_unknown_agent(self):
        assert detect_agent("Mozilla/5.0 (Windows NT 10.0)") is None

    def test_none_agent(self):
        assert detect_agent(None) is None

    def test_empty_string(self):
        assert detect_agent("") is None

    def test_case_insensitive(self):
        assert detect_agent("chatgpt-user") == "ChatGPT"


class TestEventBuffer:
    def test_record_calls_on_event(self):
        events = []
        config = AnalyticsConfig(on_event=lambda e: events.append(e))
        buf = EventBuffer(config)
        event = AgentEvent(
            agent="GPTBot", user_agent="GPTBot/1.0",
            method="GET", path="/api", status_code=200,
            duration_ms=50, timestamp="2024-01-01T00:00:00Z",
        )
        buf.record(event)
        assert len(events) == 1
        assert events[0].agent == "GPTBot"

    def test_buffer_with_endpoint(self):
        config = AnalyticsConfig(endpoint="https://analytics.example.com", buffer_size=10)
        buf = EventBuffer(config)
        event = AgentEvent(
            agent="GPTBot", user_agent="GPTBot/1.0",
            method="GET", path="/api", status_code=200,
            duration_ms=50, timestamp="2024-01-01T00:00:00Z",
        )
        buf.record(event)
        assert buf.pending == 1

    def test_flush(self):
        config = AnalyticsConfig(endpoint="https://analytics.example.com")
        buf = EventBuffer(config)
        event = AgentEvent(
            agent="GPTBot", user_agent="GPTBot/1.0",
            method="GET", path="/api", status_code=200,
            duration_ms=50, timestamp="2024-01-01T00:00:00Z",
        )
        buf.record(event)
        batch = buf.flush_sync()
        assert len(batch) == 1
        assert buf.pending == 0

    def test_no_buffer_without_endpoint(self):
        config = AnalyticsConfig()
        buf = EventBuffer(config)
        event = AgentEvent(
            agent="GPTBot", user_agent="GPTBot/1.0",
            method="GET", path="/api", status_code=200,
            duration_ms=50, timestamp="2024-01-01T00:00:00Z",
        )
        buf.record(event)
        assert buf.pending == 0


class TestCreateAnalytics:
    def test_creates_instance(self):
        analytics = create_analytics(AnalyticsConfig())
        assert "record" in analytics
        assert "flush" in analytics
        assert "shutdown" in analytics
        assert "detect" in analytics

    def test_custom_detector(self):
        custom = lambda ua: "custom" if ua else None
        analytics = create_analytics(AnalyticsConfig(detect_agent=custom))
        assert analytics["detect"]("anything") == "custom"
