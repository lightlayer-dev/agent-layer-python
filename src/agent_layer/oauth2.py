"""OAuth2 Authorization Code Flow with PKCE.

Provides framework-agnostic OAuth2 utilities for agent authentication:
- PKCE code verifier/challenge generation
- Authorization URL construction
- Token exchange and refresh
- Token validation with scope checking

No external dependencies beyond httpx.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field


# ── Types ────────────────────────────────────────────────────────────────


class OAuth2Config(BaseModel):
    """OAuth2 configuration."""

    client_id: str
    client_secret: str | None = None
    authorization_endpoint: str
    token_endpoint: str
    redirect_uri: str
    scopes: dict[str, str] | None = None
    token_ttl: int = 3600
    issuer: str | None = None
    audience: str | None = None


class TokenResponse(BaseModel):
    """OAuth2 token response."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str | None = None
    scope: str | None = None


@dataclass
class PKCEPair:
    """PKCE code verifier + code challenge pair."""

    code_verifier: str
    code_challenge: str


class DecodedAccessToken(BaseModel):
    """Decoded JWT access token."""

    sub: str
    iss: str | None = None
    aud: str | list[str] | None = None
    exp: int
    iat: int | None = None
    scopes: list[str] = Field(default_factory=list)
    client_id: str | None = None
    claims: dict[str, Any] = Field(default_factory=dict)


class TokenValidationResult(BaseModel):
    """Result of validating an access token."""

    valid: bool
    token: DecodedAccessToken | None = None
    error: str | None = None


# ── Error Class ──────────────────────────────────────────────────────────


class OAuth2TokenError(Exception):
    """Error raised during OAuth2 token operations."""

    def __init__(self, message: str, error_code: str, status_code: int) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


# ── PKCE ─────────────────────────────────────────────────────────────────

UNRESERVED = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"


def generate_code_verifier(length: int = 64) -> str:
    """Generate a cryptographically random code verifier (RFC 7636 §4.1).

    Length defaults to 64 characters (within the 43-128 range).
    """
    random_bytes = secrets.token_bytes(length)
    return "".join(UNRESERVED[b % len(UNRESERVED)] for b in random_bytes)


