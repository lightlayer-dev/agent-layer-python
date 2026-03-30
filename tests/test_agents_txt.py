"""Tests for agents.txt generation, parsing, and enforcement."""

from __future__ import annotations

from agent_layer.agents_txt import (
    AgentsTxtAuth,
    AgentsTxtConfig,
    AgentsTxtRateLimit,
    AgentsTxtRule,
    generate_agents_txt,
    is_agent_allowed,
    parse_agents_txt,
)


# ── Generator Tests ──────────────────────────────────────────────────────


def test_generate_minimal():
    config = AgentsTxtConfig(rules=[AgentsTxtRule(agent="*", allow=["/api/*"])])
    txt = generate_agents_txt(config)
    assert "User-agent: *" in txt
    assert "Allow: /api/*" in txt


def test_generate_full():
    config = AgentsTxtConfig(
        rules=[
            AgentsTxtRule(
                agent="*",
                allow=["/api/public/*"],
                deny=["/api/admin/*"],
                rate_limit=AgentsTxtRateLimit(max=100, window_seconds=60),
                preferred_interface="rest",
                auth=AgentsTxtAuth(
                    type="bearer",
                    endpoint="https://example.com/oauth/token",
                    docs_url="https://docs.example.com/auth",
                ),
                description="Default policy for all agents",
            ),
            AgentsTxtRule(
                agent="GPT-*",
                allow=["/*"],
                rate_limit=AgentsTxtRateLimit(max=1000, window_seconds=60),
            ),
        ],
        site_name="My API",
        contact="support@example.com",
        discovery_url="https://example.com/.well-known/ai",
    )
    txt = generate_agents_txt(config)
    assert "# Site: My API" in txt
    assert "# Contact: support@example.com" in txt
    assert "# Discovery: https://example.com/.well-known/ai" in txt
    assert "Allow: /api/public/*" in txt
    assert "Deny: /api/admin/*" in txt
    assert "Rate-limit: 100/60s" in txt
    assert "Preferred-interface: rest" in txt
    assert "Auth: bearer https://example.com/oauth/token" in txt
    assert "Auth-docs: https://docs.example.com/auth" in txt
    assert "# Default policy for all agents" in txt
    assert "User-agent: GPT-*" in txt
    assert "Rate-limit: 1000/60s" in txt


def test_generate_no_metadata():
    config = AgentsTxtConfig(rules=[AgentsTxtRule(agent="ClaudeBot")])
    txt = generate_agents_txt(config)
    assert "# agents.txt" in txt
    assert "# Site:" not in txt
    assert "User-agent: ClaudeBot" in txt


# ── Parser Tests ─────────────────────────────────────────────────────────


def test_parse_roundtrip():
    config = AgentsTxtConfig(
        rules=[
            AgentsTxtRule(
                agent="*",
                allow=["/api/*"],
                deny=["/admin/*"],
                rate_limit=AgentsTxtRateLimit(max=50, window_seconds=30),
                preferred_interface="mcp",
                auth=AgentsTxtAuth(type="api_key", endpoint="https://example.com/keys"),
            ),
        ],
        site_name="Test API",
        contact="test@example.com",
        discovery_url="https://example.com/.well-known/ai",
    )
    txt = generate_agents_txt(config)
    parsed = parse_agents_txt(txt)

    assert parsed.site_name == "Test API"
    assert parsed.contact == "test@example.com"
    assert parsed.discovery_url == "https://example.com/.well-known/ai"
    assert len(parsed.rules) == 1

    rule = parsed.rules[0]
    assert rule.agent == "*"
    assert rule.allow == ["/api/*"]
    assert rule.deny == ["/admin/*"]
    assert rule.rate_limit is not None
    assert rule.rate_limit.max == 50
    assert rule.rate_limit.window_seconds == 30
    assert rule.preferred_interface == "mcp"
    assert rule.auth is not None
    assert rule.auth.type == "api_key"
    assert rule.auth.endpoint == "https://example.com/keys"


def test_parse_multiple_rules():
    txt = """# agents.txt — AI Agent Access Policy
# Site: Multi-Rule API

User-agent: *
Allow: /api/public/*
Deny: /api/private/*

User-agent: GPT-*
Allow: /*

User-agent: ClaudeBot
Deny: /*
"""
    parsed = parse_agents_txt(txt)
    assert len(parsed.rules) == 3
    assert parsed.rules[0].agent == "*"
    assert parsed.rules[1].agent == "GPT-*"
    assert parsed.rules[2].agent == "ClaudeBot"


def test_parse_empty():
    parsed = parse_agents_txt("")
    assert len(parsed.rules) == 0


# ── Matcher Tests ────────────────────────────────────────────────────────


def test_allowed_wildcard():
    config = AgentsTxtConfig(rules=[AgentsTxtRule(agent="*", allow=["/api/*"])])
    assert is_agent_allowed(config, "SomeBot", "/api/data") is True
    assert is_agent_allowed(config, "SomeBot", "/admin") is False


def test_denied_path():
    config = AgentsTxtConfig(rules=[AgentsTxtRule(agent="*", allow=["/*"], deny=["/admin/*"])])
    assert is_agent_allowed(config, "Bot", "/api/data") is True
    assert is_agent_allowed(config, "Bot", "/admin/users") is False


def test_exact_agent_match():
    config = AgentsTxtConfig(
        rules=[
            AgentsTxtRule(agent="*", deny=["/*"]),
            AgentsTxtRule(agent="TrustedBot", allow=["/*"]),
        ]
    )
    assert is_agent_allowed(config, "TrustedBot", "/api/data") is True
    assert is_agent_allowed(config, "RandomBot", "/api/data") is False


def test_pattern_agent_match():
    config = AgentsTxtConfig(
        rules=[
            AgentsTxtRule(agent="*", deny=["/*"]),
            AgentsTxtRule(agent="GPT-*", allow=["/api/*"]),
        ]
    )
    assert is_agent_allowed(config, "GPT-4", "/api/chat") is True
    assert is_agent_allowed(config, "GPT-4", "/admin") is False
    assert is_agent_allowed(config, "Claude", "/api/chat") is False


def test_no_matching_rule():
    config = AgentsTxtConfig(rules=[AgentsTxtRule(agent="SpecificBot", allow=["/*"])])
    assert is_agent_allowed(config, "OtherBot", "/api") is None


def test_no_allow_deny_implicit_allow():
    config = AgentsTxtConfig(rules=[AgentsTxtRule(agent="*")])
    assert is_agent_allowed(config, "AnyBot", "/anything") is True


def test_priority_exact_over_pattern_over_wildcard():
    config = AgentsTxtConfig(
        rules=[
            AgentsTxtRule(agent="*", allow=["/public/*"]),
            AgentsTxtRule(agent="GPT-*", allow=["/api/*"]),
            AgentsTxtRule(agent="GPT-4", allow=["/*"]),
        ]
    )
    # Exact match: GPT-4 → allow everything
    assert is_agent_allowed(config, "GPT-4", "/admin") is True
    # Pattern match: GPT-3.5 → only /api/*
    assert is_agent_allowed(config, "GPT-3.5", "/api/v1") is True
    assert is_agent_allowed(config, "GPT-3.5", "/admin") is False
    # Wildcard: Claude → only /public/*
    assert is_agent_allowed(config, "Claude", "/public/data") is True
    assert is_agent_allowed(config, "Claude", "/api/v1") is False
