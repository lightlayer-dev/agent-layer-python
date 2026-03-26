"""Tests for Flask robots_txt route."""

from __future__ import annotations

from flask import Flask

from agent_layer.flask.robots_txt import robots_txt_routes
from agent_layer.robots_txt import RobotsTxtConfig


def test_serves_robots_txt() -> None:
    app = Flask(__name__)
    app.register_blueprint(robots_txt_routes())
    with app.test_client() as client:
        resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert "text/plain" in resp.content_type
    assert b"User-agent: *" in resp.data
    assert b"GPTBot" in resp.data


def test_cache_control() -> None:
    app = Flask(__name__)
    app.register_blueprint(robots_txt_routes())
    with app.test_client() as client:
        resp = client.get("/robots.txt")
    assert "max-age=86400" in resp.headers.get("Cache-Control", "")


def test_custom_config() -> None:
    app = Flask(__name__)
    config = RobotsTxtConfig(ai_agent_policy="disallow")
    app.register_blueprint(robots_txt_routes(config))
    with app.test_client() as client:
        resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert b"Disallow: /" in resp.data