def compute_code_challenge(verifier: str) -> str:
    """Compute the S256 code challenge from a code verifier.

    Returns a base64url-encoded SHA-256 hash.
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_pkce(verifier_length: int = 64) -> PKCEPair:
    """Generate a PKCE code verifier + code challenge pair."""
    code_verifier = generate_code_verifier(verifier_length)
    code_challenge = compute_code_challenge(code_verifier)
    return PKCEPair(code_verifier=code_verifier, code_challenge=code_challenge)


# ── Authorization URL ────────────────────────────────────────────────────


def build_authorization_url(
    config: OAuth2Config,
    state: str,
    code_challenge: str,
    scopes: list[str] | None = None,
) -> str:
    """Build the authorization URL for the code flow with PKCE."""
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    scope_list = scopes or (list(config.scopes.keys()) if config.scopes else [])
    if scope_list:
        params["scope"] = " ".join(scope_list)

    separator = "&" if "?" in config.authorization_endpoint else "?"
    return f"{config.authorization_endpoint}{separator}{urlencode(params)}"


# ── Token Exchange ───────────────────────────────────────────────────────


async def exchange_code(
    config: OAuth2Config,
    code: str,
    code_verifier: str,
    http_client: httpx.AsyncClient | None = None,
) -> TokenResponse:
    """Exchange an authorization code for tokens."""
    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.redirect_uri,
        "client_id": config.client_id,
        "code_verifier": code_verifier,
    }

    if config.client_secret:
        data["client_secret"] = config.client_secret

    client = http_client or httpx.AsyncClient()
    try:
        resp = await client.post(
            config.token_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    finally:
        if http_client is None:
            await client.aclose()

    if resp.status_code != 200:
        err = resp.json()
        raise OAuth2TokenError(
            err.get("error_description") or err.get("error") or "Token exchange failed",
            err.get("error", "server_error"),
            resp.status_code,
        )

    return TokenResponse(**resp.json())


async def refresh_access_token(
    config: OAuth2Config,
    refresh_token: str,
    http_client: httpx.AsyncClient | None = None,
) -> TokenResponse:
    """Refresh an access token using a refresh token."""
    data: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": config.client_id,
    }

    if config.client_secret:
        data["client_secret"] = config.client_secret

    client = http_client or httpx.AsyncClient()
    try:
        resp = await client.post(
            config.token_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    finally:
        if http_client is None:
            await client.aclose()

    if resp.status_code != 200:
        err = resp.json()
        raise OAuth2TokenError(
            err.get("error_description") or err.get("error") or "Token refresh failed",
            err.get("error", "server_error"),
            resp.status_code,
        )

    return TokenResponse(**resp.json())


# ── Token Validation ─────────────────────────────────────────────────────


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    """Decode the payload of a JWT without verifying the signature."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        # Add padding
        payload += "=" * ((4 - len(payload) % 4) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return None


def _extract_scopes(payload: dict[str, Any]) -> list[str]:
    """Extract scopes from a JWT payload."""
    if isinstance(payload.get("scope"), str):
        return [s for s in payload["scope"].split(" ") if s]
    if isinstance(payload.get("scopes"), list):
        return [str(s) for s in payload["scopes"]]
    if isinstance(payload.get("scp"), list):
        return [str(s) for s in payload["scp"]]
    return []


def validate_access_token(
    token: str,
    config: OAuth2Config,
    required_scopes: list[str] | None = None,
    clock_skew_seconds: int = 30,
) -> TokenValidationResult:
    """Decode and validate an access token (JWT).

    Performs structural validation only (expiry, issuer, audience, scopes).
    Signature verification should be done at the framework layer with a proper JWKS.
    """
    import time

    decoded = _decode_jwt_payload(token)
    if decoded is None:
        return TokenValidationResult(valid=False, error="malformed_token")

    now = int(time.time())

    # Check expiration
    exp = int(decoded.get("exp", 0))
    if exp and exp + clock_skew_seconds < now:
        return TokenValidationResult(valid=False, error="token_expired")

    # Check issuer
    if config.issuer and decoded.get("iss") != config.issuer:
        return TokenValidationResult(valid=False, error="invalid_issuer")

    # Check audience
    if config.audience:
        aud = decoded.get("aud")
        aud_list = aud if isinstance(aud, list) else [aud] if aud else []
        if config.audience not in aud_list:
            return TokenValidationResult(valid=False, error="invalid_audience")

    # Extract scopes
    scopes = _extract_scopes(decoded)

    # Check required scopes
    if required_scopes:
        missing = [s for s in required_scopes if s not in scopes]
        if missing:
            return TokenValidationResult(
                valid=False, error=f"missing_scopes: {', '.join(missing)}"
            )

    decoded_token = DecodedAccessToken(
        sub=str(decoded.get("sub", "")),
        iss=str(decoded["iss"]) if "iss" in decoded else None,
        aud=decoded.get("aud"),
        exp=exp,
        iat=int(decoded["iat"]) if "iat" in decoded else None,
        scopes=scopes,
        client_id=str(decoded["client_id"]) if "client_id" in decoded else None,
        claims=decoded,
    )

    return TokenValidationResult(valid=True, token=decoded_token)


# ── Bearer Token Extraction ──────────────────────────────────────────────


def extract_bearer_token(authorization_header: str | None) -> str | None:
    """Extract a Bearer token from an Authorization header value.

    Returns None if the header is missing or not a Bearer token.
    """
    if not authorization_header:
        return None
    parts = authorization_header.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


# ── OAuth2 Discovery ─────────────────────────────────────────────────────


def build_oauth2_metadata(config: OAuth2Config) -> dict[str, Any]:
    """Build an OAuth2 Authorization Server Metadata document (RFC 8414)."""
    metadata: dict[str, Any] = {
        "authorization_endpoint": config.authorization_endpoint,
        "token_endpoint": config.token_endpoint,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": (
            ["client_secret_post"] if config.client_secret else ["none"]
        ),
    }

    if config.issuer:
        metadata["issuer"] = config.issuer
    if config.scopes:
        metadata["scopes_supported"] = list(config.scopes.keys())

    return metadata
