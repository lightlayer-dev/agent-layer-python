"""Tests for Django robots_txt URL patterns."""

from __future__ import annotations

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        ROOT_URLCONF=__name__,
        ALLOWED_HOSTS=["*"],
        SECRET_KEY="test-secret",
    )
    django.setup()

from django.test import RequestFactory

from agent_layer.django.robots_txt import robots_txt_urlpatterns
from agent_layer.robots_txt import RobotsTxtConfig


def test_serves_robots_txt() -> None:
    patterns = robots_txt_urlpatterns()
    view = patterns[0].callback
    factory = RequestFactory()
    request = factory.get("/robots.txt")
    resp = view(request)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "text/plain; charset=utf-8"
    assert b"User-agent: *" in resp.content
    assert b"GPTBot" in resp.content


def test_cache_control() -> None:
    patterns = robots_txt_urlpatterns()
    view = patterns[0].callback
    factory = RequestFactory()
    request = factory.get("/robots.txt")
    resp = view(request)
    assert "max-age=86400" in resp.get("Cache-Control", "")


def test_custom_config() -> None:
    config = RobotsTxtConfig(ai_agent_policy="disallow")
    patterns = robots_txt_urlpatterns(config)
    view = patterns[0].callback
    factory = RequestFactory()
    request = factory.get("/robots.txt")
    resp = view(request)
    assert resp.status_code == 200
    assert b"Disallow: /" in resp.content
