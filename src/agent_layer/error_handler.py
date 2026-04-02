"""Framework-agnostic error handling helpers.

These functions extract the duplicated business logic from FastAPI/Flask/Django
agent-errors into a single, testable module.

Mirrors the TypeScript error-handler.ts in agent-layer-ts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agent_layer.errors import AgentError, format_error
from agent_layer.types import AgentErrorEnvelope, AgentErrorOptions


def _prefers_json(accept: str | None = None, user_agent: str | None = None) -> bool:
    """Determine whether the client prefers JSON (i.e., is an agent)."""
    a = accept or ""
    if "application/json" in a:
        return True
    if "text/html" in a:
        return False
    ua = user_agent or ""
    if not ua or re.search(r"bot|crawl|spider|agent|curl|httpie|python|node|go-http", ua, re.I):
        return True
    return False


def _render_html_error(envelope: AgentErrorEnvelope) -> str:
    """Render an error envelope as a simple HTML page."""
    return (
        f"<!DOCTYPE html>\n"
        f'<html lang="en">\n'
        f'<head><meta charset="utf-8"><title>Error {envelope.status}</title></head>\n'
        f"<body>\n"
        f"  <h1>{envelope.status} — {envelope.code}</h1>\n"
        f"  <p>{envelope.message}</p>\n"
        f"</body>\n"
        f"</html>"
    )


def build_error_envelope(err: Exception) -> AgentErrorEnvelope:
    """Build an error envelope from an arbitrary Exception.

    If the error is an AgentError, uses its existing envelope;
    otherwise, creates a generic internal_error envelope.
    """
    if isinstance(err, AgentError):
        return err.envelope

    status = getattr(err, "status", None) or getattr(err, "status_code", None) or 500
    return format_error(
        AgentErrorOptions(
            code="internal_error",
            message=str(err) or "An unexpected error occurred.",
            status=status,
        )
    )


@dataclass
class ErrorResponseAction:
    """Result of processing an error for response."""

    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    is_json: bool = True


def build_error_response(
    err: Exception,
    accept: str | None = None,
    user_agent: str | None = None,
) -> ErrorResponseAction:
    """Build a complete error response action from an error and request headers.

    The caller only needs to apply the result to their framework's response object.
    """
    envelope = build_error_envelope(err)
    headers: dict[str, str] = {}

    if envelope.retry_after is not None:
        headers["Retry-After"] = str(envelope.retry_after)

    is_json = _prefers_json(accept, user_agent)

    return ErrorResponseAction(
        status=envelope.status,
        headers=headers,
        body={"error": envelope.model_dump()} if is_json else _render_html_error(envelope),
        is_json=is_json,
    )


def build_not_found_response(
    method: str,
    path: str,
    accept: str | None = None,
    user_agent: str | None = None,
) -> ErrorResponseAction:
    """Build a 404 not-found response action."""
    envelope = format_error(
        AgentErrorOptions(
            code="not_found",
            message=f"No route matches {method} {path}",
            status=404,
        )
    )

    is_json = _prefers_json(accept, user_agent)

    return ErrorResponseAction(
        status=404,
        headers={},
        body={"error": envelope.model_dump()} if is_json else _render_html_error(envelope),
        is_json=is_json,
    )
