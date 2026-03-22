"""Agent traffic analytics — detect AI agent requests and collect telemetry.

Records each agent request and flushes batches to a configurable endpoint
(e.g. LightLayer dashboard) or a local callback.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from pydantic import BaseModel

logger = logging.getLogger("agent_layer.analytics")

# ── Known Agent User-Agent patterns ─────────────────────────────────────

_AGENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ChatGPT-User", re.IGNORECASE), "ChatGPT"),
    (re.compile(r"GPTBot", re.IGNORECASE), "GPTBot"),
    (re.compile(r"Google-Extended", re.IGNORECASE), "Google-Extended"),
    (re.compile(r"Googlebot", re.IGNORECASE), "Googlebot"),
    (re.compile(r"Bingbot", re.IGNORECASE), "Bingbot"),
    (re.compile(r"ClaudeBot", re.IGNORECASE), "ClaudeBot"),
    (re.compile(r"Claude-Web", re.IGNORECASE), "Claude-Web"),
    (re.compile(r"Anthropic", re.IGNORECASE), "Anthropic"),
    (re.compile(r"PerplexityBot", re.IGNORECASE), "PerplexityBot"),
    (re.compile(r"Cohere-AI", re.IGNORECASE), "Cohere"),
    (re.compile(r"YouBot", re.IGNORECASE), "YouBot"),
    (re.compile(r"CCBot", re.IGNORECASE), "CCBot"),
    (re.compile(r"Bytespider", re.IGNORECASE), "Bytespider"),
    (re.compile(r"Applebot", re.IGNORECASE), "Applebot"),
    (re.compile(r"Meta-ExternalAgent", re.IGNORECASE), "Meta-ExternalAgent"),
    (re.compile(r"AI2Bot", re.IGNORECASE), "AI2Bot"),
    (re.compile(r"Diffbot", re.IGNORECASE), "Diffbot"),
    (re.compile(r"Amazonbot", re.IGNORECASE), "Amazonbot"),
]


def detect_agent(user_agent: str | None) -> str | None:
    """Detect an AI agent from a User-Agent string. Returns agent name or None."""
    if not user_agent:
        return None
    for pattern, name in _AGENT_PATTERNS:
        if pattern.search(user_agent):
            return name
    return None


# ── Types ───────────────────────────────────────────────────────────────


class AgentEvent(BaseModel):
    """A single agent traffic event."""

    agent: str
    user_agent: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    timestamp: str
    content_type: str | None = None
    response_size: int | None = None


class AnalyticsConfig(BaseModel):
    """Configuration for agent traffic analytics."""

    endpoint: str | None = None
    api_key: str | None = None
    on_event: Callable[[AgentEvent], Any] | None = None
    buffer_size: int = 50
    flush_interval_seconds: float = 30.0
    track_all: bool = False
    detect_agent: Callable[[str], str | None] | None = None

    model_config = {"arbitrary_types_allowed": True}


# ── Event Buffer ────────────────────────────────────────────────────────


@dataclass
class EventBuffer:
    """Buffers agent events and flushes to a remote endpoint in batches."""

    endpoint: str | None = None
    api_key: str | None = None
    on_event: Callable[[AgentEvent], Any] | None = None
    buffer_size: int = 50
    flush_interval_seconds: float = 30.0

    _buffer: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)

    @property
    def pending(self) -> int:
        return len(self._buffer)

    def push(self, event: AgentEvent) -> None:
        if self.on_event:
            self.on_event(event)

        if self.endpoint:
            self._buffer.append(event.model_dump(mode="json"))
            if len(self._buffer) >= self.buffer_size:
                asyncio.ensure_future(self.flush())

    async def flush(self) -> None:
        if not self._buffer or not self.endpoint:
            return

        batch = self._buffer[:]
        self._buffer.clear()

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    self.endpoint,
                    json={"events": batch},
                    headers=headers,
                )
        except Exception:
            # Re-queue on failure (cap at 3x buffer to prevent memory leak)
            if len(self._buffer) < self.buffer_size * 3:
                self._buffer = batch + self._buffer
            logger.warning("Failed to flush %d analytics events", len(batch), exc_info=True)

    def start_flush_timer(self) -> None:
        """Start periodic flush task. Call once when the app starts."""
        if self._task or not self.endpoint:
            return

        async def _periodic_flush() -> None:
            while True:
                await asyncio.sleep(self.flush_interval_seconds)
                await self.flush()

        self._task = asyncio.ensure_future(_periodic_flush())

    async def shutdown(self) -> None:
        """Stop the flush timer and flush remaining events."""
        if self._task:
            self._task.cancel()
            self._task = None
        await self.flush()


# ── Analytics Instance ──────────────────────────────────────────────────


@dataclass
class AnalyticsInstance:
    """Framework-agnostic analytics instance."""

    buffer: EventBuffer
    config: AnalyticsConfig
    detect: Callable[[str | None], str | None]

    def record(self, event: AgentEvent) -> None:
        self.buffer.push(event)

    async def flush(self) -> None:
        await self.buffer.flush()

    async def shutdown(self) -> None:
        await self.buffer.shutdown()


def build_agent_event(
    agent: str | None,
    user_agent: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    content_type: str | None = None,
    response_size: int | None = None,
) -> AgentEvent:
    """Build an AgentEvent — framework-agnostic helper."""
    return AgentEvent(
        agent=agent or "unknown",
        user_agent=user_agent,
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=round(duration_ms, 2),
        timestamp=datetime.now(timezone.utc).isoformat(),
        content_type=content_type,
        response_size=response_size,
    )


def create_analytics(config: AnalyticsConfig) -> AnalyticsInstance:
    """Create an analytics instance. Framework adapters wrap this to create middleware."""
    buffer = EventBuffer(
        endpoint=config.endpoint,
        api_key=config.api_key,
        on_event=config.on_event,
        buffer_size=config.buffer_size,
        flush_interval_seconds=config.flush_interval_seconds,
    )

    if config.detect_agent:
        custom = config.detect_agent

        def _detect(ua: str | None) -> str | None:
            return custom(ua) if ua else None
    else:
        _detect = detect_agent

    return AnalyticsInstance(buffer=buffer, config=config, detect=_detect)
