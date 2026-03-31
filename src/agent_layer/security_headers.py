"""Security headers for agent-facing APIs.

Sets headers that protect the API without blocking legitimate agent access:
- HSTS (Strict-Transport-Security)
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Referrer-Policy
- Content-Security-Policy
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SecurityHeadersConfig(BaseModel):
    """Configuration for security headers."""

    hsts_max_age: int = 31536000
    hsts_include_subdomains: bool = True
    frame_options: Literal["DENY", "SAMEORIGIN"] | bool = "DENY"
    content_type_options: Literal["nosniff"] | bool = "nosniff"
    referrer_policy: str | bool = "strict-origin-when-cross-origin"
    csp: str | bool = "default-src 'self'"
    permissions_policy: str | bool = False


def generate_security_headers(config: SecurityHeadersConfig | None = None) -> dict[str, str]:
    """Generate a map of security headers based on config."""
    if config is None:
        config = SecurityHeadersConfig()

    headers: dict[str, str] = {}

    # HSTS
    if config.hsts_max_age > 0:
        sub = "; includeSubDomains" if config.hsts_include_subdomains else ""
        headers["Strict-Transport-Security"] = f"max-age={config.hsts_max_age}{sub}"

    # X-Content-Type-Options
    if config.content_type_options is not False:
        cto: str = (
            config.content_type_options
            if isinstance(config.content_type_options, str)
            else "nosniff"
        )
        headers["X-Content-Type-Options"] = cto

    # X-Frame-Options
    if config.frame_options is not False:
        fo: str = config.frame_options if isinstance(config.frame_options, str) else "DENY"
        headers["X-Frame-Options"] = fo

    # Referrer-Policy
    if config.referrer_policy is not False:
        rp: str = (
            config.referrer_policy
            if isinstance(config.referrer_policy, str)
            else "strict-origin-when-cross-origin"
        )
        headers["Referrer-Policy"] = rp

    # CSP
    if config.csp is not False:
        csp: str = config.csp if isinstance(config.csp, str) else "default-src 'self'"
        headers["Content-Security-Policy"] = csp

    # Permissions-Policy
    if config.permissions_policy and isinstance(config.permissions_policy, str):
        headers["Permissions-Policy"] = config.permissions_policy

    return headers
