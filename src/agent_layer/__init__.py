"""agent-layer — Make web apps AI-agent-friendly."""

from agent_layer.errors import AgentError, format_error, not_found_error, rate_limit_error
from agent_layer.rate_limit import MemoryStore, create_rate_limiter
from agent_layer.llms_txt import generate_llms_txt, generate_llms_full_txt
from agent_layer.discovery import generate_ai_manifest, generate_json_ld

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
]
