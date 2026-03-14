"""Tests for error envelope formatting."""

from agent_layer.errors import AgentError, format_error, not_found_error, rate_limit_error
from agent_layer.types import AgentErrorOptions


class TestFormatError:
    def test_basic_error(self):
        envelope = format_error(AgentErrorOptions(code="bad_request", message="Invalid input", status=400))
        assert envelope.type == "invalid_request_error"
        assert envelope.code == "bad_request"
        assert envelope.status == 400
        assert envelope.is_retriable is False

    def test_500_is_retriable(self):
        envelope = format_error(AgentErrorOptions(code="internal", message="Oops", status=500))
        assert envelope.is_retriable is True

    def test_429_is_retriable(self):
        envelope = format_error(AgentErrorOptions(code="limit", message="Slow down", status=429))
        assert envelope.is_retriable is True

    def test_custom_type(self):
        envelope = format_error(AgentErrorOptions(code="x", message="y", type="custom_error"))
        assert envelope.type == "custom_error"

    def test_optional_fields(self):
        envelope = format_error(AgentErrorOptions(
            code="x", message="y", status=400,
            retry_after=30, param="email", docs_url="https://docs.example.com",
        ))
        assert envelope.retry_after == 30
        assert envelope.param == "email"
        assert envelope.docs_url == "https://docs.example.com"

    def test_unknown_status_defaults_to_api_error(self):
        envelope = format_error(AgentErrorOptions(code="x", message="y", status=418))
        assert envelope.type == "api_error"


class TestAgentError:
    def test_exception(self):
        err = AgentError(AgentErrorOptions(code="not_found", message="Gone", status=404))
        assert err.status == 404
        assert str(err) == "Gone"

    def test_to_dict(self):
        err = AgentError(AgentErrorOptions(code="x", message="y", status=500))
        d = err.to_dict()
        assert "error" in d
        assert d["error"]["code"] == "x"


class TestHelpers:
    def test_not_found_error(self):
        envelope = not_found_error()
        assert envelope.status == 404
        assert envelope.code == "not_found"

    def test_rate_limit_error(self):
        envelope = rate_limit_error(60)
        assert envelope.status == 429
        assert envelope.retry_after == 60
        assert envelope.is_retriable is True
