"""Agent-friendly error handling middleware for Django."""

from __future__ import annotations


from django.http import JsonResponse

from agent_layer.errors import AgentError, format_error
from agent_layer.types import AgentErrorOptions


class AgentErrorsMiddleware:
    """Django middleware that catches exceptions and returns agent-friendly envelopes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Convert 404s to agent-friendly envelopes
        if response.status_code == 404:
            envelope = format_error(
                AgentErrorOptions(
                    code="not_found",
                    message=f"No route found for {request.method} {request.path}",
                    status=404,
                )
            )
            return JsonResponse(
                {"error": envelope.model_dump(exclude_none=True)},
                status=404,
            )

        return response

    def process_exception(self, request, exception):
        if isinstance(exception, AgentError):
            return JsonResponse(exception.to_dict(), status=exception.status)

        envelope = format_error(
            AgentErrorOptions(
                code="internal_error",
                message=str(exception) or "An unexpected error occurred.",
                status=500,
            )
        )
        return JsonResponse(
            {"error": envelope.model_dump(exclude_none=True)},
            status=500,
        )
