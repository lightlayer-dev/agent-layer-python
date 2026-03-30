"""
Agent Identity — SPIFFE ID parsing, JWT claims, authz policies, audit events.

Implements the IETF draft-klrc-aiagent-auth-00 specification for
agent identity verification with SPIFFE/WIMSE support.
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fnmatch import fnmatch
from typing import Any, Awaitable, Callable


@dataclass
class SpiffeId:
    """Parsed SPIFFE URI."""

    trust_domain: str
    path: str
    raw: str


@dataclass
class AgentIdentityClaims:
    """Extracted JWT claims for agent identity."""

    agent_id: str
    spiffe_id: SpiffeId | None = None
    issuer: str | None = None
    audience: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    expires_at: float | None = None
    issued_at: float | None = None
    delegated: bool = False
    delegated_by: str | None = None
    custom_claims: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentAuthzPolicy:
    """Authorization policy rule."""

    name: str
    agent_pattern: str | None = None
    trust_domains: list[str] | None = None
    required_scopes: list[str] | None = None
    methods: list[str] | None = None
    paths: list[str] | None = None
    allow_delegated: bool | None = None
    custom_evaluator: Callable[[AgentIdentityClaims, Any], bool] | None = None
    effect: str = "allow"  # "allow" or "deny"


@dataclass
class AgentIdentityConfig:
    """Configuration for agent identity verification."""

    trusted_issuers: list[str] = field(default_factory=list)
    audience: list[str] = field(default_factory=list)
    trusted_domains: list[str] = field(default_factory=list)
    clock_skew_seconds: int = 30
    max_lifetime_seconds: int = 3600
    policies: list[AgentAuthzPolicy] = field(default_factory=list)
    default_policy: str = "deny"  # "allow" or "deny"
    verify_token: Callable[[str], Awaitable[dict[str, Any]]] | None = None


@dataclass
class AuthzContext:
    """Context for authorization evaluation."""

    method: str
    path: str


@dataclass
class AuthzResult:
    """Result of authorization evaluation."""

    allowed: bool
    matched_policy: str | None = None
    denied_reason: str | None = None


@dataclass
class TokenValidationError:
    """Token validation error."""

    code: str
    message: str


@dataclass
class AgentIdentityAuditEvent:
    """Audit event for agent identity operations."""

    type: str = "agent_identity"
    timestamp: str = ""
    agent_id: str = ""
    spiffe_id: str | None = None
    issuer: str | None = None
    delegated: bool = False
    delegated_by: str | None = None
    scopes: list[str] = field(default_factory=list)
    method: str = ""
    path: str = ""
    authz_result: AuthzResult | None = None


# ── SPIFFE ID Parsing ────────────────────────────────────────────────────

_SPIFFE_RE = re.compile(r"^spiffe://([^/]+)(/.*)?$")


def parse_spiffe_id(uri: str) -> SpiffeId | None:
    """Parse a SPIFFE URI into its components."""
    m = _SPIFFE_RE.match(uri)
    if not m:
        return None
    return SpiffeId(
        trust_domain=m.group(1),
        path=m.group(2) or "",
        raw=uri,
    )


def is_spiffe_trusted(spiffe_id: SpiffeId, trusted_domains: list[str]) -> bool:
    """Check if a SPIFFE ID's trust domain is in the trusted list."""
    return spiffe_id.trust_domain in trusted_domains


# ── JWT Decoding ─────────────────────────────────────────────────────────

_KNOWN_CLAIMS = {
    "iss", "sub", "aud", "exp", "iat", "nbf", "jti",
    "scope", "scopes", "scp", "agent_id", "act",
}


def _base64url_decode(s: str) -> str:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s).decode()


