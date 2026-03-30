"""Tests for Flask AG-UI streaming middleware."""

from __future__ import annotations

import json

import pytest
from flask import Flask

from agent_layer.flask.ag_ui import ag_ui_stream, AgUiMiddlewareOptions


@pytest.fixture
def app():
    """Create a minimal Flask app with AG-UI endpoint."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    def handler(request, emit):
        emit.run_started()
        emit.text_start()
        emit.text_delta("Hello from Flask!")
        emit.text_end()
        emit.run_finished()

    app.add_url_rule(
        "/api/agent",
        view_func=ag_ui_stream(handler),
        methods=["POST"],
    )
    return app


def test_ag_ui_stream_returns_sse(app):
    """Test that AG-UI stream returns SSE content type."""
    with app.test_client() as client:
        resp = client.post("/api/agent", json={"prompt": "test"})
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/event-stream")


def test_ag_ui_stream_events(app):
    """Test that AG-UI stream emits correct event sequence."""
    with app.test_client() as client:
        resp = client.post("/api/agent", json={"prompt": "test"})
        data = resp.get_data(as_text=True)

        # Should contain the expected event types
        assert "event: RUN_STARTED" in data
        assert "event: TEXT_MESSAGE_START" in data
        assert "event: TEXT_MESSAGE_CONTENT" in data
        assert "event: TEXT_MESSAGE_END" in data
        assert "event: RUN_FINISHED" in data

        # Should contain the text delta
        assert "Hello from Flask!" in data


def test_ag_ui_stream_sse_headers(app):
    """Test SSE headers are set correctly."""
    with app.test_client() as client:
        resp = client.post("/api/agent", json={"prompt": "test"})
        assert resp.headers.get("Cache-Control") == "no-cache, no-transform"
        assert resp.headers.get("X-Accel-Buffering") == "no"


def test_ag_ui_stream_thread_id_from_body(app):
    """Test that threadId is extracted from request body."""

    def handler(request, emit):
        emit.run_started()
        emit.run_finished()

    test_app = Flask(__name__)
    test_app.config["TESTING"] = True
    test_app.add_url_rule(
        "/api/agent",
        view_func=ag_ui_stream(handler),
        methods=["POST"],
    )

    with test_app.test_client() as client:
        resp = client.post("/api/agent", json={"threadId": "my-thread-123"})
        data = resp.get_data(as_text=True)

        # Parse the RUN_STARTED event to check threadId
        for line in data.split("\n"):
            if line.startswith("data: ") and "RUN_STARTED" in line:
                event_data = json.loads(line[6:])
                assert event_data["threadId"] == "my-thread-123"


def test_ag_ui_stream_error_handling():
    """Test that handler errors produce RUN_ERROR events."""

    def handler(request, emit):
        emit.run_started()
        raise ValueError("Something went wrong")

    test_app = Flask(__name__)
    test_app.config["TESTING"] = True
    test_app.add_url_rule(
        "/api/agent",
        view_func=ag_ui_stream(handler),
        methods=["POST"],
    )

    with test_app.test_client() as client:
        resp = client.post("/api/agent", json={"prompt": "test"})
        data = resp.get_data(as_text=True)
        assert "event: RUN_ERROR" in data
        assert "Something went wrong" in data


def test_ag_ui_stream_custom_error_handler():
    """Test custom error handler option."""
    custom_error_called = False

    def on_error(err, emit):
        nonlocal custom_error_called
        custom_error_called = True
        emit.run_error(f"Custom: {err}")

    def handler(request, emit):
        raise RuntimeError("Oops")

    opts = AgUiMiddlewareOptions(on_error=on_error)
    test_app = Flask(__name__)
    test_app.config["TESTING"] = True
    test_app.add_url_rule(
        "/api/agent",
        view_func=ag_ui_stream(handler, opts),
        methods=["POST"],
    )

    with test_app.test_client() as client:
        resp = client.post("/api/agent", json={})
        data = resp.get_data(as_text=True)
        assert custom_error_called
        assert "Custom: Oops" in data
