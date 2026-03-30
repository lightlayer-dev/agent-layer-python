"""
AG-UI Streaming — Server-Sent Events streaming for CopilotKit.

Implements the AG-UI protocol (https://docs.ag-ui.com) for streaming
agent responses to CopilotKit and other AG-UI-compatible frontends.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class AgUiEventType(str, Enum):
    """AG-UI event types."""

    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"
    STEP_STARTED = "STEP_STARTED"
    STEP_FINISHED = "STEP_FINISHED"
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    STATE_DELTA = "STATE_DELTA"
    CUSTOM = "CUSTOM"


AG_UI_HEADERS = {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def encode_event(event_type: str, data: dict[str, Any]) -> str:
    """Encode a single AG-UI event as SSE format."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def encode_events(events: list[tuple[str, dict[str, Any]]]) -> str:
    """Encode multiple AG-UI events as SSE format."""
    return "".join(encode_event(t, d) for t, d in events)


class AgUiEmitter:
    """High-level event emitter for AG-UI streaming."""

    def __init__(
        self,
        write: Callable[[str], Any],
        thread_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        self._write = write
        self.thread_id = thread_id or str(uuid.uuid4())
        self.run_id = run_id or str(uuid.uuid4())
        self._current_message_id: str | None = None
        self._current_tool_call_id: str | None = None

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._write(encode_event(event_type, data))

    def run_started(self) -> None:
        self._emit(AgUiEventType.RUN_STARTED, {
            "threadId": self.thread_id,
            "runId": self.run_id,
        })

    def run_finished(self) -> None:
        self._emit(AgUiEventType.RUN_FINISHED, {
            "threadId": self.thread_id,
            "runId": self.run_id,
        })

    def run_error(self, message: str, code: str | None = None) -> None:
        data: dict[str, Any] = {
            "threadId": self.thread_id,
            "runId": self.run_id,
            "message": message,
        }
        if code:
            data["code"] = code
        self._emit(AgUiEventType.RUN_ERROR, data)

    def step_started(self, step_name: str) -> None:
        self._emit(AgUiEventType.STEP_STARTED, {
            "threadId": self.thread_id,
            "runId": self.run_id,
            "stepName": step_name,
        })

    def step_finished(self, step_name: str) -> None:
        self._emit(AgUiEventType.STEP_FINISHED, {
            "threadId": self.thread_id,
            "runId": self.run_id,
            "stepName": step_name,
        })

    def text_start(self, message_id: str | None = None, role: str = "assistant") -> None:
        self._current_message_id = message_id or str(uuid.uuid4())
        self._emit(AgUiEventType.TEXT_MESSAGE_START, {
            "messageId": self._current_message_id,
            "role": role,
        })

    def text_delta(self, content: str) -> None:
        self._emit(AgUiEventType.TEXT_MESSAGE_CONTENT, {
            "messageId": self._current_message_id,
            "delta": content,
        })

    def text_end(self) -> None:
        self._emit(AgUiEventType.TEXT_MESSAGE_END, {
            "messageId": self._current_message_id,
        })
        self._current_message_id = None

    def text_message(self, content: str, role: str = "assistant") -> None:
        """Convenience: emit start + content + end for a complete message."""
        self.text_start(role=role)
        self.text_delta(content)
        self.text_end()

    def tool_call_start(
        self, name: str, tool_call_id: str | None = None
    ) -> None:
        self._current_tool_call_id = tool_call_id or str(uuid.uuid4())
        self._emit(AgUiEventType.TOOL_CALL_START, {
            "toolCallId": self._current_tool_call_id,
            "toolCallName": name,
        })

    def tool_call_args(self, delta: str) -> None:
        self._emit(AgUiEventType.TOOL_CALL_ARGS, {
            "toolCallId": self._current_tool_call_id,
            "delta": delta,
        })

    def tool_call_end(self) -> None:
        self._emit(AgUiEventType.TOOL_CALL_END, {
            "toolCallId": self._current_tool_call_id,
        })

    def tool_call_result(self, result: str) -> None:
        self._emit(AgUiEventType.TOOL_CALL_RESULT, {
            "toolCallId": self._current_tool_call_id,
            "result": result,
        })
        self._current_tool_call_id = None

    def state_snapshot(self, state: dict[str, Any]) -> None:
        self._emit(AgUiEventType.STATE_SNAPSHOT, {
            "snapshot": state,
        })

    def state_delta(self, delta: list[dict[str, Any]]) -> None:
        self._emit(AgUiEventType.STATE_DELTA, {
            "delta": delta,
        })

    def custom(self, name: str, value: Any = None) -> None:
        self._emit(AgUiEventType.CUSTOM, {
            "name": name,
            "value": value,
        })


def create_ag_ui_emitter(
    write: Callable[[str], Any],
    thread_id: str | None = None,
    run_id: str | None = None,
) -> AgUiEmitter:
    """Create an AG-UI emitter wrapping a write function."""
    return AgUiEmitter(write, thread_id=thread_id, run_id=run_id)
