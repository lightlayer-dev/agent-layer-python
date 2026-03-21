"""Tests for agents.txt generation, parsing, and enforcement."""

from agent_layer.core.agents_txt import (
    AgentsTxtConfig,
    AgentsTxtRule,
    Permission,
    generate_agents_txt,
    is_agent_allowed,
    parse_agents_txt,
)


class TestGenerateAgentsTxt:
    def test_empty_config(self):
        config = AgentsTxtConfig()
        result = generate_agents_txt(config)
        assert result == "\n"

    def test_single_allow_all(self):
        config = AgentsTxtConfig(
            rules=[AgentsTxtRule(agent="*", permission=Permission.ALLOW, paths=["/"])]
        )
        result = generate_agents_txt(config)
        assert "User-agent: *" in result
        assert "Allow: /" in result

    def test_disallow_rule(self):
        config = AgentsTxtConfig(
            rules=[
                AgentsTxtRule(
                    agent="BadBot",
                    permission=Permission.DISALLOW,
                    paths=["/"],
                )
            ]
        )
        result = generate_agents_txt(config)
        assert "User-agent: BadBot" in result
        assert "Disallow: /" in result

    def test_multiple_rules(self):
        config = AgentsTxtConfig(
            rules=[
                AgentsTxtRule(agent="*", permission=Permission.ALLOW, paths=["/"]),
                AgentsTxtRule(
                    agent="BadBot",
                    permission=Permission.DISALLOW,
                    paths=["/api", "/admin"],
                ),
            ]
        )
        result = generate_agents_txt(config)
        assert "User-agent: *" in result
        assert "User-agent: BadBot" in result
        assert "Disallow: /api" in result
        assert "Disallow: /admin" in result

    def test_comment(self):
        config = AgentsTxtConfig(
            comment="This is a test",
            rules=[AgentsTxtRule(agent="*")],
        )
        result = generate_agents_txt(config)
        assert "# This is a test" in result

    def test_rule_description(self):
        config = AgentsTxtConfig(
            rules=[
                AgentsTxtRule(
                    agent="GPTBot",
                    permission=Permission.ALLOW,
                    description="Allow OpenAI's bot",
                )
            ]
        )
        result = generate_agents_txt(config)
        assert "# Allow OpenAI's bot" in result

    def test_multiple_paths(self):
        config = AgentsTxtConfig(
            rules=[
                AgentsTxtRule(
                    agent="*",
                    permission=Permission.ALLOW,
                    paths=["/api", "/docs", "/public"],
                )
            ]
        )
        result = generate_agents_txt(config)
        assert result.count("Allow:") == 3


class TestParseAgentsTxt:
    def test_parse_simple(self):
        content = "User-agent: *\nAllow: /\n"
        rules = parse_agents_txt(content)
        assert len(rules) == 1
        assert rules[0].agent == "*"
        assert rules[0].permission == Permission.ALLOW
        assert rules[0].paths == ["/"]

    def test_parse_disallow(self):
        content = "User-agent: BadBot\nDisallow: /\n"
        rules = parse_agents_txt(content)
        assert len(rules) == 1
        assert rules[0].agent == "BadBot"
        assert rules[0].permission == Permission.DISALLOW

    def test_parse_multiple_rules(self):
        content = """User-agent: *
Allow: /

User-agent: BadBot
Disallow: /api
"""
        rules = parse_agents_txt(content)
        assert len(rules) == 2
        assert rules[0].agent == "*"
        assert rules[1].agent == "BadBot"

    def test_parse_with_comments(self):
        content = """# Main rule
User-agent: *
Allow: /
"""
        rules = parse_agents_txt(content)
        assert len(rules) == 1
        assert rules[0].description == "Main rule"

    def test_parse_empty(self):
        rules = parse_agents_txt("")
        assert len(rules) == 0

    def test_roundtrip(self):
        config = AgentsTxtConfig(
            rules=[
                AgentsTxtRule(agent="*", permission=Permission.ALLOW, paths=["/"]),
                AgentsTxtRule(agent="BadBot", permission=Permission.DISALLOW, paths=["/api"]),
            ]
        )
        text = generate_agents_txt(config)
        parsed = parse_agents_txt(text)
        assert len(parsed) == 2
        assert parsed[0].agent == "*"
        assert parsed[1].agent == "BadBot"


class TestIsAgentAllowed:
    def test_no_rules_allows_all(self):
        assert is_agent_allowed([], "AnyBot") is True

    def test_allow_all(self):
        rules = [AgentsTxtRule(agent="*", permission=Permission.ALLOW, paths=["/"])]
        assert is_agent_allowed(rules, "AnyBot", "/") is True

    def test_disallow_specific_agent(self):
        rules = [
            AgentsTxtRule(agent="*", permission=Permission.ALLOW, paths=["/"]),
            AgentsTxtRule(agent="BadBot", permission=Permission.DISALLOW, paths=["/"]),
        ]
        assert is_agent_allowed(rules, "GoodBot", "/") is True
        assert is_agent_allowed(rules, "BadBot", "/") is False

    def test_disallow_specific_path(self):
        rules = [
            AgentsTxtRule(agent="*", permission=Permission.ALLOW, paths=["/"]),
            AgentsTxtRule(agent="*", permission=Permission.DISALLOW, paths=["/private"]),
        ]
        assert is_agent_allowed(rules, "Bot", "/public") is True
        assert is_agent_allowed(rules, "Bot", "/private") is False

    def test_wildcard_agent_pattern(self):
        rules = [
            AgentsTxtRule(agent="GPT*", permission=Permission.ALLOW, paths=["/"]),
        ]
        assert is_agent_allowed(rules, "GPTBot", "/") is True
        assert is_agent_allowed(rules, "GPT-4", "/") is True

    def test_specific_beats_wildcard(self):
        rules = [
            AgentsTxtRule(agent="*", permission=Permission.DISALLOW, paths=["/"]),
            AgentsTxtRule(agent="GoodBot", permission=Permission.ALLOW, paths=["/"]),
        ]
        assert is_agent_allowed(rules, "GoodBot", "/") is True
        assert is_agent_allowed(rules, "OtherBot", "/") is False

    def test_default_path(self):
        rules = [AgentsTxtRule(agent="*", permission=Permission.ALLOW)]
        assert is_agent_allowed(rules, "Bot") is True
