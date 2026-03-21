"""Tests for structured error envelopes."""

from agent_layer.core.errors import (
    AgentError,
    AgentErrorOptions,
    format_error,
    not_found_error,
    rate_limit_error,
)


class TestFormatError:
    def test_basic_error(self):
        envelope = format_error(
            AgentErrorOptions(code="test_error", message="Something went wrong")
        )
        assert envelope.code == "test_error"
        assert envelope.message == "Something went wrong"
        assert envelope.status == 500
        assert envelope.type == "api_error"
        assert envelope.is_retriable is True  # 500 is retriable

    def test_custom_type(self):
        envelope = format_error(
            AgentErrorOptions(
                code="custom",
                message="Custom error",
                type="custom_type",
                status=418,
            )
        )
        assert envelope.type == "custom_type"
        assert envelope.status == 418

    def test_400_type(self):
        envelope = format_error(
            AgentErrorOptions(code="bad", message="Bad request", status=400)
        )
        assert envelope.type == "invalid_request_error"
        assert envelope.is_retriable is False

    def test_401_type(self):
        envelope = format_error(
            AgentErrorOptions(code="auth", message="Unauthorized", status=401)
        )
        assert envelope.type == "authentication_error"

    def test_403_type(self):
        envelope = format_error(
            AgentErrorOptions(code="perm", message="Forbidden", status=403)
        )
        assert envelope.type == "permission_error"

    def test_404_type(self):
        envelope = format_error(
            AgentErrorOptions(code="nf", message="Not found", status=404)
        )
        assert envelope.type == "not_found_error"

    def test_422_type(self):
        envelope = format_error(
            AgentErrorOptions(code="val", message="Validation error", status=422)
        )
        assert envelope.type == "validation_error"

    def test_429_type(self):
        envelope = format_error(
            AgentErrorOptions(code="rl", message="Rate limited", status=429)
        )
        assert envelope.type == "rate_limit_error"
        assert envelope.is_retriable is True

    def test_retry_after(self):
        envelope = format_error(
            AgentErrorOptions(
                code="rl",
                message="Rate limited",
                status=429,
                retry_after=30,
            )
        )
        assert envelope.retry_after == 30

    def test_param(self):
        envelope = format_error(
            AgentErrorOptions(
                code="invalid",
                message="Invalid param",
                status=400,
                param="email",
            )
        )
        assert envelope.param == "email"

    def test_docs_url(self):
        envelope = format_error(
            AgentErrorOptions(
                code="err",
                message="See docs",
                docs_url="https://docs.example.com/errors/err",
            )
        )
        assert envelope.docs_url == "https://docs.example.com/errors/err"

    def test_to_dict(self):
        envelope = format_error(
            AgentErrorOptions(code="test", message="Test", status=400)
        )
        d = envelope.to_dict()
        assert d["code"] == "test"
        assert d["message"] == "Test"
        assert d["status"] == 400
        assert "retry_after" not in d
        assert "param" not in d

    def test_to_dict_with_optionals(self):
        envelope = format_error(
            AgentErrorOptions(
                code="test",
                message="Test",
                status=429,
                retry_after=60,
                param="x",
                docs_url="https://docs.example.com",
            )
        )
        d = envelope.to_dict()
        assert d["retry_after"] == 60
        assert d["param"] == "x"
        assert d["docs_url"] == "https://docs.example.com"

    def test_explicit_not_retriable(self):
        envelope = format_error(
            AgentErrorOptions(
                code="err",
                message="Permanent",
                status=500,
                is_retriable=False,
            )
        )
        assert envelope.is_retriable is False


class TestAgentError:
    def test_exception(self):
        err = AgentError(
            AgentErrorOptions(code="test", message="Test error", status=400)
        )
        assert str(err) == "Test error"
        assert err.status == 400
        assert err.envelope.code == "test"

    def test_to_json(self):
        err = AgentError(
            AgentErrorOptions(code="test", message="Test error", status=400)
        )
        j = err.to_json()
        assert "error" in j
        assert j["error"]["code"] == "test"
        assert j["error"]["status"] == 400

    def test_is_exception(self):
        err = AgentError(
            AgentErrorOptions(code="test", message="Test", status=500)
        )
        assert isinstance(err, Exception)


class TestConvenienceErrors:
    def test_not_found_default(self):
        envelope = not_found_error()
        assert envelope.status == 404
        assert envelope.code == "not_found"
        assert "not found" in envelope.message.lower()

    def test_not_found_custom_message(self):
        envelope = not_found_error("User not found")
        assert envelope.message == "User not found"

    def test_rate_limit(self):
        envelope = rate_limit_error(30)
        assert envelope.status == 429
        assert envelope.code == "rate_limit_exceeded"
        assert envelope.is_retriable is True
        assert envelope.retry_after == 30
