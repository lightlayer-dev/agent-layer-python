"""Django middleware for agent-layer."""

from agent_layer.django.errors import AgentErrorsMiddleware
from agent_layer.django.rate_limits import RateLimitsMiddleware
from agent_layer.django.analytics import AgentAnalyticsMiddleware
from agent_layer.django.agent_identity import AgentIdentityMiddleware
from agent_layer.django.x402 import X402PaymentMiddleware
from agent_layer.django.meta import AgentMetaMiddleware
from agent_layer.django.views import a2a_urlpatterns, discovery_urlpatterns, llms_txt_urlpatterns
from agent_layer.django.auth import agent_auth_urlpatterns
from agent_layer.django.mcp import mcp_urlpatterns
from agent_layer.django.unified_discovery import unified_discovery_urlpatterns
from agent_layer.django.ag_ui import ag_ui_stream as django_ag_ui_stream
from agent_layer.django.app import configure_agent_layer

__all__ = [
    "AgentErrorsMiddleware",
    "RateLimitsMiddleware",
    "AgentAnalyticsMiddleware",
    "AgentIdentityMiddleware",
    "X402PaymentMiddleware",
    "AgentMetaMiddleware",
    "a2a_urlpatterns",
    "agent_auth_urlpatterns",
    "discovery_urlpatterns",
    "llms_txt_urlpatterns",
    "mcp_urlpatterns",
    "unified_discovery_urlpatterns",
    "django_ag_ui_stream",
    "configure_agent_layer",
]
