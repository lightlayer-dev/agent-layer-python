"""
A2A (Agent-to-Agent) Protocol — Agent Card generation.

Implements the /.well-known/agent.json endpoint per Google's A2A protocol
specification (https://a2a-protocol.org).

An Agent Card is a JSON metadata document that describes an agent's
capabilities, supported input/output modes, authentication requirements,
and skills — enabling machine-readable discovery by other agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class A2AProvider:
    """Provider/organization info."""

    organization: str
    url: str | None = None


@dataclass
class A2AAuthScheme:
    """Authentication scheme the agent supports."""

    type: str  # "apiKey", "oauth2", "bearer", "none"
    location: str | None = None  # "header", "query"
    name: str | None = None
    authorization_url: str | None = None
    token_url: str | None = None
    scopes: dict[str, str] = field(default_factory=dict)


@dataclass
class A2ACapabilities:
    """Capabilities the agent supports."""

    streaming: bool = False
    push_notifications: bool = False
    state_transition_history: bool = False


@dataclass
class A2ASkill:
    """A skill/capability the agent can perform."""

    id: str
    name: str
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    input_modes: list[str] = field(default_factory=list)
    output_modes: list[str] = field(default_factory=list)


@dataclass
class A2AAgentCard:
    """The full Agent Card document served at /.well-known/agent.json."""

    name: str
    url: str
    skills: list[A2ASkill] = field(default_factory=list)
    protocol_version: str = "1.0.0"
    description: str | None = None
    provider: A2AProvider | None = None
    version: str | None = None
    documentation_url: str | None = None
    capabilities: A2ACapabilities | None = None
    authentication: A2AAuthScheme | None = None
    default_input_modes: list[str] = field(default_factory=lambda: ["text/plain"])
    default_output_modes: list[str] = field(default_factory=lambda: ["text/plain"])


@dataclass
class A2AConfig:
    """Configuration for generating an Agent Card."""

    card: A2AAgentCard


def generate_agent_card(config: A2AConfig) -> dict[str, Any]:
    """Generate a valid A2A Agent Card as a JSON-serializable dictionary.

    Ensures required fields are present and sets sensible defaults.
    """
    card = config.card
    result: dict[str, Any] = {
        "protocolVersion": card.protocol_version or "1.0.0",
        "name": card.name,
        "url": card.url,
        "defaultInputModes": card.default_input_modes or ["text/plain"],
        "defaultOutputModes": card.default_output_modes or ["text/plain"],
        "skills": [],
    }

    if card.description:
        result["description"] = card.description

    if card.provider:
        provider: dict[str, str] = {"organization": card.provider.organization}
        if card.provider.url:
            provider["url"] = card.provider.url
        result["provider"] = provider

    if card.version:
        result["version"] = card.version

    if card.documentation_url:
        result["documentationUrl"] = card.documentation_url

    if card.capabilities:
        result["capabilities"] = {
            "streaming": card.capabilities.streaming,
            "pushNotifications": card.capabilities.push_notifications,
            "stateTransitionHistory": card.capabilities.state_transition_history,
        }

    if card.authentication:
        auth: dict[str, Any] = {"type": card.authentication.type}
        if card.authentication.location:
            auth["in"] = card.authentication.location
        if card.authentication.name:
            auth["name"] = card.authentication.name
        if card.authentication.authorization_url:
            auth["authorizationUrl"] = card.authentication.authorization_url
        if card.authentication.token_url:
            auth["tokenUrl"] = card.authentication.token_url
        if card.authentication.scopes:
            auth["scopes"] = card.authentication.scopes
        result["authentication"] = auth

    for skill in (card.skills or []):
        skill_dict: dict[str, Any] = {"id": skill.id, "name": skill.name}
        if skill.description:
            skill_dict["description"] = skill.description
        if skill.tags:
            skill_dict["tags"] = skill.tags
        if skill.examples:
            skill_dict["examples"] = skill.examples
        if skill.input_modes:
            skill_dict["inputModes"] = skill.input_modes
        if skill.output_modes:
            skill_dict["outputModes"] = skill.output_modes
        result["skills"].append(skill_dict)

    return result


def validate_agent_card(card: dict[str, Any]) -> list[str]:
    """Validate an Agent Card has the minimum required fields.

    Returns a list of error messages. An empty list means the card is valid.
    """
    errors: list[str] = []

    if not card.get("name"):
        errors.append("name is required")
    if not card.get("url"):
        errors.append("url is required")
    if "skills" not in card:
        errors.append("skills is required")
    if not card.get("protocolVersion"):
        errors.append("protocolVersion is required")

    url = card.get("url", "")
    if url and not url.startswith("http"):
        errors.append("url must be an HTTP(S) URL")

    skills = card.get("skills")
    if skills is not None and not isinstance(skills, list):
        errors.append("skills must be an array")

    if skills and isinstance(skills, list):
        for skill in skills:
            if not skill.get("id"):
                errors.append("each skill must have an id")
            if not skill.get("name"):
                errors.append("each skill must have a name")

    return errors
