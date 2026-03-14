"""Tests for discovery (AI manifest + JSON-LD)."""

from agent_layer.discovery import generate_ai_manifest, generate_json_ld
from agent_layer.types import AIManifest, AIManifestContact, DiscoveryConfig


class TestGenerateAIManifest:
    def test_basic(self):
        config = DiscoveryConfig(manifest=AIManifest(name="My API"))
        result = generate_ai_manifest(config)
        assert result["name"] == "My API"

    def test_excludes_none(self):
        config = DiscoveryConfig(manifest=AIManifest(name="X"))
        result = generate_ai_manifest(config)
        assert "description" not in result


class TestGenerateJsonLd:
    def test_basic(self):
        config = DiscoveryConfig(manifest=AIManifest(name="X"))
        ld = generate_json_ld(config)
        assert ld["@context"] == "https://schema.org"
        assert ld["@type"] == "WebAPI"
        assert ld["name"] == "X"

    def test_with_contact(self):
        config = DiscoveryConfig(manifest=AIManifest(
            name="X",
            contact=AIManifestContact(email="a@b.com", url="https://x.com"),
        ))
        ld = generate_json_ld(config)
        assert ld["url"] == "https://x.com"
        assert ld["contactPoint"]["email"] == "a@b.com"

    def test_with_capabilities(self):
        config = DiscoveryConfig(manifest=AIManifest(name="X", capabilities=["search", "create"]))
        ld = generate_json_ld(config)
        assert len(ld["potentialAction"]) == 2
        assert ld["potentialAction"][0]["name"] == "search"
