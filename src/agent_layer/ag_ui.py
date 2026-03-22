"""
AG-UI (Agent-User Interaction) Protocol — Server-Sent Events streaming.

Implements the server side of the AG-UI protocol (https://docs.ag-ui.com):
Framework-agnostic types and helpers for streaming agent responses
to CopilotKit, Google ADK, and other AG-UI-compatible frontends.

See: https://docs.ag-ui.com/concepts/events
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal, Optional, Union


# ── Event Types ──────────────────────────────────────────────────────────

AgUiRole = Literal["developer", "system", "assistant", "user", "tool"]

AG_UI_HEADERS = {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # Disable nginx buffering
}


# ── Event dataclasses ────────────────────────────────────────────────────


@dataclass
class RunStartedEvent:
    thread_id: str
    run_id: str
    parent_run_id: Optional[str] = None
    timestamp: Optional[int] = None
    type: str = "RUN_STARTED"


@dataclass
class RunFinishedEvent:
    thread_id: str
    run_id: str
    result: Any = None
    timestamp: Optional[int] = None
    type: str = "RUN_FINISHED"


@dataclass
class RunErrorEvent:
    message: str
    code: Optional[str] = None
    timestamp: Optional[int] = None
    type: str = "RUN_ERROR"


@dataclass
class StepStartedEvent:
    step_name: str
    timestamp: Optional[int] = None
    type: str = "STEP_STARTED"


@dataclass
class StepFinishedEvent:
    step_name: str
    timestamp: Optional[int] = None
    type: str = "STEP_FINISHED"


@dataclass
class TextMessageStartEvent:
    message_id: str
    role: AgUiRole
    timestamp: Optional[int] = None
    type: str = "TEXT_MESSAGE_START"


@dataclass
class TextMessageContentEvent:
    message_id: str
    delta: str
    timestamp: Optional[int] = None
    type: str = "TEXT_MESSAGE_CONTENT"


@dataclass
class TextMessageEndEvent:
    message_id: str
    timestamp: Optional[int] = None
    type: str = "TEXT_MESSAGE_END"


@dataclass
class ToolCallStartEvent:
    tool_call_id: str
    tool_call_name: str
    parent_message_id: Optional[str] = None
    timestamp: Optional[int] = None
    type: str = "TOOL_CALL_START"


@dataclass
class ToolCallArgsEvent:
    tool_call_id: str
    delta: str
    timestamp: Optional[int] = None
    type: str = "TOOL_CALL_ARGS"


@dataclass
class ToolCallEndEvent:
    tool_call_id: str
    timestamp: Optional[int] = None
    type: str = "TOOL_CALL_END"


@dataclass
class ToolCallResultEvent:
    tool_call_id: str
    result: str
    timestamp: Optional[int] = None
    type: str = "TOOL_CALL_RESULT"


@dataclass
class StateSnapshotEvent:
    snapshot: dict[str, Any]
    timestamp: Optional[int] = None
    type: str = "STATE_SNAPSHOT"


@dataclass
class StateDeltaEvent:
    delta: list[Any]
    timestamp: Optional[int] = None
    type: str = "STATE_DELTA"


@dataclass
class CustomEvent:
    name: str
    value: Any
    timestamp: Optional[int] = None
    type: str = "CUSTOM"


AgUiEvent = Union[
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    StepStartedEvent,
    StepFinishedEvent,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    ToolCallStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    StateSnapshotEvent,
    StateDeltaEvent,
    CustomEvent,
]


# ── Encoder ──────────────────────────────────────────────────────────────


def _to_camel(s: str) -> str:
    """Convert snake_case to camelCase."""
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _event_to_dict(event: AgUiEvent) -> dict[str, Any]:
    """Convert an event dataclass to a JSON-serializable dict with camelCase keys."""
    result: dict[str, Any] = {}
    for k, v in event.__dict__.items():
        if v is None:
            continue
        result[_to_camel(k)] = v
    return result


def encode_event(event: AgUiEvent) -> str:
    """Encode an AG-UI event as a Server-Sent Events data line."""
    data = json.dumps(_event_to_dict(event))
    return f"event: {event.type}\ndata: {data}\n\n"


def encode_events(events: list[AgUiEvent]) -> str:
    """Encode multiple AG-UI events."""
    return "".join(encode_event(e) for e in events)


# ── Emitter ──────────────────────────────────────────────────────────────


class AgUiEmitter:
    """
    High-level AG-UI event emitter. Wraps a `write` callable and provides
    convenient methods for emitting structured SSE events.

    Usage::

        emitter = AgUiEmitter(lambda chunk: response.write(chunk))
        emitter.run_started()
        emitter.text_start()
        emitter.text_delta("Hello ")
        emitter.text_delta("world!")
        emitter.text_end()
        emitter.run_finished()
    """

    def __init__(
        self,
        write: Callable[[str], None],
        *,
        thread_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ):
        self._write = write
        self.thread_id = thread_id or str(uuid.uuid4())
        self.run_id = run_id or str(uuid.uuid4())
        self._current_message_id: Optional[str] = None
        self._current_tool_call_id: Optional[str] = None

    def emit(self, event: AgUiEvent) -> None:
        """Emit a raw event."""
        if event.timestamp is None:
            event.timestamp = int(time.time() * 1000)
        self._write(encode_event(event))

    # ── Lifecycle ──

    def run_started(self, parent_run_id: Optional[str] = None) -> None:
        self.emit(RunStartedEvent(
            thread_id=self.thread_id,
            run_id=self.run_id,
            parent_run_id=parent_run_id,
        ))

    def run_finished(self, result: Any = None) -> None:
        self.emit(RunFinishedEvent(
            thread_id=self.thread_id,
            run_id=self.run_id,
            result=result,
        ))

    def run_error(self, message: str, code: Optional[str] = None) -> None:
        self.emit(RunErrorEvent(message=message, code=code))

    def step_started(self, step_name: str) -> None:
        self.emit(StepStartedEvent(step_name=step_name))

    def step_finished(self, step_name: str) -> None:
        self.emit(StepFinishedEvent(step_name=step_name))

    # ── Text messages ──

    def text_start(
        self, role: AgUiRole = "assistant", message_id: Optional[str] = None
    ) -> str:
        self._current_message_id = message_id or str(uuid.uuid4())
        self.emit(TextMessageStartEvent(
            message_id=self._current_message_id, role=role
        ))
        return self._current_message_id

    def text_delta(self, delta: str, message_id: Optional[str] = None) -> None:
        mid = message_id or self._current_message_id
        if not mid:
            raise RuntimeError(
                "text_delta called without an active message. Call text_start() first."
            )
        self.emit(TextMessageContentEvent(message_id=mid, delta=delta))

    def text_end(self, message_id: Optional[str] = None) -> None:
        mid = message_id or self._current_message_id
        if not mid:
            raise RuntimeError(
                "text_end called without an active message. Call text_start() first."
            )
        self.emit(TextMessageEndEvent(message_id=mid))
        if mid == self._current_message_id:
            self._current_message_id = None

    def text_message(self, text: str, role: AgUiRole = "assistant") -> str:
        """Convenience: emit a complete text message (start + content + end)."""
        mid = str(uuid.uuid4())
        self.emit(TextMessageStartEvent(message_id=mid, role=role))
        self.emit(TextMessageContentEvent(message_id=mid, delta=text))
        self.emit(TextMessageEndEvent(message_id=mid))
        return mid

    # ── Tool calls ──

    def tool_call_start(
        self,
        tool_call_name: str,
        tool_call_id: Optional[str] = None,
        parent_message_id: Optional[str] = None,
    ) -> str:
        self._current_tool_call_id = tool_call_id or str(uuid.uuid4())
        self.emit(ToolCallStartEvent(
            tool_call_id=self._current_tool_call_id,
            tool_call_name=tool_call_name,
            parent_message_id=parent_message_id,
        ))
        return self._current_tool_call_id

    def tool_call_args(self, delta: str, tool_call_id: Optional[str] = None) -> None:
        tid = tool_call_id or self._current_tool_call_id
        if not tid:
            raise RuntimeError(
                "tool_call_args called without an active tool call. Call tool_call_start() first."
            )
        self.emit(ToolCallArgsEvent(tool_call_id=tid, delta=delta))

    def tool_call_end(self, tool_call_id: Optional[str] = None) -> None:
        tid = tool_call_id or self._current_tool_call_id
        if not tid:
            raise RuntimeError(
                "tool_call_end called without an active tool call. Call tool_call_start() first."
            )
        self.emit(ToolCallEndEvent(tool_call_id=tid))

    def tool_call_result(self, result: str, tool_call_id: Optional[str] = None) -> None:
        tid = tool_call_id or self._current_tool_call_id
        if not tid:
            raise RuntimeError(
                "tool_call_result called without an active tool call."
            )
        self.emit(ToolCallResultEvent(tool_call_id=tid, result=result))
        if tid == self._current_tool_call_id:
            self._current_tool_call_id = None

    # ── State ──

    def state_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.emit(StateSnapshotEvent(snapshot=snapshot))

    def state_delta(self, delta: list[Any]) -> None:
        self.emit(StateDeltaEvent(delta=delta))

    # ── Custom ──

    def custom(self, name: str, value: Any) -> None:
        self.emit(CustomEvent(name=name, value=value))