def decode_jwt_claims(token: str) -> dict[str, Any] | None:
    """Decode JWT payload without verification (for claims extraction)."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        return json.loads(_base64url_decode(parts[1]))
    except Exception:
        return None


def extract_claims(payload: dict[str, Any]) -> AgentIdentityClaims:
    """Extract agent identity claims from a JWT payload."""
    agent_id = payload.get("agent_id") or payload.get("sub", "")

    # Parse SPIFFE ID from agent_id
    spiffe_id = parse_spiffe_id(agent_id) if agent_id else None

    # Extract scopes from various formats
    scopes: list[str] = []
    if "scope" in payload and isinstance(payload["scope"], str):
        scopes = payload["scope"].split()
    elif "scopes" in payload and isinstance(payload["scopes"], list):
        scopes = payload["scopes"]
    elif "scp" in payload and isinstance(payload["scp"], list):
        scopes = payload["scp"]

    # Extract audience as list
    aud = payload.get("aud", [])
    audience = [aud] if isinstance(aud, str) else list(aud)

    # Detect delegation via act claim
    act = payload.get("act")
    delegated = act is not None
    delegated_by = act.get("sub") if isinstance(act, dict) else None

    # Custom claims
    custom_claims = {k: v for k, v in payload.items() if k not in _KNOWN_CLAIMS}

    return AgentIdentityClaims(
        agent_id=agent_id,
        spiffe_id=spiffe_id,
        issuer=payload.get("iss"),
        audience=audience,
        scopes=scopes,
        expires_at=payload.get("exp"),
        issued_at=payload.get("iat"),
        delegated=delegated,
        delegated_by=delegated_by,
        custom_claims=custom_claims,
    )


# ── Claims Validation ────────────────────────────────────────────────────

def validate_claims(
    claims: AgentIdentityClaims,
    config: AgentIdentityConfig,
) -> TokenValidationError | None:
    """Validate agent identity claims against config."""
    # Check issuer
    if config.trusted_issuers and claims.issuer not in config.trusted_issuers:
        return TokenValidationError("untrusted_issuer", f"Untrusted issuer: {claims.issuer}")

    # Check audience
    if config.audience:
        if not any(a in config.audience for a in claims.audience):
            return TokenValidationError("invalid_audience", "Invalid audience")

    # Check expiration
    now = time.time()
    if claims.expires_at is not None:
        if now > claims.expires_at + config.clock_skew_seconds:
            return TokenValidationError("expired_token", "Token has expired")

    # Check max lifetime
    if claims.issued_at is not None and claims.expires_at is not None:
        lifetime = claims.expires_at - claims.issued_at
        if lifetime > config.max_lifetime_seconds:
            return TokenValidationError(
                "token_too_long_lived",
                f"Token lifetime {lifetime}s exceeds max {config.max_lifetime_seconds}s",
            )

    # Check SPIFFE trust domain
    if claims.spiffe_id and config.trusted_domains:
        if not is_spiffe_trusted(claims.spiffe_id, config.trusted_domains):
            return TokenValidationError(
                "untrusted_domain",
                f"Untrusted domain: {claims.spiffe_id.trust_domain}",
            )

    return None


# ── Authorization ────────────────────────────────────────────────────────

def evaluate_authz(
    claims: AgentIdentityClaims,
    context: AuthzContext,
    policies: list[AgentAuthzPolicy],
    default_policy: str = "deny",
) -> AuthzResult:
    """Evaluate authorization policies. First match wins."""
    for policy in policies:
        if not _policy_matches(claims, context, policy):
            continue

        if policy.effect == "deny":
            return AuthzResult(
                allowed=False,
                matched_policy=policy.name,
                denied_reason=f"Denied by policy: {policy.name}",
            )

        return AuthzResult(allowed=True, matched_policy=policy.name)

    # Default policy
    if default_policy == "allow":
        return AuthzResult(allowed=True)
    return AuthzResult(allowed=False, denied_reason="No matching policy (default deny)")


def _policy_matches(
    claims: AgentIdentityClaims,
    context: AuthzContext,
    policy: AgentAuthzPolicy,
) -> bool:
    """Check if a policy matches the current request."""
    # Agent pattern
    if policy.agent_pattern:
        if not fnmatch(claims.agent_id, policy.agent_pattern):
            return False

    # Trust domains
    if policy.trust_domains:
        if not claims.spiffe_id:
            return False
        if claims.spiffe_id.trust_domain not in policy.trust_domains:
            return False

    # Methods
    if policy.methods:
        if context.method.upper() not in [m.upper() for m in policy.methods]:
            return False

    # Paths
    if policy.paths:
        if not any(fnmatch(context.path, p) for p in policy.paths):
            return False

    # Delegation
    if policy.allow_delegated is not None:
        if claims.delegated and not policy.allow_delegated:
            return False

    # Required scopes
    if policy.required_scopes:
        if "*" not in claims.scopes:
            if not all(s in claims.scopes for s in policy.required_scopes):
                return False

    # Custom evaluator
    if policy.custom_evaluator:
        if not policy.custom_evaluator(claims, context):
            return False

    return True


# ── Audit Events ─────────────────────────────────────────────────────────

def build_audit_event(
    claims: AgentIdentityClaims,
    context: AuthzContext,
    authz_result: AuthzResult,
) -> AgentIdentityAuditEvent:
    """Generate an audit event for analytics."""
    return AgentIdentityAuditEvent(
        type="agent_identity",
        timestamp=datetime.now(timezone.utc).isoformat(),
        agent_id=claims.agent_id,
        spiffe_id=claims.spiffe_id.raw if claims.spiffe_id else None,
        issuer=claims.issuer,
        delegated=claims.delegated,
        delegated_by=claims.delegated_by,
        scopes=claims.scopes,
        method=context.method,
        path=context.path,
        authz_result=authz_result,
    )


# ── Identity Handler ─────────────────────────────────────────────────────

def _extract_bearer_token(header: str | None) -> str | None:
    """Extract token from a Bearer authorization header."""
    if not header:
        return None
    if header.startswith("Bearer "):
        return header[7:]
    return None


async def handle_require_identity(
    raw_header: str | None,
    config: AgentIdentityConfig,
    context: AuthzContext,
) -> dict[str, Any]:
    """Full identity verification flow.

    Returns {"claims": ..., "authz": ...} on success,
    or {"error": {"status": 401|403, "code": ..., "message": ...}} on failure.
    """
    token = _extract_bearer_token(raw_header)
    if not token:
        return {"error": {"status": 401, "code": "missing_token", "message": "Missing or invalid Authorization header"}}

    if config.verify_token:
        try:
            payload = await config.verify_token(token)
        except Exception:
            return {"error": {"status": 401, "code": "verification_failed", "message": "Token verification failed"}}
    else:
        payload = decode_jwt_claims(token)

    if payload is None:
        return {"error": {"status": 401, "code": "malformed_token", "message": "Malformed token"}}

    claims = extract_claims(payload)
    validation_error = validate_claims(claims, config)

    if validation_error:
        status = 401 if validation_error.code == "expired_token" else 403
        return {"error": {"status": status, "code": validation_error.code, "message": validation_error.message}}

    authz = evaluate_authz(claims, context, config.policies, config.default_policy)
    if not authz.allowed:
        return {"error": {"status": 403, "code": "authorization_denied", "message": authz.denied_reason or "Access denied"}}

    return {"claims": claims, "authz": authz}


async def handle_optional_identity(
    raw_header: str | None,
    config: AgentIdentityConfig,
) -> AgentIdentityClaims | None:
    """Non-strict identity extraction. Returns None on any error."""
    token = _extract_bearer_token(raw_header)
    if not token:
        return None

    try:
        if config.verify_token:
            payload = await config.verify_token(token)
        else:
            payload = decode_jwt_claims(token)
    except Exception:
        return None

    if payload is None:
        return None

    claims = extract_claims(payload)
    if validate_claims(claims, config) is not None:
        return None

    return claims
