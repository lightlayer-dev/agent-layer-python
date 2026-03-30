"""Tests for unified discovery module."""

from agent_layer.core.agents_txt import AgentsTxtRule, Permission
from agent_layer.core.llms_txt import RouteMetadata, RouteParameter
from agent_layer.core.unified_discovery import (
    DiscoveryFormats,
    UnifiedAuthConfig,
    UnifiedDiscoveryConfig,
    UnifiedSkill,
    generate_all_discovery,
    generate_unified_agents_txt,
    generate_unified_agent_card,
    generate_unified_ai_manifest,
    generate_unified_llms_full_txt,
    generate_unified_llms_txt,
)


def _make_config(**kwargs) -> UnifiedDiscoveryConfig:
    defaults = dict(
        name="Test API",
        url="https://api.example.com",
        description="A test API",
        skills=[
            UnifiedSkill(id="search", name="Search", description="Search the web"),
        ],
    )
    defaults.update(kwargs)
    return UnifiedDiscoveryConfig(**defaults)


class TestGenerateUnifiedAiManifest:
    def test_basic(self):
        result = generate_unified_ai_manifest(_make_config())
        assert result["name"] == "Test API"

    def test_with_auth(self):
        config = _make_config(auth=UnifiedAuthConfig(type="bearer"))
        result = generate_unified_ai_manifest(config)
        # bearer → api_key in AI manifest
        assert result["auth"]["type"] == "api_key"

    def test_llms_txt_url(self):
        config = _make_config()
        result = generate_unified_ai_manifest(config)
        assert result.get("llms_txt_url") == "https://api.example.com/llms.txt"


class TestGenerateUnifiedAgentCard:
    def test_basic(self):
        result = generate_unified_agent_card(_make_config())
        assert result["name"] == "Test API"
        assert result["url"] == "https://api.example.com"
        assert len(result["skills"]) == 1

    def test_with_provider(self):
        config = _make_config(
            provider_organization="TestCorp",
            provider_url="https://testcorp.com",
        )
        result = generate_unified_agent_card(config)
        assert result["provider"]["organization"] == "TestCorp"

    def test_auth_mapping(self):
        config = _make_config(auth=UnifiedAuthConfig(type="api_key"))
        result = generate_unified_agent_card(config)
        # api_key → apiKey in A2A
        assert result["authentication"]["type"] == "apiKey"


class TestGenerateUnifiedLlmsTxt:
    def test_basic(self):
        result = generate_unified_llms_txt(_make_config())
        assert "# Test API" in result
        assert "Search" in result

    def test_with_description(self):
        result = generate_unified_llms_txt(_make_config())
        assert "A test API" in result


class TestGenerateUnifiedLlmsFullTxt:
    def test_with_routes(self):
        config = _make_config(
            routes=[RouteMetadata(method="GET", path="/api/search", summary="Search endpoint")]
        )
        result = generate_unified_llms_full_txt(config)
        assert "GET /api/search" in result


class TestGenerateUnifiedAgentsTxt:
    def test_basic(self):
        config = _make_config(
            agents_txt_rules=[AgentsTxtRule(agent="*", permission=Permission.ALLOW, paths=["/"])]
        )
        result = generate_unified_agents_txt(config)
        assert "User-agent: *" in result


class TestGenerateAllDiscovery:
    def test_all_formats(self):
        config = _make_config(
            agents_txt_rules=[AgentsTxtRule(agent="*", permission=Permission.ALLOW)],
        )
        result = generate_all_discovery(config)
        assert "/.well-known/ai" in result
        assert "/.well-known/agent.json" in result
        assert "/agents.txt" in result
        assert "/llms.txt" in result
        assert "/llms-full.txt" in result

    def test_format_disabling(self):
        config = _make_config(
            formats=DiscoveryFormats(ai_manifest=False, llms_full_txt=False),
        )
        result = generate_all_discovery(config)
        assert "/.well-known/ai" not in result
        assert "/llms-full.txt" not in result
        assert "/.well-known/agent.json" in result

    def test_json_vs_string(self):
        config = _make_config()
        result = generate_all_discovery(config)
        assert isinstance(result["/.well-known/ai"], dict)
        assert isinstance(result["/.well-known/agent.json"], dict)
        assert isinstance(result["/llms.txt"], str)
