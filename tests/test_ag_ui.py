"""Tests for AG-UI streaming module."""

import json

from agent_layer.core.ag_ui import (
    AG_UI_HEADERS,
    AgUiEmitter,
    AgUiEventType,
    create_ag_ui_emitter,
    encode_event,
    encode_events,
)


class TestEncodeEvent:
    def test_format(self):
        result = encode_event("TEST", {"key": "value"})
        assert result.startswith("event: TEST\n")
        assert "data: " in result
        assert result.endswith("\n\n")

    def test_data_is_json(self):
        result = encode_event("TEST", {"key": "value"})
        data_line = result.split("\n")[1]
        data = json.loads(data_line.replace("data: ", ""))
        assert data["key"] == "value"


class TestEncodeEvents:
    def test_multiple(self):
        events = [("A", {"x": 1}), ("B", {"y": 2})]
        result = encode_events(events)
        assert "event: A\n" in result
        assert "event: B\n" in result


class TestAgUiEmitter:
    def test_text_message(self):
        chunks: list[str] = []
        emitter = create_ag_ui_emitter(lambda s: chunks.append(s))

        emitter.run_started()
        emitter.text_start()
        emitter.text_delta("Hello ")
        emitter.text_delta("world")
        emitter.text_end()
        emitter.run_finished()

        combined = "".join(chunks)
        assert "RUN_STARTED" in combined
        assert "TEXT_MESSAGE_START" in combined
        assert "TEXT_MESSAGE_CONTENT" in combined
        assert "TEXT_MESSAGE_END" in combined
        assert "RUN_FINISHED" in combined
        assert "Hello " in combined

    def test_tool_call(self):
        chunks: list[str] = []
        emitter = create_ag_ui_emitter(lambda s: chunks.append(s))

        emitter.tool_call_start("search")
        emitter.tool_call_args('{"q": "test"}')
        emitter.tool_call_end()
        emitter.tool_call_result("found 5 results")

        combined = "".join(chunks)
        assert "TOOL_CALL_START" in combined
        assert "TOOL_CALL_ARGS" in combined
        assert "TOOL_CALL_END" in combined
        assert "TOOL_CALL_RESULT" in combined

    def test_step_events(self):
        chunks: list[str] = []
        emitter = create_ag_ui_emitter(lambda s: chunks.append(s))

        emitter.step_started("processing")
        emitter.step_finished("processing")

        combined = "".join(chunks)
        assert "STEP_STARTED" in combined
        assert "STEP_FINISHED" in combined

    def test_state_events(self):
        chunks: list[str] = []
        emitter = create_ag_ui_emitter(lambda s: chunks.append(s))

        emitter.state_snapshot({"count": 0})
        emitter.state_delta([{"op": "replace", "path": "/count", "value": 1}])

        combined = "".join(chunks)
        assert "STATE_SNAPSHOT" in combined
        assert "STATE_DELTA" in combined

    def test_custom_event(self):
        chunks: list[str] = []
        emitter = create_ag_ui_emitter(lambda s: chunks.append(s))
        emitter.custom("my_event", {"data": 42})
        assert "CUSTOM" in "".join(chunks)

    def test_error_event(self):
        chunks: list[str] = []
        emitter = create_ag_ui_emitter(lambda s: chunks.append(s))
        emitter.run_error("Something went wrong")
        assert "RUN_ERROR" in "".join(chunks)

    def test_timestamps_added(self):
        chunks: list[str] = []
        emitter = create_ag_ui_emitter(lambda s: chunks.append(s))
        emitter.run_started()
        data = json.loads(chunks[0].split("data: ")[1].strip())
        assert "timestamp" in data

    def test_custom_ids(self):
        emitter = AgUiEmitter(lambda s: None, thread_id="t1", run_id="r1")
        assert emitter.thread_id == "t1"
        assert emitter.run_id == "r1"

    def test_text_message_convenience(self):
        chunks: list[str] = []
        emitter = create_ag_ui_emitter(lambda s: chunks.append(s))
        emitter.text_message("Hello world")
        combined = "".join(chunks)
        assert "TEXT_MESSAGE_START" in combined
        assert "TEXT_MESSAGE_CONTENT" in combined
        assert "TEXT_MESSAGE_END" in combined


class TestAgUiHeaders:
    def test_content_type(self):
        assert AG_UI_HEADERS["Content-Type"] == "text/event-stream"

    def test_no_cache(self):
        assert "no-cache" in AG_UI_HEADERS["Cache-Control"]
