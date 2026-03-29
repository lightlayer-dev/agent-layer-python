"""Agent Onboarding — Self-registration via webhook-based credential provisioning.

Agents discover the registration endpoint through /.well-known/agent.json and /llms.txt,
POST to /agent/register with their identity, and receive credentials back. The middleware
forwards the request to the API owner's provisioning webhook and returns the result.
The middleware never stores credentials — it's a stateless facilitator.

Ported from the LightLayer TypeScript and Gateway Go implementations.

See: https://github.com/lightlayer-dev/gateway
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from agent_layer.types import AgentErrorOptions
from agent_layer.errors import format_error

# ── Types ────────────────────────────────────────────────────────────────

SUPPORTED_CREDENTIAL_TYPES = ("api_key", "oauth2_client_credentials", "bearer")

EXEMPT_PATHS = frozenset({
    "/agent/register",
    "/llms.txt",
    "/llms-full.txt",
    "/agents.txt",
    "/robots.txt",
})


@dataclass
class OnboardingConfig:
    """Configuration for the agent onboarding middleware."""

    provisioning_webhook: str
    """URL to POST agent registrations to (required)."""

    webhook_secret: str | None = None
    """HMAC-SHA256 secret for signing webhook calls. If empty, no signature is sent."""

    webhook_timeout_ms: int = 10_000
    """Timeout for webhook HTTP calls in ms. Default: 10000."""

    require_identity: bool = False
    """If true, agent must present identity_token to register."""

    allowed_providers: list[str] = field(default_factory=list)
    """If set, only these providers can register. Empty = allow all."""

    auth_docs: str | None = None
    """URL to auth documentation, included in 401 responses."""

    rate_limit_max: int | None = None
    """Max registrations per IP per window. None = no limit."""

    rate_limit_window_ms: int = 3_600_000
    """Window size in ms. Default: 3600000 (1 hour)."""


@dataclass
class RegistrationRequest:
    """The body an agent sends to POST /agent/register."""

    agent_id: str
    agent_name: str
    agent_provider: str
    identity_token: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class Credential:
    """Provisioned credentials in one of three formats."""

    type: Literal["api_key", "oauth2_client_credentials", "bearer"]
    # api_key fields
    token: str | None = None
    header: str | None = None
    # oauth2 fields
    client_id: str | None = None
    client_secret: str | None = None
    scopes: list[str] | None = None
    token_endpoint: str | None = None
    # bearer fields
    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
    expires_at: str | None = None


@dataclass
class RegistrationResponse:
    """Standardized response to a registration request."""

    status: Literal["provisioned", "rejected"]
    credentials: Credential | None = None
    reason: str | None = None


@dataclass
class WebhookRequest:
    """Sent to the API owner's provisioning webhook."""

    agent_id: str
    agent_name: str
    agent_provider: str
    identity_verified: bool
    request_ip: str
    timestamp: str  # ISO 8601


@dataclass
class AuthRequiredResponse:
    """Returned as 401 when an unauthenticated agent hits the API."""

    error: str = "auth_required"
    message: str = "This API requires authentication. Register to get credentials."
    register_url: str = "/agent/register"
    auth_docs: str | None = None
    supported_credential_types: list[str] = field(
        default_factory=lambda: list(SUPPORTED_CREDENTIAL_TYPES)
    )


@dataclass
class HandlerResult:
    """Result of a registration or auth check."""

    status: int
    body: dict[str, Any]


# ── Rate Limiting (in-memory sliding window) ─────────────────────────────

@dataclass
class _RateLimitWindow:
    count: int
    reset_at: float  # epoch seconds


# ── HMAC Helpers ─────────────────────────────────────────────────────────


def sign_webhook_payload(body: str, secret: str) -> str:
    """Compute HMAC-SHA256 of a payload using the given secret."""
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def verify_webhook_signature(body: str, secret: str, signature: str) -> bool:
    """Verify that a signature header matches the expected HMAC-SHA256."""
    expected = f"sha256={sign_webhook_payload(body, secret)}"
    if len(expected) != len(signature):
        return False
    return hmac.compare_digest(expected, signature)


# ── Handler Factory ──────────────────────────────────────────────────────


def _make_error(status: int, code: str, message: str) -> dict[str, Any]:
    envelope = format_error(AgentErrorOptions(
        status=status,
        code=code,
        message=message,
        is_retriable=status in (429, 502),
    ))
    return envelope.model_dump(exclude_none=True)


