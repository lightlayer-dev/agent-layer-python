"""Tests for robots_txt core generation."""

from __future__ import annotations

from agent_layer.robots_txt import (
    AI_AGENTS,
    RobotsTxtConfig,
    RobotsTxtRule,
    generate_robots_txt,
)


def test_default_robots_txt() -> None:
    """Default config includes wildcard allow and all AI agents."""
    result = generate_robots_txt()
    assert "User-agent: *" in result
    assert "Allow: /" in result
    for agent in AI_AGENTS:
        assert f"User-agent: {agent}" in result


def test_disallow_ai_agents() -> None:
    """ai_agent_policy='disallow' blocks all AI agents."""
    config = RobotsTxtConfig(ai_agent_policy="disallow")
    result = generate_robots_txt(config)
    assert "User-agent: GPTBot" in result
    assert "Disallow: /" in result


def test_custom_ai_allow_paths() -> None:
    """Custom ai_allow paths are used for AI agent rules."""
    config = RobotsTxtConfig(ai_allow=["/api/", "/docs/"])
    result = generate_robots_txt(config)
    assert "Allow: /api/" in result
    assert "Allow: /docs/" in result


def test_custom_rules_skip_ai_agents() -> None:
    """Explicit rules skip automatic AI agent generation."""
    config = RobotsTxtConfig(
        rules=[RobotsTxtRule(user_agent="*", allow=["/"], disallow=["/admin/"])]
    )
    result = generate_robots_txt(config)
    assert "Disallow: /admin/" in result
    assert "GPTBot" not in result


def test_sitemaps() -> None:
    """Sitemaps are appended at the end."""
    config = RobotsTxtConfig(sitemaps=["https://example.com/sitemap.xml"])
    result = generate_robots_txt(config)
    assert "Sitemap: https://example.com/sitemap.xml" in result


def test_no_ai_agents() -> None:
    """include_ai_agents=False excludes AI agent rules."""
    config = RobotsTxtConfig(include_ai_agents=False)
    result = generate_robots_txt(config)
    assert "GPTBot" not in result
    assert "User-agent: *" in result


def test_crawl_delay() -> None:
    """crawl_delay is included when set."""
    config = RobotsTxtConfig(rules=[RobotsTxtRule(user_agent="*", allow=["/"], crawl_delay=10)])
    result = generate_robots_txt(config)
    assert "Crawl-delay: 10" in result
