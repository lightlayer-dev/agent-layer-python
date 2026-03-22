"""One-liner to configure all agent-layer features on a Django app."""

from __future__ import annotations

from typing import Any

from agent_layer.types import AgentLayerConfig


def configure_agent_layer(urlpatterns: list, config: AgentLayerConfig) -> list:
    """One-liner: compose all agent-layer URL patterns for a Django project.

    Returns extended urlpatterns with agent-layer routes appended.

    Middleware (errors, rate limiting, meta, analytics, agent identity)
    must still be added to MIDDLEWARE in settings.py.

    Usage::

        from agent_layer.django import configure_agent_layer
        from agent_layer.types import AgentLayerConfig, LlmsTxtConfig

        urlpatterns = [
            path("admin/", admin.site.urls),
        ]
        urlpatterns = configure_agent_layer(urlpatterns, AgentLayerConfig(
            llms_txt=LlmsTxtConfig(title="My API"),
        ))
    """
    from agent_layer.django.views import (
        a2a_urlpatterns,
        discovery_urlpatterns,
        llms_txt_urlpatterns,
    )

    if config.llms_txt:
        urlpatterns.extend(llms_txt_urlpatterns(config.llms_txt))

    if config.discovery:
        urlpatterns.extend(discovery_urlpatterns(config.discovery))

    if config.agent_auth:
        from agent_layer.django.auth import agent_auth_urlpatterns

        urlpatterns.extend(agent_auth_urlpatterns(config.agent_auth))

    if config.a2a:
        from agent_layer.a2a import A2AConfig

        if isinstance(config.a2a, A2AConfig):
            urlpatterns.extend(a2a_urlpatterns(config.a2a))

    return urlpatterns
