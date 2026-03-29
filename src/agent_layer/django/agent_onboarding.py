"""Agent Onboarding URL patterns and auth middleware for Django."""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.urls import path

from agent_layer.agent_onboarding import (
    OnboardingConfig,
    RegistrationRequest,
    create_onboarding_handler,
)


def _get_client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def agent_onboarding_urlpatterns(config: OnboardingConfig) -> list:
    """Create Django URL patterns with POST /agent/register."""
    handler = create_onboarding_handler(config)

    async def register_view(request):
        if request.method != "POST":
            return JsonResponse({"error": "Method not allowed"}, status=405)

        body = json.loads(request.body)
        reg = RegistrationRequest(
            agent_id=body.get("agent_id", ""),
            agent_name=body.get("agent_name", ""),
            agent_provider=body.get("agent_provider", ""),
            identity_token=body.get("identity_token"),
            metadata=body.get("metadata"),
        )
        ip = _get_client_ip(request)
        result = await handler.handle_register(reg, ip)
        return JsonResponse(result.body, status=result.status)

    return [
        path("agent/register", register_view, name="agent_onboarding_register"),
    ]


# ── Exempt paths ─────────────────────────────────────────────────────────

_EXEMPT_PATHS = frozenset({
    "/agent/register",
    "/llms.txt",
    "/llms-full.txt",
    "/agents.txt",
    "/robots.txt",
})


class AgentOnboardingAuthMiddleware:
    """Django middleware that returns 401 for unauthenticated agent requests."""

    def __init__(self, get_response, *, config: OnboardingConfig):
        self.get_response = get_response
        self.handler = create_onboarding_handler(config)

    def __call__(self, request):
        headers: dict[str, str | None] = {}
        for key, value in request.META.items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").lower()
                headers[header_name] = value

        if self.handler.should_return_401(request.path, headers):
            return JsonResponse(self.handler.get_auth_required_response(), status=401)

        return self.get_response(request)
