"""Tests for AI discovery manifest and JSON-LD generation."""

from agent_layer.core.discovery import (
    AIManifest,
    AIManifestAuth,
    AIManifestContact,
    DiscoveryConfig,
    generate_ai_manifest,
    generate_json_ld,
)


class TestGenerateAIManifest:
    def test_minimal(self):
        config = DiscoveryConfig(manifest=AIManifest(name="My API"))
        result = generate_ai_manifest(config)
        assert result == {"name": "My API"}

    def test_full(self):
        config = DiscoveryConfig(
            manifest=AIManifest(
                name="My API",
                description="A great API",
                openapi_url="https://api.example.com/openapi.json",
                llms_txt_url="https://api.example.com/llms.txt",
                auth=AIManifestAuth(
                    type="bearer",
                ),
                contact=AIManifestContact(
                    email="hello@example.com",
                    url="https://example.com",
                ),
                capabilities=["search", "create"],
            )
        )
        result = generate_ai_manifest(config)
        assert result["name"] == "My API"
        assert result["description"] == "A great API"
        assert result["openapi_url"] == "https://api.example.com/openapi.json"
        assert result["llms_txt_url"] == "https://api.example.com/llms.txt"
        assert result["auth"]["type"] == "bearer"
        assert result["contact"]["email"] == "hello@example.com"
        assert result["contact"]["url"] == "https://example.com"
        assert result["capabilities"] == ["search", "create"]

    def test_with_oauth_auth(self):
        config = DiscoveryConfig(
            manifest=AIManifest(
                name="OAuth API",
                auth=AIManifestAuth(
                    type="oauth2",
                    authorization_url="https://auth.example.com/authorize",
                    token_url="https://auth.example.com/token",
                    scopes={"read": "Read access", "write": "Write access"},
                ),
            )
        )
        result = generate_ai_manifest(config)
        assert result["auth"]["type"] == "oauth2"
        assert result["auth"]["authorization_url"] == "https://auth.example.com/authorize"
        assert result["auth"]["scopes"]["read"] == "Read access"

    def test_no_optional_fields(self):
        config = DiscoveryConfig(manifest=AIManifest(name="Simple"))
        result = generate_ai_manifest(config)
        assert "description" not in result
        assert "auth" not in result
        assert "contact" not in result
        assert "capabilities" not in result


class TestGenerateJsonLd:
    def test_minimal(self):
        config = DiscoveryConfig(manifest=AIManifest(name="My API"))
        result = generate_json_ld(config)
        assert result["@context"] == "https://schema.org"
        assert result["@type"] == "WebAPI"
        assert result["name"] == "My API"

    def test_with_description(self):
        config = DiscoveryConfig(
            manifest=AIManifest(name="My API", description="A great API")
        )
        result = generate_json_ld(config)
        assert result["description"] == "A great API"

    def test_with_documentation(self):
        config = DiscoveryConfig(
            manifest=AIManifest(
                name="My API",
                openapi_url="https://api.example.com/docs",
            )
        )
        result = generate_json_ld(config)
        assert result["documentation"] == "https://api.example.com/docs"

    def test_with_contact(self):
        config = DiscoveryConfig(
            manifest=AIManifest(
                name="My API",
                contact=AIManifestContact(
                    email="hello@example.com",
                    url="https://example.com",
                ),
            )
        )
        result = generate_json_ld(config)
        assert result["url"] == "https://example.com"
        assert result["contactPoint"]["@type"] == "ContactPoint"
        assert result["contactPoint"]["email"] == "hello@example.com"

    def test_with_capabilities(self):
        config = DiscoveryConfig(
            manifest=AIManifest(
                name="My API",
                capabilities=["search", "create"],
            )
        )
        result = generate_json_ld(config)
        assert len(result["potentialAction"]) == 2
        assert result["potentialAction"][0]["@type"] == "Action"
        assert result["potentialAction"][0]["name"] == "search"

    def test_no_optional_fields(self):
        config = DiscoveryConfig(manifest=AIManifest(name="Simple"))
        result = generate_json_ld(config)
        assert "description" not in result
        assert "documentation" not in result
        assert "url" not in result
        assert "contactPoint" not in result
        assert "potentialAction" not in result
