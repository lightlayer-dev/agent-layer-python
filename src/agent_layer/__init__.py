"""agent-layer — Make web apps AI-agent-friendly."""

from agent_layer.errors import AgentError, format_error, not_found_error, rate_limit_error
from agent_layer.rate_limit import MemoryStore, create_rate_limiter
from agent_layer.llms_txt import generate_llms_txt, generate_llms_full_txt
from agent_layer.discovery import generate_ai_manifest, generate_json_ld
from agent_layer.a2a import (
    A2AAgentCard,
    A2AConfig,
    A2ASkill,
    generate_agent_card,
    validate_agent_card,
)
from agent_layer.analytics import (
    AgentEvent,
    AnalyticsConfig,
    AnalyticsInstance,
    EventBuffer,
    create_analytics,
    detect_agent,
)

__all__ = [
    "AgentError",
    "format_error",
    "not_found_error",
    "rate_limit_error",
    "MemoryStore",
    "create_rate_limiter",
    "generate_llms_txt",
    "generate_llms_full_txt",
    "generate_ai_manifest",
    "generate_json_ld",
    "AgentEvent",
    "AnalyticsConfig",
    "AnalyticsInstance",
    "EventBuffer",
    "create_analytics",
    "detect_agent",
    "A2AAgentCard",
    "A2AConfig",
    "A2ASkill",
    "generate_agent_card",
    "validate_agent_card",
]
