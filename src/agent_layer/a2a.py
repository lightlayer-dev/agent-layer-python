"""A2A (Agent-to-Agent) Protocol — Agent Card generation.

Implements the /.well-known/agent.json endpoint per Google's A2A protocol
specification (https://a2a-protocol.org).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── A2A Agent Card Types ────────────────────────────────────────────────


class A2ASkill(BaseModel):
    """A skill/capability the agent can perform."""

    id: str
    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    input_modes: list[str] = Field(default_factory=list)
    output_modes: list[str] = Field(default_factory=list)


class A2AAuthScheme(BaseModel):
    """Authentication scheme the agent supports."""

    type: str
    in_: str | None = Field(None, alias="in")
    name: str | None = None
    authorization_url: str | None = None
    token_url: str | None = None
    scopes: dict[str, str] | None = None

    model_config = {"populate_by_name": True}


class A2AProvider(BaseModel):
    """Provider/organization info."""

    organization: str
    url: str | None = None


class A2ACapabilities(BaseModel):
    """Capabilities the agent supports."""

    streaming: bool | None = None
    push_notifications: bool | None = None
    state_transition_history: bool | None = None


class A2AAgentCard(BaseModel):
    """The full Agent Card document served at /.well-known/agent.json."""

    protocol_version: str = "1.0.0"
    name: str
    description: str | None = None
    url: str
    provider: A2AProvider | None = None
    version: str | None = None
    documentation_url: str | None = None
    capabilities: A2ACapabilities | None = None
    authentication: A2AAuthScheme | None = None
    default_input_modes: list[str] = Field(default_factory=lambda: ["text/plain"])
    default_output_modes: list[str] = Field(default_factory=lambda: ["text/plain"])
    skills: list[A2ASkill] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class A2AConfig(BaseModel):
    """Configuration for generating an Agent Card."""

    card: A2AAgentCard


# ── Generator ───────────────────────────────────────────────────────────


def generate_agent_card(config: A2AConfig) -> dict[str, Any]:
    """Generate a valid A2A Agent Card JSON-serializable dict.

    Uses camelCase keys to match the A2A protocol spec.
    """
    card = config.card

    result: dict[str, Any] = {
        "protocolVersion": card.protocol_version,
        "name": card.name,
        "url": card.url,
        "defaultInputModes": card.default_input_modes,
        "defaultOutputModes": card.default_output_modes,
        "skills": [_serialize_skill(s) for s in card.skills],
    }

    if card.description:
        result["description"] = card.description
    if card.version:
        result["version"] = card.version
    if card.documentation_url:
        result["documentationUrl"] = card.documentation_url
    if card.provider:
        result["provider"] = _serialize_provider(card.provider)
    if card.capabilities:
        result["capabilities"] = _serialize_capabilities(card.capabilities)
    if card.authentication:
        result["authentication"] = _serialize_auth(card.authentication)

    return result


def validate_agent_card(card: dict[str, Any]) -> list[str]:
    """Validate an Agent Card dict has minimum required fields.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []

    if not card.get("name"):
        errors.append("name is required")
    if not card.get("url"):
        errors.append("url is required")
    if "skills" not in card:
        errors.append("skills is required")
    if not card.get("protocolVersion") and not card.get("protocol_version"):
        errors.append("protocolVersion is required")

    url = card.get("url", "")
    if url and not url.startswith("http"):
        errors.append("url must be an HTTP(S) URL")

    skills = card.get("skills")
    if skills is not None:
        if not isinstance(skills, list):
            errors.append("skills must be an array")
        else:
            for skill in skills:
                if not skill.get("id"):
                    errors.append("each skill must have an id")
                if not skill.get("name"):
                    errors.append("each skill must have a name")

    return errors


# ── Serialization helpers ───────────────────────────────────────────────


def _serialize_skill(skill: A2ASkill) -> dict[str, Any]:
    result: dict[str, Any] = {"id": skill.id, "name": skill.name}
    if skill.description:
        result["description"] = skill.description
    if skill.tags:
        result["tags"] = skill.tags
    if skill.examples:
        result["examples"] = skill.examples
    if skill.input_modes:
        result["inputModes"] = skill.input_modes
    if skill.output_modes:
        result["outputModes"] = skill.output_modes
    return result


def _serialize_provider(provider: A2AProvider) -> dict[str, Any]:
    result: dict[str, Any] = {"organization": provider.organization}
    if provider.url:
        result["url"] = provider.url
    return result


def _serialize_capabilities(caps: A2ACapabilities) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if caps.streaming is not None:
        result["streaming"] = caps.streaming
    if caps.push_notifications is not None:
        result["pushNotifications"] = caps.push_notifications
    if caps.state_transition_history is not None:
        result["stateTransitionHistory"] = caps.state_transition_history
    return result


def _serialize_auth(auth: A2AAuthScheme) -> dict[str, Any]:
    result: dict[str, Any] = {"type": auth.type}
    if auth.in_:
        result["in"] = auth.in_
    if auth.name:
        result["name"] = auth.name
    if auth.authorization_url:
        result["authorizationUrl"] = auth.authorization_url
    if auth.token_url:
        result["tokenUrl"] = auth.token_url
    if auth.scopes:
        result["scopes"] = auth.scopes
    return result
