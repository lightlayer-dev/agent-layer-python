"""Flask middleware for agent-layer."""

from agent_layer.flask.errors import agent_errors_handler
from agent_layer.flask.rate_limits import rate_limits_middleware
from agent_layer.flask.llms_txt import llms_txt_blueprint
from agent_layer.flask.discovery import discovery_blueprint
from agent_layer.flask.auth import agent_auth_blueprint
from agent_layer.flask.meta import agent_meta_middleware
from agent_layer.flask.analytics import agent_analytics_middleware
from agent_layer.flask.agent_identity import agent_identity_middleware
from agent_layer.flask.x402 import x402_middleware
from agent_layer.flask.a2a import a2a_blueprint
from agent_layer.flask.mcp import mcp_blueprint
from agent_layer.flask.unified_discovery import unified_discovery_blueprint
from agent_layer.flask.ag_ui import ag_ui_stream as flask_ag_ui_stream
from agent_layer.flask.app import configure_agent_layer

__all__ = [
    "agent_errors_handler",
    "rate_limits_middleware",
    "llms_txt_blueprint",
    "discovery_blueprint",
    "agent_auth_blueprint",
    "agent_meta_middleware",
    "agent_analytics_middleware",
    "agent_identity_middleware",
    "x402_middleware",
    "a2a_blueprint",
    "mcp_blueprint",
    "unified_discovery_blueprint",
    "flask_ag_ui_stream",
    "configure_agent_layer",
]
