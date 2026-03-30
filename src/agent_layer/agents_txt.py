"""
agents.txt — A robots.txt-style permission and capability declaration for AI agents.

Generates a human- and machine-readable text file at /agents.txt that tells agents:
- What paths they can access
- What rate limits apply
- What auth is required
- What interface (REST, MCP, etc.) is preferred

Inspired by robots.txt but purpose-built for the agentic web.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional


# ── Types ────────────────────────────────────────────────────────────────


@dataclass
class AgentsTxtRateLimit:
    """Rate limit declaration for agents.txt."""

    max: int
    """Maximum requests per window."""
    window_seconds: int = 60
    """Window size in seconds."""


@dataclass
class AgentsTxtAuth:
    """Auth requirement for an agents.txt rule."""

    type: Literal["bearer", "api_key", "oauth2", "none"]
    endpoint: Optional[str] = None
    """URL to obtain credentials."""
    docs_url: Optional[str] = None
    """Docs URL for auth."""


@dataclass
class AgentsTxtRule:
    """A single rule block in agents.txt."""

    agent: str
    """Agent name pattern to match (e.g. '*', 'GPT-*', 'ClaudeBot')."""
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)
    rate_limit: Optional[AgentsTxtRateLimit] = None
    preferred_interface: Optional[Literal["rest", "mcp", "graphql", "a2a"]] = None
    auth: Optional[AgentsTxtAuth] = None
    description: Optional[str] = None


@dataclass
class AgentsTxtConfig:
    """Top-level agents.txt configuration."""

    rules: list[AgentsTxtRule]
    site_name: Optional[str] = None
    contact: Optional[str] = None
    discovery_url: Optional[str] = None
    enforce: bool = False
    """Whether to enforce rules as middleware (deny non-matching agents)."""


# Standalone variant for middleware configs that include enforce
AgentsTxtMiddlewareConfig = AgentsTxtConfig


# ── Generator ────────────────────────────────────────────────────────────


def generate_agents_txt(config: AgentsTxtConfig) -> str:
    """Generate the agents.txt file content from configuration."""
    lines: list[str] = []

    lines.append("# agents.txt — AI Agent Access Policy")

    if config.site_name:
        lines.append(f"# Site: {config.site_name}")

    if config.contact:
        lines.append(f"# Contact: {config.contact}")

    if config.discovery_url:
        lines.append(f"# Discovery: {config.discovery_url}")

    for rule in config.rules:
        lines.append("")
        lines.append(f"User-agent: {rule.agent}")

        if rule.description:
            lines.append(f"# {rule.description}")

        for path in rule.allow:
            lines.append(f"Allow: {path}")

        for path in rule.deny:
            lines.append(f"Deny: {path}")

        if rule.rate_limit:
            window = rule.rate_limit.window_seconds
            lines.append(f"Rate-limit: {rule.rate_limit.max}/{window}s")

        if rule.preferred_interface:
            lines.append(f"Preferred-interface: {rule.preferred_interface}")

        if rule.auth:
            auth_parts = [rule.auth.type]
            if rule.auth.endpoint:
                auth_parts.append(rule.auth.endpoint)
            lines.append(f"Auth: {' '.join(auth_parts)}")
            if rule.auth.docs_url:
                lines.append(f"Auth-docs: {rule.auth.docs_url}")

    return "\n".join(lines) + "\n"


# ── Parser ───────────────────────────────────────────────────────────────


def parse_agents_txt(content: str) -> AgentsTxtConfig:
    """Parse an agents.txt string back into structured rules."""
    config = AgentsTxtConfig(rules=[])
    current_rule: Optional[AgentsTxtRule] = None

    for raw_line in content.split("\n"):
        line = raw_line.strip()

        # Header comments
        if line.startswith("# Site:"):
            config.site_name = line[len("# Site:") :].strip()
            continue
        if line.startswith("# Contact:"):
            config.contact = line[len("# Contact:") :].strip()
            continue
        if line.startswith("# Discovery:"):
            config.discovery_url = line[len("# Discovery:") :].strip()
            continue

        # Skip comments and blank lines between rules
        if line == "" or (line.startswith("#") and current_rule is None):
            continue

        # Inline comments within a rule block — skip
        if line.startswith("#") and current_rule is not None:
            continue

        # Parse directives
        colon_idx = line.find(":")
        if colon_idx == -1:
            continue

        directive = line[:colon_idx].strip().lower()
        value = line[colon_idx + 1 :].strip()

        if directive == "user-agent":
            current_rule = AgentsTxtRule(agent=value)
            config.rules.append(current_rule)
            continue

        if current_rule is None:
            continue

        if directive == "allow":
            current_rule.allow.append(value)
        elif directive == "deny":
            current_rule.deny.append(value)
        elif directive == "rate-limit":
            match = re.match(r"^(\d+)/(\d+)s$", value)
            if match:
                current_rule.rate_limit = AgentsTxtRateLimit(
                    max=int(match.group(1)),
                    window_seconds=int(match.group(2)),
                )
        elif directive == "preferred-interface":
            if value in ("rest", "mcp", "graphql", "a2a"):
                current_rule.preferred_interface = value  # type: ignore[assignment]
        elif directive == "auth":
            parts = value.split()
            current_rule.auth = AgentsTxtAuth(
                type=parts[0],  # type: ignore[arg-type]
                endpoint=parts[1] if len(parts) > 1 else None,
            )
        elif directive == "auth-docs":
            if current_rule.auth:
                current_rule.auth.docs_url = value

    return config


# ── Matcher ──────────────────────────────────────────────────────────────


def _path_matches(path: str, pattern: str) -> bool:
    """Simple glob-style path matching (trailing * for prefix)."""
    if pattern in ("*", "/*"):
        return True
    if pattern.endswith("*"):
        prefix = pattern[:-1]
        return path.startswith(prefix)
    return path == pattern


def _find_matching_rule(rules: list[AgentsTxtRule], agent_name: str) -> Optional[AgentsTxtRule]:
    """Find the best matching rule. Priority: exact > prefix pattern > wildcard."""
    wildcard_rule: Optional[AgentsTxtRule] = None
    pattern_rule: Optional[AgentsTxtRule] = None
    exact_rule: Optional[AgentsTxtRule] = None

    for rule in rules:
        if rule.agent == "*":
            wildcard_rule = rule
        elif rule.agent.endswith("*"):
            prefix = rule.agent[:-1]
            if agent_name.startswith(prefix):
                pattern_rule = rule
        elif rule.agent == agent_name:
            exact_rule = rule

    return exact_rule or pattern_rule or wildcard_rule


def is_agent_allowed(config: AgentsTxtConfig, agent_name: str, path: str) -> Optional[bool]:
    """
    Check whether a given agent + path combination is allowed.

    Returns True if allowed, False if denied, None if no matching rule.
    """
    matching_rule = _find_matching_rule(config.rules, agent_name)

    if matching_rule is None:
        return None

    # Deny takes precedence within the same rule
    for pattern in matching_rule.deny:
        if _path_matches(path, pattern):
            return False

    if matching_rule.allow:
        for pattern in matching_rule.allow:
            if _path_matches(path, pattern):
                return True
        # Allow rules exist but none matched → deny
        return False

    # No allow/deny rules → implicitly allowed
    return True
