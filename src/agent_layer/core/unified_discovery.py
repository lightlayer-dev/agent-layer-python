"""
Unified Discovery — Multi-format content negotiation.

Generates all discovery formats (MCP, A2A, llms.txt, agents.txt)
from a single unified configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_layer.core.a2a import (
    A2AAgentCard,
    A2AAuthScheme,
    A2ACapabilities,
    A2AConfig,
    A2ASkill,
    generate_agent_card,
)
from agent_layer.core.agents_txt import (
    AgentsTxtConfig,
    AgentsTxtRule,
    generate_agents_txt,
)
from agent_layer.core.discovery import (
    AIManifest,
    AIManifestAuth,
    DiscoveryConfig,
    generate_ai_manifest,
)
from agent_layer.core.llms_txt import (
    LlmsTxtConfig,
    LlmsTxtSection,
    RouteMetadata,
    generate_llms_txt,
    generate_llms_full_txt,
)


@dataclass
class DiscoveryFormats:
    """Control which discovery formats are generated."""

    ai_manifest: bool = True
    agent_card: bool = True
    agents_txt: bool = True
    llms_txt: bool = True
    llms_full_txt: bool = True


@dataclass
class UnifiedAuthConfig:
    """Shared auth configuration across all formats."""

    type: str = "none"  # "oauth2", "api_key", "bearer", "none"
    authorization_url: str | None = None
    token_url: str | None = None
    scopes: dict[str, str] = field(default_factory=dict)
    location: str | None = None  # "header", "query"
    name: str | None = None


@dataclass
class UnifiedSkill:
    """Skill/capability definition that maps across formats."""

    id: str
    name: str
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)


@dataclass
class UnifiedDiscoveryConfig:
    """Master configuration for unified discovery."""

    name: str
    url: str
    description: str | None = None
    version: str | None = None
    provider_organization: str | None = None
    provider_url: str | None = None
    documentation_url: str | None = None
    auth: UnifiedAuthConfig | None = None
    skills: list[UnifiedSkill] = field(default_factory=list)
    routes: list[RouteMetadata] = field(default_factory=list)
    agents_txt_rules: list[AgentsTxtRule] = field(default_factory=list)
    formats: DiscoveryFormats = field(default_factory=DiscoveryFormats)


def _map_auth_to_ai_manifest(auth: UnifiedAuthConfig | None) -> AIManifestAuth | None:
    """Map unified auth to AI manifest format (bearer → api_key)."""
    if not auth or auth.type == "none":
        return None
    auth_type = "api_key" if auth.type == "bearer" else auth.type
    return AIManifestAuth(
        type=auth_type,
        authorization_url=auth.authorization_url,
        token_url=auth.token_url,
        scopes=auth.scopes if auth.scopes else {},
    )


def _map_auth_to_a2a(auth: UnifiedAuthConfig | None) -> A2AAuthScheme | None:
    """Map unified auth to A2A format (api_key → apiKey)."""
    if not auth or auth.type == "none":
        return None
    auth_type = "apiKey" if auth.type == "api_key" else auth.type
    return A2AAuthScheme(
        type=auth_type,
        location=auth.location,
        name=auth.name,
        authorization_url=auth.authorization_url,
        token_url=auth.token_url,
        scopes={k: v for k, v in auth.scopes.items()} if auth.scopes else {},
    )


def generate_unified_ai_manifest(config: UnifiedDiscoveryConfig) -> dict[str, Any]:
    """Generate /.well-known/ai manifest from unified config."""
    manifest = AIManifest(
        name=config.name,
        description=config.description,
        auth=_map_auth_to_ai_manifest(config.auth),
    )
    # Add llms_txt_url if llms.txt is enabled
    if config.formats.llms_txt:
        manifest.llms_txt_url = f"{config.url}/llms.txt"
    return generate_ai_manifest(DiscoveryConfig(manifest=manifest))


def generate_unified_agent_card(config: UnifiedDiscoveryConfig) -> dict[str, Any]:
    """Generate /.well-known/agent.json from unified config."""
    from agent_layer.core.a2a import A2AProvider

    skills = [
        A2ASkill(
            id=s.id,
            name=s.name,
            description=s.description,
            tags=s.tags,
            examples=s.examples,
        )
        for s in config.skills
    ]

    card = A2AAgentCard(
        name=config.name,
        url=config.url,
        description=config.description,
        version=config.version,
        documentation_url=config.documentation_url,
        skills=skills,
        authentication=_map_auth_to_a2a(config.auth),
    )

    if config.provider_organization:
        card.provider = A2AProvider(
            organization=config.provider_organization,
            url=config.provider_url,
        )

    return generate_agent_card(A2AConfig(card=card))


def generate_unified_llms_txt(config: UnifiedDiscoveryConfig) -> str:
    """Generate /llms.txt from unified config."""
    sections = [
        LlmsTxtSection(title=s.name, content=s.description or "")
        for s in config.skills
    ]
    llms_config = LlmsTxtConfig(
        title=config.name,
        description=config.description,
        sections=sections,
    )
    return generate_llms_txt(llms_config)


def generate_unified_llms_full_txt(config: UnifiedDiscoveryConfig) -> str:
    """Generate /llms-full.txt from unified config (includes routes)."""
    sections = [
        LlmsTxtSection(title=s.name, content=s.description or "")
        for s in config.skills
    ]
    llms_config = LlmsTxtConfig(
        title=config.name,
        description=config.description,
        sections=sections,
    )
    return generate_llms_full_txt(llms_config, routes=config.routes)


def generate_unified_agents_txt(config: UnifiedDiscoveryConfig) -> str:
    """Generate /agents.txt from unified config."""
    agents_config = AgentsTxtConfig(rules=config.agents_txt_rules)
    return generate_agents_txt(agents_config)


def generate_all_discovery(
    config: UnifiedDiscoveryConfig,
) -> dict[str, str | dict[str, Any]]:
    """Generate all enabled discovery documents.

    Returns a dict mapping endpoint paths to their content.
    """
    result: dict[str, str | dict[str, Any]] = {}
    fmt = config.formats

    if fmt.ai_manifest:
        result["/.well-known/ai"] = generate_unified_ai_manifest(config)

    if fmt.agent_card:
        result["/.well-known/agent.json"] = generate_unified_agent_card(config)

    if fmt.agents_txt:
        result["/agents.txt"] = generate_unified_agents_txt(config)

    if fmt.llms_txt:
        result["/llms.txt"] = generate_unified_llms_txt(config)

    if fmt.llms_full_txt:
        result["/llms-full.txt"] = generate_unified_llms_full_txt(config)

    return result
