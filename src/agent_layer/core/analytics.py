"""
Analytics — Agent detection via User-Agent, event buffering, pluggable flush.

Detects known AI agent patterns in User-Agent strings and records
events for analytics. Events are buffered and flushed to a remote
endpoint or processed via a local callback.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


# Known AI agent User-Agent patterns
_AGENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ChatGPT", re.compile(r"ChatGPT", re.IGNORECASE)),
    ("GPTBot", re.compile(r"GPTBot", re.IGNORECASE)),
    ("Google-Extended", re.compile(r"Google-Extended", re.IGNORECASE)),
    ("Googlebot", re.compile(r"Googlebot", re.IGNORECASE)),
    ("Bingbot", re.compile(r"Bingbot", re.IGNORECASE)),
    ("ClaudeBot", re.compile(r"ClaudeBot", re.IGNORECASE)),
    ("Claude-Web", re.compile(r"Claude-Web", re.IGNORECASE)),
    ("Anthropic", re.compile(r"Anthropic", re.IGNORECASE)),
    ("PerplexityBot", re.compile(r"PerplexityBot", re.IGNORECASE)),
    ("Cohere", re.compile(r"Cohere", re.IGNORECASE)),
    ("YouBot", re.compile(r"YouBot", re.IGNORECASE)),
    ("CCBot", re.compile(r"CCBot", re.IGNORECASE)),
    ("Bytespider", re.compile(r"Bytespider", re.IGNORECASE)),
    ("Applebot", re.compile(r"Applebot", re.IGNORECASE)),
    ("Meta-ExternalAgent", re.compile(r"Meta-ExternalAgent", re.IGNORECASE)),
    ("AI2Bot", re.compile(r"AI2Bot", re.IGNORECASE)),
    ("Diffbot", re.compile(r"Diffbot", re.IGNORECASE)),
    ("Amazonbot", re.compile(r"Amazonbot", re.IGNORECASE)),
]


def detect_agent(user_agent: str | None) -> str | None:
    """Detect if a User-Agent string belongs to a known AI agent.

    Returns the agent name or None if no match.
    """
    if not user_agent:
        return None
    for name, pattern in _AGENT_PATTERNS:
        if pattern.search(user_agent):
            return name
    return None


@dataclass
class AgentEvent:
    """A single analytics event for an agent request."""

    agent: str
    user_agent: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    timestamp: str
    content_type: str | None = None
    response_size: int | None = None


@dataclass
class AnalyticsConfig:
    """Configuration for the analytics system."""

    endpoint: str | None = None
    api_key: str | None = None
    on_event: Callable[[AgentEvent], None] | None = None
    buffer_size: int = 50
    flush_interval_ms: int = 30_000
    track_all: bool = False
    detect_agent: Callable[[str | None], str | None] | None = None


class EventBuffer:
    """Buffered event storage with pluggable flush to remote endpoint."""

    def __init__(self, config: AnalyticsConfig) -> None:
        self._config = config
        self._buffer: list[AgentEvent] = []

    @property
    def pending(self) -> int:
        return len(self._buffer)

    def record(self, event: AgentEvent) -> None:
        """Record an event. Invokes on_event callback immediately, buffers for remote flush."""
        if self._config.on_event:
            self._config.on_event(event)

        if self._config.endpoint:
            self._buffer.append(event)
            if len(self._buffer) >= self._config.buffer_size:
                self.flush_sync()

    def flush_sync(self) -> list[AgentEvent]:
        """Flush buffered events and return them. In production, these would be sent to endpoint."""
        if not self._buffer:
            return []
        batch = list(self._buffer)
        self._buffer.clear()
        return batch

    def shutdown(self) -> list[AgentEvent]:
        """Flush remaining events and shut down."""
        return self.flush_sync()


def create_analytics(config: AnalyticsConfig) -> dict[str, Any]:
    """Create an analytics instance with the given configuration.

    Returns a dict with record, flush, shutdown functions and config/buffer references.
    """
    buffer = EventBuffer(config)
    detector = config.detect_agent or detect_agent

    return {
        "record": buffer.record,
        "flush": buffer.flush_sync,
        "shutdown": buffer.shutdown,
        "buffer": buffer,
        "detect": detector,
        "config": config,
    }
