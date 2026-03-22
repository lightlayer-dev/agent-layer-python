"""Tests for AG-UI event encoding and emitter."""

from __future__ import annotations

import json

from agent_layer.ag_ui import (
    AG_UI_HEADERS,
    AgUiEmitter,
    CustomEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageStartEvent,
    encode_event,
    encode_events,
)


def test_encode_event_format():
    event = RunStartedEvent(thread_id="t1", run_id="r1", timestamp=1000)
    encoded = encode_event(event)
    assert encoded.startswith("event: RUN_STARTED\n")
    assert "data: " in encoded
    data = json.loads(encoded.split("data: ")[1].strip())
    assert data["type"] == "RUN_STARTED"
    assert data["threadId"] == "t1"
    assert data["runId"] == "r1"
    assert data["timestamp"] == 1000


def test_encode_events_multiple():
    events = [
        RunStartedEvent(thread_id="t1", run_id="r1", timestamp=1000),
        TextMessageStartEvent(message_id="m1", role="assistant", timestamp=1001),
    ]
    encoded = encode_events(events)
    assert encoded.count("event: ") == 2
    assert "RUN_STARTED" in encoded
    assert "TEXT_MESSAGE_START" in encoded


def test_encode_camel_case():
    event = TextMessageContentEvent(message_id="m1", delta="hello", timestamp=1000)
    encoded = encode_event(event)
    data = json.loads(encoded.split("data: ")[1].strip())
    assert "messageId" in data
    assert "message_id" not in data


def test_emitter_text_flow():
    chunks: list[str] = []
    emitter = AgUiEmitter(chunks.append, thread_id="t1", run_id="r1")

    emitter.run_started()
    mid = emitter.text_start()
    emitter.text_delta("Hello ")
    emitter.text_delta("world!")
    emitter.text_end()
    emitter.run_finished()

    assert len(chunks) == 6
    assert "RUN_STARTED" in chunks[0]
    assert "TEXT_MESSAGE_START" in chunks[1]
    assert "TEXT_MESSAGE_CONTENT" in chunks[2]
    assert "Hello " in chunks[2]
    assert "TEXT_MESSAGE_CONTENT" in chunks[3]
    assert "world!" in chunks[3]
    assert "TEXT_MESSAGE_END" in chunks[4]
    assert "RUN_FINISHED" in chunks[5]


def test_emitter_text_message_convenience():
    chunks: list[str] = []
    emitter = AgUiEmitter(chunks.append, thread_id="t1", run_id="r1")

    mid = emitter.text_message("Hello world!", role="system")
    assert len(chunks) == 3
    assert "TEXT_MESSAGE_START" in chunks[0]
    assert "system" in chunks[0]
    assert "TEXT_MESSAGE_CONTENT" in chunks[1]
    assert "TEXT_MESSAGE_END" in chunks[2]


def test_emitter_tool_call_flow():
    chunks: list[str] = []
    emitter = AgUiEmitter(chunks.append)

    tid = emitter.tool_call_start("search")
    emitter.tool_call_args('{"query": "hello"}')
    emitter.tool_call_end()
    emitter.tool_call_result('["result1", "result2"]')

    assert len(chunks) == 4
    assert "TOOL_CALL_START" in chunks[0]
    assert "search" in chunks[0]
    assert "TOOL_CALL_ARGS" in chunks[1]
    assert "TOOL_CALL_END" in chunks[2]
    assert "TOOL_CALL_RESULT" in chunks[3]


def test_emitter_state():
    chunks: list[str] = []
    emitter = AgUiEmitter(chunks.append)

    emitter.state_snapshot({"count": 42})
    emitter.state_delta([{"op": "replace", "path": "/count", "value": 43}])

    assert len(chunks) == 2
    assert "STATE_SNAPSHOT" in chunks[0]
    assert "42" in chunks[0]
    assert "STATE_DELTA" in chunks[1]


def test_emitter_custom():
    chunks: list[str] = []
    emitter = AgUiEmitter(chunks.append)

    emitter.custom("progress", {"percent": 75})

    assert len(chunks) == 1
    assert "CUSTOM" in chunks[0]
    assert "progress" in chunks[0]


def test_emitter_error():
    chunks: list[str] = []
    emitter = AgUiEmitter(chunks.append)

    emitter.run_error("Something went wrong", code="TIMEOUT")

    assert "RUN_ERROR" in chunks[0]
    assert "Something went wrong" in chunks[0]
    assert "TIMEOUT" in chunks[0]


def test_emitter_step_lifecycle():
    chunks: list[str] = []
    emitter = AgUiEmitter(chunks.append)

    emitter.step_started("reasoning")
    emitter.step_finished("reasoning")

    assert "STEP_STARTED" in chunks[0]
    assert "reasoning" in chunks[0]
    assert "STEP_FINISHED" in chunks[1]


def test_emitter_auto_generates_ids():
    chunks: list[str] = []
    emitter = AgUiEmitter(chunks.append)

    assert emitter.thread_id  # auto-generated UUID
    assert emitter.run_id


def test_emitter_auto_timestamps():
    chunks: list[str] = []
    emitter = AgUiEmitter(chunks.append)

    emitter.run_started()
    data = json.loads(chunks[0].split("data: ")[1].strip())
    assert "timestamp" in data
    assert isinstance(data["timestamp"], int)


def test_ag_ui_headers():
    assert AG_UI_HEADERS["Content-Type"] == "text/event-stream"
    assert "no-cache" in AG_UI_HEADERS["Cache-Control"]


def test_none_fields_excluded():
    event = RunStartedEvent(thread_id="t1", run_id="r1")
    encoded = encode_event(event)
    data = json.loads(encoded.split("data: ")[1].strip())
    # parentRunId should not be in the output since it's None
    assert "parentRunId" not in data
