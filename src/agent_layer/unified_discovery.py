"""Unified multi-format discovery — single config, all agent discovery formats.

Generates:
- /.well-known/ai       (AI manifest)
- /.well-known/agent.json (A2A Agent Card per Google A2A protocol)
- /agents.txt            (robots.txt-style permissions for AI agents)
- /llms.txt              (LLM-oriented documentation)
- /llms-full.txt         (auto-generated from routes)

See:
- https://github.com/nichochar/open-agent-schema (agents.txt)
- https://a2a-protocol.org (A2A Agent Card)
- https://llmstxt.org (llms.txt)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_layer.a2a import (
    A2AAgentCard,
    A2AAuthScheme,
    A2ACapabilities,
    A2AConfig,
    A2AProvider,
    A2ASkill,
    generate_agent_card,
)
from agent_layer.discovery import generate_ai_manifest
from agent_layer.llms_txt import generate_llms_full_txt, generate_llms_txt
from agent_layer.types import (
    AIManifest,
    AIManifestAuth,
    AIManifestContact,
    DiscoveryConfig,
    LlmsTxtConfig,
    LlmsTxtSection,
    RouteMetadata,
)


# ── Agents.txt Types ────────────────────────────────────────────────────


class AgentsTxtRule(BaseModel):
    """A rule in agents.txt (allow/disallow per user-agent)."""

    path: str
    permission: Literal["allow", "disallow"]


class AgentsTxtBlock(BaseModel):
    """A block in agents.txt targeting one or more user-agents."""

    user_agent: str
    rules: list[AgentsTxtRule]


class AgentsTxtConfig(BaseModel):
    """Configuration for agents.txt generation."""

    blocks: list[AgentsTxtBlock]
    sitemap_url: str | None = None
    comment: str | None = None


# ── Unified Config ──────────────────────────────────────────────────────


class DiscoveryFormats(BaseModel):
    """Control which discovery formats are generated."""

    well_known_ai: bool = True
    agent_card: bool = True
    agents_txt: bool = True
    llms_txt: bool = True


class UnifiedAuthConfig(BaseModel):
    """Auth configuration shared across discovery formats."""

    type: Literal["oauth2", "api_key", "bearer", "none"]
    in_: Literal["header", "query"] | None = Field(None, alias="in")
    name: str | None = None
    authorization_url: str | None = None
    token_url: str | None = None
    scopes: dict[str, str] | None = None

    model_config = {"populate_by_name": True}


class UnifiedSkill(BaseModel):
    """A skill/capability (maps to A2A skills, llms.txt sections, etc.)."""

    id: str
    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    input_modes: list[str] = Field(default_factory=list)
    output_modes: list[str] = Field(default_factory=list)


class UnifiedDiscoveryConfig(BaseModel):
    """Single source of truth for all discovery formats."""

    name: str
    description: str | None = None
    url: str
    version: str | None = None
    provider: A2AProvider | None = None
    contact: AIManifestContact | None = None
    openapi_url: str | None = None
    documentation_url: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    agent_capabilities: A2ACapabilities | None = None
    auth: UnifiedAuthConfig | None = None
    skills: list[UnifiedSkill] = Field(default_factory=list)
    routes: list[RouteMetadata] = Field(default_factory=list)
    agents_txt: AgentsTxtConfig | None = None
    formats: DiscoveryFormats = Field(default_factory=DiscoveryFormats)
    llms_txt_sections: list[LlmsTxtSection] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── Generators ──────────────────────────────────────────────────────────


def is_format_enabled(formats: DiscoveryFormats, fmt: str) -> bool:
    """Check if a given format is enabled."""
    return getattr(formats, fmt, True)


def generate_unified_ai_manifest(config: UnifiedDiscoveryConfig) -> dict[str, Any]:
    """Generate /.well-known/ai manifest from unified config."""
    auth: AIManifestAuth | None = None
    if config.auth:
        auth_type = "api_key" if config.auth.type == "bearer" else config.auth.type
        auth = AIManifestAuth(
            type=auth_type,
            authorization_url=config.auth.authorization_url,
            token_url=config.auth.token_url,
            scopes=config.auth.scopes,
        )

    llms_txt_url = (
        f"{config.url}/llms.txt" if config.formats.llms_txt else None
    )

    manifest = AIManifest(
        name=config.name,
        description=config.description,
        openapi_url=config.openapi_url,
        llms_txt_url=llms_txt_url,
        auth=auth,
        contact=config.contact,
        capabilities=config.capabilities,
    )

    return generate_ai_manifest(DiscoveryConfig(manifest=manifest))


def generate_unified_agent_card(config: UnifiedDiscoveryConfig) -> dict[str, Any]:
    """Generate A2A Agent Card from unified config."""
    auth_scheme: A2AAuthScheme | None = None
    if config.auth:
        auth_type = "apiKey" if config.auth.type == "api_key" else config.auth.type
        auth_scheme = A2AAuthScheme(
            type=auth_type,
            **{"in": config.auth.in_},
            name=config.auth.name,
            authorization_url=config.auth.authorization_url,
            token_url=config.auth.token_url,
            scopes=config.auth.scopes,
        )

    skills = [
        A2ASkill(
            id=s.id,
            name=s.name,
            description=s.description,
            tags=s.tags,
            examples=s.examples,
            input_modes=s.input_modes,
            output_modes=s.output_modes,
        )
        for s in config.skills
    ]

    card = A2AAgentCard(
        protocol_version="1.0.0",
        name=config.name,
        description=config.description,
        url=config.url,
        provider=config.provider,
        version=config.version,
        documentation_url=config.documentation_url or config.openapi_url,
        capabilities=config.agent_capabilities,
        authentication=auth_scheme,
        skills=skills,
    )

    return generate_agent_card(A2AConfig(card=card))


def generate_unified_llms_txt(config: UnifiedDiscoveryConfig) -> str:
    """Generate /llms.txt from unified config."""
    sections = [
        LlmsTxtSection(
            title=s.name,
            content="\n".join(
                filter(
                    None,
                    [
                        s.description or "",
                        (
                            "\nExamples:\n"
                            + "\n".join(f"- {e}" for e in s.examples)
                            if s.examples
                            else ""
                        ),
                    ],
                )
            ),
        )
        for s in config.skills
    ] + list(config.llms_txt_sections)

    return generate_llms_txt(
        LlmsTxtConfig(
            title=config.name,
            description=config.description,
            sections=sections,
        )
    )


def generate_unified_llms_full_txt(config: UnifiedDiscoveryConfig) -> str:
    """Generate /llms-full.txt from unified config (with routes)."""
    sections = [
        LlmsTxtSection(
            title=s.name,
            content="\n".join(
                filter(
                    None,
                    [
                        s.description or "",
                        (
                            "\nExamples:\n"
                            + "\n".join(f"- {e}" for e in s.examples)
                            if s.examples
                            else ""
                        ),
                    ],
                )
            ),
        )
        for s in config.skills
    ] + list(config.llms_txt_sections)

    return generate_llms_full_txt(
        LlmsTxtConfig(
            title=config.name,
            description=config.description,
            sections=sections,
        ),
        list(config.routes),
    )


def generate_agents_txt(config: UnifiedDiscoveryConfig) -> str:
    """Generate /agents.txt from unified config."""
    if not config.agents_txt:
        return (
            f"# agents.txt — AI agent access rules for {config.name}\n"
            f"# See https://github.com/nichochar/open-agent-schema\n\n"
            f"User-agent: *\nAllow: /\n"
        )

    lines: list[str] = []

    if config.agents_txt.comment:
        for line in config.agents_txt.comment.split("\n"):
            lines.append(f"# {line}")
        lines.append("")

    for block in config.agents_txt.blocks:
        lines.append(f"User-agent: {block.user_agent}")
        for rule in block.rules:
            directive = "Allow" if rule.permission == "allow" else "Disallow"
            lines.append(f"{directive}: {rule.path}")
        lines.append("")

    if config.agents_txt.sitemap_url:
        lines.append(f"Sitemap: {config.agents_txt.sitemap_url}")
        lines.append("")

    return "\n".join(lines)


def generate_all_discovery(
    config: UnifiedDiscoveryConfig,
) -> dict[str, str | dict[str, Any]]:
    """Generate all enabled discovery documents.

    Returns a dict of path → content (str for text, dict for JSON).
    """
    result: dict[str, str | dict[str, Any]] = {}

    if config.formats.well_known_ai:
        result["/.well-known/ai"] = generate_unified_ai_manifest(config)

    if config.formats.agent_card:
        result["/.well-known/agent.json"] = generate_unified_agent_card(config)

    if config.formats.llms_txt:
        result["/llms.txt"] = generate_unified_llms_txt(config)
        result["/llms-full.txt"] = generate_unified_llms_full_txt(config)

    if config.formats.agents_txt:
        result["/agents.txt"] = generate_agents_txt(config)

    return result
