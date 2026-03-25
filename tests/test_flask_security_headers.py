"""Tests for Flask security_headers middleware."""

from __future__ import annotations

from flask import Flask

from agent_layer.flask.security_headers import security_headers_middleware
from agent_layer.security_headers import SecurityHeadersConfig


def _make_app(config: SecurityHeadersConfig | None = None) -> Flask:
    app = Flask(__name__)
    security_headers_middleware(app, config)

    @app.route("/test")
    def test_endpoint():  # type: ignore[no-untyped-def]
        return "ok"

    return app


def test_default_security_headers() -> None:
    app = _make_app()
    with app.test_client() as client:
        resp = client.get("/test")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["Content-Security-Policy"] == "default-src 'self'"


def test_custom_security_headers() -> None:
    config = SecurityHeadersConfig(frame_options="SAMEORIGIN", csp=False)
    app = _make_app(config)
    with app.test_client() as client:
        resp = client.get("/test")
    assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "Content-Security-Policy" not in resp.headers
