"""robots.txt generation with AI agent awareness.

Generates a robots.txt that explicitly addresses AI agents (GPTBot, ClaudeBot, etc.)
to signal intentional access control rather than leaving it ambiguous.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Well-known AI agents ────────────────────────────────────────────────

AI_AGENTS: list[str] = [
    "GPTBot",
    "ChatGPT-User",
    "Google-Extended",
    "Anthropic",
    "ClaudeBot",
    "CCBot",
    "Amazonbot",
    "Bytespider",
    "Applebot-Extended",
    "PerplexityBot",
    "Cohere-ai",
]


# ── Types ───────────────────────────────────────────────────────────────


class RobotsTxtRule(BaseModel):
    """A single robots.txt rule block."""

    user_agent: str
    allow: list[str] = Field(default_factory=list)
    disallow: list[str] = Field(default_factory=list)
    crawl_delay: int | None = None


class RobotsTxtConfig(BaseModel):
    """Configuration for robots.txt generation."""

    rules: list[RobotsTxtRule] | None = None
    sitemaps: list[str] = Field(default_factory=list)
    include_ai_agents: bool = True
    ai_agent_policy: str = "allow"  # "allow" or "disallow"
    ai_allow: list[str] = Field(default_factory=lambda: ["/"])
    ai_disallow: list[str] = Field(default_factory=list)


# ── Generator ───────────────────────────────────────────────────────────


def generate_robots_txt(config: RobotsTxtConfig | None = None) -> str:
    """Generate a robots.txt string with AI agent awareness."""
    if config is None:
        config = RobotsTxtConfig()

    lines: list[str] = []

    if config.rules:
        for rule in config.rules:
            lines.append(f"User-agent: {rule.user_agent}")
            for path in rule.allow:
                lines.append(f"Allow: {path}")
            for path in rule.disallow:
                lines.append(f"Disallow: {path}")
            if rule.crawl_delay is not None:
                lines.append(f"Crawl-delay: {rule.crawl_delay}")
            lines.append("")
    else:
        lines.append("User-agent: *")
        lines.append("Allow: /")
        lines.append("")

    # Add AI agent rules if requested (default: true)
    if config.include_ai_agents and not config.rules:
        for agent in AI_AGENTS:
            lines.append(f"User-agent: {agent}")
            if config.ai_agent_policy == "allow":
                for path in config.ai_allow:
                    lines.append(f"Allow: {path}")
                for path in config.ai_disallow:
                    lines.append(f"Disallow: {path}")
            else:
                lines.append("Disallow: /")
            lines.append("")

    # Add sitemaps
    for sitemap in config.sitemaps:
        lines.append(f"Sitemap: {sitemap}")

    return "\n".join(lines).rstrip() + "\n"
