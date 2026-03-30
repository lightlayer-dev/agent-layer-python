"""Django middleware for agent-layer."""

from agent_layer.django.errors import AgentErrorsMiddleware
from agent_layer.django.rate_limits import RateLimitsMiddleware
from agent_layer.django.analytics import AgentAnalyticsMiddleware
from agent_layer.django.agent_identity import AgentIdentityMiddleware
from agent_layer.django.x402 import X402PaymentMiddleware
from agent_layer.django.meta import AgentMetaMiddleware
from agent_layer.django.a2a import a2a_urlpatterns
from agent_layer.django.discovery import discovery_urlpatterns
from agent_layer.django.llms_txt import llms_txt_urlpatterns
from agent_layer.django.auth import agent_auth_urlpatterns
from agent_layer.django.mcp import mcp_urlpatterns
from agent_layer.django.unified_discovery import unified_discovery_urlpatterns
from agent_layer.django.ag_ui import ag_ui_stream as django_ag_ui_stream
from agent_layer.django.api_keys import require_api_key as django_require_api_key
from agent_layer.django.oauth2 import oauth2_urlpatterns
from agent_layer.django.robots_txt import robots_txt_urlpatterns
from agent_layer.django.security_headers import (
    SecurityHeadersMiddleware,
    security_headers_middleware_class,
)
from agent_layer.django.agent_onboarding import (
    agent_onboarding_urlpatterns,
    AgentOnboardingAuthMiddleware,
)
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
    "django_require_api_key",
    "oauth2_urlpatterns",
    "robots_txt_urlpatterns",
    "SecurityHeadersMiddleware",
    "security_headers_middleware_class",
    "agent_onboarding_urlpatterns",
    "AgentOnboardingAuthMiddleware",
    "configure_agent_layer",
]
