"""FastAPI middleware for agent-layer."""

from agent_layer.fastapi.errors import agent_errors_middleware, not_found_handler
from agent_layer.fastapi.rate_limits import rate_limits_middleware
from agent_layer.fastapi.llms_txt import llms_txt_routes
from agent_layer.fastapi.discovery import discovery_routes
from agent_layer.fastapi.auth import agent_auth_routes
from agent_layer.fastapi.meta import agent_meta_middleware
from agent_layer.fastapi.analytics import agent_analytics_middleware
from agent_layer.fastapi.agent_identity import (
    agent_identity_middleware,
    agent_identity_optional_middleware,
)
from agent_layer.fastapi.x402 import x402_middleware
from agent_layer.fastapi.a2a import a2a_routes
from agent_layer.fastapi.unified_discovery import unified_discovery_routes
from agent_layer.fastapi.mcp import mcp_routes
from agent_layer.fastapi.api_keys import api_key_dependency
from agent_layer.fastapi.oauth2 import oauth2_routes
from agent_layer.fastapi.robots_txt import robots_txt_routes
from agent_layer.fastapi.security_headers import security_headers_middleware
from agent_layer.fastapi.agent_onboarding import agent_onboarding_routes, agent_onboarding_auth_middleware
from agent_layer.fastapi.app import configure_agent_layer

__all__ = [
    "agent_errors_middleware",
    "not_found_handler",
    "rate_limits_middleware",
    "llms_txt_routes",
    "discovery_routes",
    "agent_auth_routes",
    "agent_meta_middleware",
    "agent_analytics_middleware",
    "agent_identity_middleware",
    "agent_identity_optional_middleware",
    "x402_middleware",
    "a2a_routes",
    "unified_discovery_routes",
    "mcp_routes",
    "api_key_dependency",
    "oauth2_routes",
    "robots_txt_routes",
    "security_headers_middleware",
    "agent_onboarding_routes",
    "agent_onboarding_auth_middleware",
    "configure_agent_layer",
]
