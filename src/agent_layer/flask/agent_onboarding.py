"""Agent Onboarding blueprint and auth middleware for Flask."""

from __future__ import annotations

from flask import Blueprint, jsonify, make_response, request

from agent_layer.agent_onboarding import (
    OnboardingConfig,
    RegistrationRequest,
    create_onboarding_handler,
)
from agent_layer.async_utils import run_async_in_sync


def _get_client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def agent_onboarding_blueprint(config: OnboardingConfig) -> Blueprint:
    """Create a Flask blueprint with POST /agent/register."""
    bp = Blueprint("agent_onboarding", __name__)
    handler = create_onboarding_handler(config)

    @bp.route("/agent/register", methods=["POST"])
    def register_agent():
        body = request.get_json(force=True)
        reg = RegistrationRequest(
            agent_id=body.get("agent_id", ""),
            agent_name=body.get("agent_name", ""),
            agent_provider=body.get("agent_provider", ""),
            identity_token=body.get("identity_token"),
            metadata=body.get("metadata"),
        )
        ip = _get_client_ip()
        result = run_async_in_sync(handler.handle_register(reg, ip))
        return make_response(jsonify(result.body), result.status)

    return bp


def agent_onboarding_auth_middleware(config: OnboardingConfig):
    """Create a Flask before_request handler that returns 401 for unauthenticated agent requests."""
    handler = create_onboarding_handler(config)

    def before_request():
        headers: dict[str, str | None] = {}
        for k, v in request.headers:
            headers[k.lower()] = v

        if handler.should_return_401(request.path, headers):
            return make_response(jsonify(handler.get_auth_required_response()), 401)
        return None

    return before_request
