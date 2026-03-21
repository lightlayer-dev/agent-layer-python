"""agent-layer — Python middleware to make your web app AI-agent-friendly."""

from agent_layer.core.agents_txt import (
    AgentsTxtConfig,
    AgentsTxtRule,
    generate_agents_txt,
    is_agent_allowed,
    parse_agents_txt,
)
from agent_layer.core.a2a import (
    A2AAgentCard,
    A2AAuthScheme,
    A2ACapabilities,
    A2AConfig,
    A2AProvider,
    A2ASkill,
    generate_agent_card,
    validate_agent_card,
)
from agent_layer.core.discovery import (
    AIManifest,
    AIManifestAuth,
    DiscoveryConfig,
    generate_ai_manifest,
    generate_json_ld,
)
from agent_layer.core.errors import (
    AgentError,
    AgentErrorEnvelope,
    AgentErrorOptions,
    format_error,
    not_found_error,
    rate_limit_error,
)
from agent_layer.core.llms_txt import (
    LlmsTxtConfig,
    LlmsTxtSection,
    RouteMetadata,
    RouteParameter,
    generate_llms_txt,
    generate_llms_full_txt,
)
from agent_layer.core.rate_limit import (
    MemoryStore,
    RateLimitConfig,
    RateLimitResult,
    create_rate_limiter,
)

__all__ = [
    # agents.txt
    "AgentsTxtConfig",
    "AgentsTxtRule",
    "generate_agents_txt",
    "parse_agents_txt",
    "is_agent_allowed",
    # A2A
    "A2AAgentCard",
    "A2AAuthScheme",
    "A2ACapabilities",
    "A2AConfig",
    "A2AProvider",
    "A2ASkill",
    "generate_agent_card",
    "validate_agent_card",
    # Discovery
    "AIManifest",
    "AIManifestAuth",
    "DiscoveryConfig",
    "generate_ai_manifest",
    "generate_json_ld",
    # Errors
    "AgentError",
    "AgentErrorEnvelope",
    "AgentErrorOptions",
    "format_error",
    "not_found_error",
    "rate_limit_error",
    # LLMs.txt
    "LlmsTxtConfig",
    "LlmsTxtSection",
    "RouteMetadata",
    "RouteParameter",
    "generate_llms_txt",
    "generate_llms_full_txt",
    # Rate limit
    "MemoryStore",
    "RateLimitConfig",
    "RateLimitResult",
    "create_rate_limiter",
]

__version__ = "0.1.0"
