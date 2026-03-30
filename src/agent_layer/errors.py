"""Agent-friendly error envelopes."""

from __future__ import annotations

from agent_layer.types import AgentErrorEnvelope, AgentErrorOptions

STATUS_TYPES: dict[int, str] = {
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
    return STATUS_TYPES.get(status, "api_error")


def format_error(opts: AgentErrorOptions) -> AgentErrorEnvelope:
    """Format an error into the standard agent-friendly envelope."""
    status = opts.status
    is_retriable = (
        opts.is_retriable if opts.is_retriable is not None else (status == 429 or status >= 500)
    )

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
    """Error that carries an agent-friendly envelope."""

    def __init__(self, opts: AgentErrorOptions) -> None:
        super().__init__(opts.message)
        self.envelope = format_error(opts)

    @property
    def status(self) -> int:
        return self.envelope.status

    def to_dict(self) -> dict:
        return {"error": self.envelope.model_dump(exclude_none=True)}


def not_found_error(message: str = "The requested resource was not found.") -> AgentErrorEnvelope:
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
