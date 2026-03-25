"""Tests for security_headers core generation."""

from __future__ import annotations

from agent_layer.security_headers import SecurityHeadersConfig, generate_security_headers


def test_default_headers() -> None:
    """Default config produces all standard security headers."""
    headers = generate_security_headers()
    assert headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert headers["Content-Security-Policy"] == "default-src 'self'"
    assert "Permissions-Policy" not in headers


def test_custom_hsts() -> None:
    """Custom HSTS max-age is respected."""
    config = SecurityHeadersConfig(hsts_max_age=86400, hsts_include_subdomains=False)
    headers = generate_security_headers(config)
    assert headers["Strict-Transport-Security"] == "max-age=86400"


def test_disabled_hsts() -> None:
    """hsts_max_age=0 disables HSTS."""
    config = SecurityHeadersConfig(hsts_max_age=0)
    headers = generate_security_headers(config)
    assert "Strict-Transport-Security" not in headers


def test_sameorigin_frame() -> None:
    """SAMEORIGIN frame option."""
    config = SecurityHeadersConfig(frame_options="SAMEORIGIN")
    headers = generate_security_headers(config)
    assert headers["X-Frame-Options"] == "SAMEORIGIN"


def test_disable_frame_options() -> None:
    """frame_options=False disables X-Frame-Options."""
    config = SecurityHeadersConfig(frame_options=False)
    headers = generate_security_headers(config)
    assert "X-Frame-Options" not in headers


def test_custom_csp() -> None:
    """Custom CSP is set."""
    config = SecurityHeadersConfig(csp="default-src 'none'")
    headers = generate_security_headers(config)
    assert headers["Content-Security-Policy"] == "default-src 'none'"


def test_disable_csp() -> None:
    """csp=False disables Content-Security-Policy."""
    config = SecurityHeadersConfig(csp=False)
    headers = generate_security_headers(config)
    assert "Content-Security-Policy" not in headers


def test_permissions_policy() -> None:
    """Permissions-Policy is included when set."""
    config = SecurityHeadersConfig(permissions_policy="camera=(), microphone=()")
    headers = generate_security_headers(config)
    assert headers["Permissions-Policy"] == "camera=(), microphone=()"


def test_disable_referrer_policy() -> None:
    """referrer_policy=False disables Referrer-Policy."""
    config = SecurityHeadersConfig(referrer_policy=False)
    headers = generate_security_headers(config)
    assert "Referrer-Policy" not in headers