class OnboardingHandler:
    """Stateless agent onboarding handler.

    Usage::

        handler = OnboardingHandler(OnboardingConfig(
            provisioning_webhook="https://api.example.com/provision",
        ))

        # POST /agent/register
        result = await handler.handle_register(request_body, client_ip)

        # Check if 401 should be returned
        if handler.should_return_401(path, headers):
            return handler.get_auth_required_response()
    """

    def __init__(self, config: OnboardingConfig) -> None:
        self.config = config
        self._windows: dict[str, _RateLimitWindow] = {}

    def _check_rate_limit(self, ip: str) -> bool:
        if self.config.rate_limit_max is None:
            return True
        now = time.time()
        win = self._windows.get(ip)
        if win is None or now >= win.reset_at:
            self._windows[ip] = _RateLimitWindow(
                count=1,
                reset_at=now + self.config.rate_limit_window_ms / 1000,
            )
            return True
        if win.count >= self.config.rate_limit_max:
            return False
        win.count += 1
        return True

    async def _call_webhook(self, webhook_req: WebhookRequest) -> dict[str, Any]:
        body_str = json.dumps({
            "agent_id": webhook_req.agent_id,
            "agent_name": webhook_req.agent_name,
            "agent_provider": webhook_req.agent_provider,
            "identity_verified": webhook_req.identity_verified,
            "request_ip": webhook_req.request_ip,
            "timestamp": webhook_req.timestamp,
        })

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.config.webhook_secret:
            sig = sign_webhook_payload(body_str, self.config.webhook_secret)
            headers["X-Webhook-Signature"] = f"sha256={sig}"

        timeout_s = self.config.webhook_timeout_ms / 1000
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                self.config.provisioning_webhook,
                content=body_str,
                headers=headers,
            )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Webhook returned status {resp.status_code}: {resp.text[:200]}"
                )
            return resp.json()  # type: ignore[no-any-return]

    async def handle_register(
        self,
        body: RegistrationRequest,
        client_ip: str,
    ) -> HandlerResult:
        """Handle POST /agent/register."""

        # Rate limit check.
        if not self._check_rate_limit(client_ip):
            return HandlerResult(
                status=429,
                body=_make_error(
                    429,
                    "rate_limit_exceeded",
                    "Too many registration attempts. Try again later.",
                ),
            )

        # Validate required fields.
        if not body.agent_id:
            return HandlerResult(
                status=400,
                body=_make_error(400, "missing_field", "agent_id is required"),
            )
        if not body.agent_name:
            return HandlerResult(
                status=400,
                body=_make_error(400, "missing_field", "agent_name is required"),
            )
        if not body.agent_provider:
            return HandlerResult(
                status=400,
                body=_make_error(400, "missing_field", "agent_provider is required"),
            )

        # Check identity requirement.
        if self.config.require_identity and not body.identity_token:
            return HandlerResult(
                status=400,
                body=_make_error(
                    400,
                    "identity_required",
                    "This API requires an identity_token for registration",
                ),
            )

        # Check allowed providers.
        if self.config.allowed_providers:
            allowed = any(
                p.lower() == body.agent_provider.lower()
                for p in self.config.allowed_providers
            )
            if not allowed:
                return HandlerResult(
                    status=403,
                    body=_make_error(
                        403,
                        "provider_not_allowed",
                        f'Agent provider "{body.agent_provider}" is not allowed',
                    ),
                )

        # Build webhook request.
        webhook_req = WebhookRequest(
            agent_id=body.agent_id,
            agent_name=body.agent_name,
            agent_provider=body.agent_provider,
            identity_verified=bool(body.identity_token),
            request_ip=client_ip,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Call provisioning webhook.
        try:
            resp = await self._call_webhook(webhook_req)
        except Exception:
            return HandlerResult(
                status=502,
                body=_make_error(
                    502,
                    "webhook_error",
                    "Failed to provision credentials. Please try again later.",
                ),
            )

        status = 403 if resp.get("status") == "rejected" else 200
        return HandlerResult(status=status, body=resp)

    def should_return_401(
        self,
        path: str,
        headers: dict[str, str | None],
    ) -> bool:
        """Check if a request should get a 401 auth-required response."""
        if path.startswith("/.well-known/") or path in EXEMPT_PATHS:
            return False
        if headers.get("authorization"):
            return False
        if headers.get("x-api-key"):
            return False
        return True

    def get_auth_required_response(self) -> dict[str, Any]:
        """Get the standard 401 response body."""
        return {
            "error": "auth_required",
            "message": "This API requires authentication. Register to get credentials.",
            "register_url": "/agent/register",
            "auth_docs": self.config.auth_docs,
            "supported_credential_types": list(SUPPORTED_CREDENTIAL_TYPES),
        }


def create_onboarding_handler(config: OnboardingConfig) -> OnboardingHandler:
    """Factory function for creating an OnboardingHandler.

    Mirrors the TS API: ``createOnboardingHandler(config)``.
    """
    return OnboardingHandler(config)
