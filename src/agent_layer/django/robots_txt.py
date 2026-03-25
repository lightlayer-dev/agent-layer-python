"""Django URL patterns for /robots.txt."""

from __future__ import annotations

from django.http import HttpResponse
from django.urls import URLPattern, path

from agent_layer.robots_txt import RobotsTxtConfig, generate_robots_txt


def robots_txt_urlpatterns(config: RobotsTxtConfig | None = None) -> list[URLPattern]:
    """Return Django URL patterns that serve GET /robots.txt."""
    content = generate_robots_txt(config)

    def robots_txt_view(request):  # type: ignore[no-untyped-def]
        response = HttpResponse(content, content_type="text/plain; charset=utf-8")
        response["Cache-Control"] = "public, max-age=86400"
        return response

    return [path("robots.txt", robots_txt_view, name="robots_txt")]
