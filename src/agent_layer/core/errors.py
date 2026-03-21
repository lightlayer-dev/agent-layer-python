"""
Structured error envelopes for AI agents.

Provides a consistent error format that agents can parse and act on,
including retry logic, parameter identification, and documentation links.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_STATUS_TYPES: dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    409: "conflict_error",
    422: "validation_error",
    429: "rate_limit_error",
    500: "api_error",
}


def _type_for_status(status: int) -> str:
    return _STATUS_TYPES.get(status, "api_error")


@dataclass
class AgentErrorOptions:
    """Options for creating an agent error."""

    code: str
    message: str
    type: str | None = None
    status: int = 500
    is_retriable: bool | None = None
    retry_after: int | None = None
    param: str | None = None
    docs_url: str | None = None


@dataclass
class AgentErrorEnvelope:
    """The structured error envelope returned to agents."""

    type: str
    code: str
    message: str
    status: int
    is_retriable: bool
    retry_after: int | None = None
    param: str | None = None
    docs_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        result: dict[str, Any] = {
            "type": self.type,
            "code": self.code,
            "message": self.message,
            "status": self.status,
            "is_retriable": self.is_retriable,
        }
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        if self.param is not None:
            result["param"] = self.param
        if self.docs_url is not None:
            result["docs_url"] = self.docs_url
        return result


def format_error(opts: AgentErrorOptions) -> AgentErrorEnvelope:
    """Format error options into a structured error envelope."""
    status = opts.status
    is_retriable = opts.is_retriable
    if is_retriable is None:
        is_retriable = status == 429 or status >= 500

    return AgentErrorEnvelope(
        type=opts.type or _type_for_status(status),
        code=opts.code,
        message=opts.message,
        status=status,
        is_retriable=is_retriable,
        retry_after=opts.retry_after,
        param=opts.param,
        docs_url=opts.docs_url,
    )


class AgentError(Exception):
    """Custom exception that carries a structured error envelope."""

    def __init__(self, opts: AgentErrorOptions) -> None:
        super().__init__(opts.message)
        self.envelope = format_error(opts)

    @property
    def status(self) -> int:
        return self.envelope.status

    def to_json(self) -> dict[str, Any]:
        """Return the error in the standard envelope format."""
        return {"error": self.envelope.to_dict()}


def not_found_error(
    message: str = "The requested resource was not found.",
) -> AgentErrorEnvelope:
    """Create a 404 Not Found error envelope."""
    return format_error(AgentErrorOptions(code="not_found", message=message, status=404))


def rate_limit_error(retry_after: int) -> AgentErrorEnvelope:
    """Create a 429 Rate Limit error envelope."""
    return format_error(
        AgentErrorOptions(
            code="rate_limit_exceeded",
            message="Too many requests. Please retry after the specified time.",
            status=429,
            is_retriable=True,
            retry_after=retry_after,
        )
    )
