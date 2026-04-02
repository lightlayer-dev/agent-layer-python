"""Tests for the framework-agnostic error handler."""

from __future__ import annotations

from agent_layer.error_handler import (
    build_error_envelope,
    build_error_response,
    build_not_found_response,
)
from agent_layer.errors import AgentError
from agent_layer.types import AgentErrorOptions


class TestBuildErrorEnvelope:
    def test_agent_error_returns_its_envelope(self):
        err = AgentError(AgentErrorOptions(code="rate_limit", message="Too many requests", status=429))
        envelope = build_error_envelope(err)
        assert envelope.code == "rate_limit"
        assert envelope.status == 429

    def test_generic_error_returns_internal_error(self):
        err = RuntimeError("something broke")
        envelope = build_error_envelope(err)
        assert envelope.code == "internal_error"
        assert envelope.status == 500

    def test_error_with_status_attr(self):
        err = Exception("not found")
        err.status = 404  # type: ignore
        envelope = build_error_envelope(err)
        assert envelope.status == 404


class TestBuildErrorResponse:
    def test_json_response_for_agent(self):
        err = RuntimeError("oops")
        result = build_error_response(err, accept="application/json")
        assert result.is_json is True
        assert result.status == 500
        assert "error" in result.body

    def test_html_response_for_browser(self):
        err = RuntimeError("oops")
        result = build_error_response(err, accept="text/html")
        assert result.is_json is False
        assert "<!DOCTYPE html>" in result.body

    def test_retry_after_header(self):
        err = AgentError(AgentErrorOptions(code="rate_limit", message="Too many requests", status=429, retry_after=60))
        result = build_error_response(err)
        assert result.headers.get("Retry-After") == "60"

    def test_bot_user_agent_gets_json(self):
        err = RuntimeError("fail")
        result = build_error_response(err, user_agent="python-requests/2.28")
        assert result.is_json is True


class TestBuildNotFoundResponse:
    def test_returns_404(self):
        result = build_not_found_response("GET", "/missing", accept="application/json")
        assert result.status == 404
        assert result.is_json is True

    def test_html_for_browser(self):
        result = build_not_found_response("GET", "/missing", accept="text/html")
        assert result.is_json is False
        assert "not_found" in result.body
