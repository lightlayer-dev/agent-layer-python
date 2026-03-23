"""Tests for Django AG-UI streaming middleware."""

from __future__ import annotations

import json

import django
from django.conf import settings

# Configure minimal Django settings for testing
if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={},
        ROOT_URLCONF=__name__,
        SECRET_KEY="test-secret-key",
    )
    django.setup()

import pytest
from django.http import StreamingHttpResponse
from django.test import RequestFactory

from agent_layer.django.ag_ui import ag_ui_stream, AgUiMiddlewareOptions


@pytest.fixture
def rf():
    return RequestFactory()


def test_ag_ui_stream_returns_streaming_response(rf):
    """Test that AG-UI stream returns a StreamingHttpResponse."""
    def handler(request, emit):
        emit.run_started()
        emit.run_finished()

    view = ag_ui_stream(handler)
    request = rf.post("/api/agent", json.dumps({"prompt": "test"}), content_type="application/json")
    response = view(request)

    assert isinstance(response, StreamingHttpResponse)
    assert response["Content-Type"] == "text/event-stream"


def test_ag_ui_stream_events(rf):
    """Test that AG-UI stream emits correct event sequence."""
    def handler(request, emit):
        emit.run_started()
        emit.text_start()
        emit.text_delta("Hello from Django!")
        emit.text_end()
        emit.run_finished()

    view = ag_ui_stream(handler)
    request = rf.post("/api/agent", json.dumps({"prompt": "test"}), content_type="application/json")
    response = view(request)
    data = b"".join(response.streaming_content).decode()

    assert "event: RUN_STARTED" in data
    assert "event: TEXT_MESSAGE_START" in data
    assert "event: TEXT_MESSAGE_CONTENT" in data
    assert "event: TEXT_MESSAGE_END" in data
    assert "event: RUN_FINISHED" in data
    assert "Hello from Django!" in data


def test_ag_ui_stream_sse_headers(rf):
    """Test SSE headers are set correctly."""
    def handler(request, emit):
        emit.run_started()
        emit.run_finished()

    view = ag_ui_stream(handler)
    request = rf.post("/api/agent", json.dumps({}), content_type="application/json")
    response = view(request)

    assert response["Cache-Control"] == "no-cache, no-transform"
    assert response["X-Accel-Buffering"] == "no"


def test_ag_ui_stream_thread_id_from_body(rf):
    """Test that threadId is extracted from request body."""
    def handler(request, emit):
        emit.run_started()
        emit.run_finished()

    view = ag_ui_stream(handler)
    request = rf.post(
        "/api/agent",
        json.dumps({"threadId": "my-thread-456"}),
        content_type="application/json",
    )
    response = view(request)
    data = b"".join(response.streaming_content).decode()

    for line in data.split("\n"):
        if line.startswith("data: ") and "RUN_STARTED" in line:
            event_data = json.loads(line[6:])
            assert event_data["threadId"] == "my-thread-456"


def test_ag_ui_stream_error_handling(rf):
    """Test that handler errors produce RUN_ERROR events."""
    def handler(request, emit):
        emit.run_started()
        raise ValueError("Something went wrong")

    view = ag_ui_stream(handler)
    request = rf.post("/api/agent", json.dumps({}), content_type="application/json")
    response = view(request)
    data = b"".join(response.streaming_content).decode()

    assert "event: RUN_ERROR" in data
    assert "Something went wrong" in data


def test_ag_ui_stream_custom_error_handler(rf):
    """Test custom error handler option."""
    custom_called = False

    def on_error(err, emit):
        nonlocal custom_called
        custom_called = True
        emit.run_error(f"Custom: {err}")

    def handler(request, emit):
        raise RuntimeError("Oops")

    view = ag_ui_stream(handler, AgUiMiddlewareOptions(on_error=on_error))
    request = rf.post("/api/agent", json.dumps({}), content_type="application/json")
    response = view(request)
    data = b"".join(response.streaming_content).decode()

    assert custom_called
    assert "Custom: Oops" in data
