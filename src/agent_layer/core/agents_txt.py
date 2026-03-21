"""
agents.txt — Generate, parse, and enforce agents.txt access control.

Follows the robots.txt-style convention for AI agent access control.
Each rule specifies an agent pattern and whether it's allowed/disallowed
for given paths.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from enum import Enum


class Permission(Enum):
    ALLOW = "allow"
    DISALLOW = "disallow"


@dataclass
class AgentsTxtRule:
    """A single rule in agents.txt."""

    agent: str
    """Agent name or pattern (supports * wildcard). Use '*' for all agents."""

    permission: Permission = Permission.ALLOW
    """Whether the agent is allowed or disallowed."""

    paths: list[str] = field(default_factory=lambda: ["/"])
    """Paths this rule applies to. Supports * wildcard."""

    description: str | None = None
    """Optional human-readable description of this rule."""


@dataclass
class AgentsTxtConfig:
    """Configuration for generating agents.txt."""

    rules: list[AgentsTxtRule] = field(default_factory=list)
    """List of agent access rules."""

    comment: str | None = None
    """Optional comment at the top of the file."""


def generate_agents_txt(config: AgentsTxtConfig) -> str:
    """Generate agents.txt content from configuration.

    Returns a string in the standard agents.txt format:

        # Comment
        User-agent: *
        Allow: /
        Disallow: /private

        User-agent: BadBot
        Disallow: /
    """
    lines: list[str] = []

    if config.comment:
        for comment_line in config.comment.splitlines():
            lines.append(f"# {comment_line}")
        lines.append("")

    for i, rule in enumerate(config.rules):
        if i > 0:
            lines.append("")

        if rule.description:
            lines.append(f"# {rule.description}")

        lines.append(f"User-agent: {rule.agent}")

        for path in rule.paths:
            directive = "Allow" if rule.permission == Permission.ALLOW else "Disallow"
            lines.append(f"{directive}: {path}")

    return "\n".join(lines) + "\n"


def parse_agents_txt(content: str) -> list[AgentsTxtRule]:
    """Parse agents.txt content into a list of rules.

    Handles the standard robots.txt-style format with User-agent,
    Allow, and Disallow directives.
    """
    rules: list[AgentsTxtRule] = []
    current_agent: str | None = None
    current_paths: list[str] = []
    current_permission: Permission = Permission.ALLOW
    current_description: str | None = None

    def _flush() -> None:
        nonlocal current_agent, current_paths, current_permission, current_description
        if current_agent is not None:
            rules.append(
                AgentsTxtRule(
                    agent=current_agent,
                    permission=current_permission,
                    paths=current_paths if current_paths else ["/"],
                    description=current_description,
                )
            )
        current_agent = None
        current_paths = []
        current_permission = Permission.ALLOW
        current_description = None

    last_comment: str | None = None

    for line in content.splitlines():
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            if current_agent is not None and current_paths:
                _flush()
            continue

        # Comments
        if stripped.startswith("#"):
            last_comment = stripped[1:].strip()
            continue

        # Parse directives
        match = re.match(r"^(User-agent|Allow|Disallow)\s*:\s*(.*)$", stripped, re.IGNORECASE)
        if not match:
            continue

        directive = match.group(1).lower()
        value = match.group(2).strip()

        if directive == "user-agent":
            if current_agent is not None:
                _flush()
            current_agent = value
            current_description = last_comment
            last_comment = None
        elif directive == "allow":
            current_permission = Permission.ALLOW
            if value:
                current_paths.append(value)
        elif directive == "disallow":
            current_permission = Permission.DISALLOW
            if value:
                current_paths.append(value)

    # Flush the last rule
    _flush()

    return rules


def is_agent_allowed(
    rules: list[AgentsTxtRule],
    agent_name: str,
    path: str = "/",
) -> bool:
    """Check whether a specific agent is allowed to access a given path.

    Rules are evaluated in order. More specific agent patterns take
    precedence over wildcards. If no rule matches, access is allowed
    by default (open by default, like robots.txt).
    """
    # Find matching rules, preferring specific agent matches over wildcards
    specific_matches: list[AgentsTxtRule] = []
    wildcard_matches: list[AgentsTxtRule] = []

    for rule in rules:
        if rule.agent == agent_name:
            specific_matches.append(rule)
        elif fnmatch.fnmatch(agent_name.lower(), rule.agent.lower()):
            wildcard_matches.append(rule)

    # Use specific matches first, fall back to wildcard
    matches = specific_matches if specific_matches else wildcard_matches

    if not matches:
        return True  # No matching rules → allowed by default

    # Check path against matching rules (last matching path wins)
    for rule in reversed(matches):
        for rule_path in rule.paths:
            if fnmatch.fnmatch(path, rule_path) or path.startswith(rule_path.rstrip("*")):
                return rule.permission == Permission.ALLOW

    return True  # No path match → allowed by default
