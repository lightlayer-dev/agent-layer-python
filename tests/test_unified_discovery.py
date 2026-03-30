"""Tests for unified multi-format discovery."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_layer.unified_discovery import (
    AgentsTxtBlock,
    AgentsTxtConfig,
    AgentsTxtRule,
    DiscoveryFormats,
    UnifiedAuthConfig,
    UnifiedDiscoveryConfig,
    UnifiedSkill,
    generate_agents_txt,
    generate_all_discovery,
    generate_unified_agent_card,
    generate_unified_ai_manifest,
    generate_unified_llms_full_txt,
    generate_unified_llms_txt,
    is_format_enabled,
)
from agent_layer.fastapi.unified_discovery import unified_discovery_routes
from agent_layer.types import AIManifestContact, RouteMetadata, RouteParameter


@pytest.fixture
def base_config() -> UnifiedDiscoveryConfig:
    return UnifiedDiscoveryConfig(
        name="Widget API",
        description="REST API for widgets",
        url="https://api.example.com",
        version="2.0.0",
        contact=AIManifestContact(email="support@example.com", url="https://example.com"),
        openapi_url="https://api.example.com/openapi.json",
        documentation_url="https://docs.example.com",
        capabilities=["search", "crud"],
        auth=UnifiedAuthConfig(
            type="oauth2",
            authorization_url="https://auth.example.com/authorize",
            token_url="https://auth.example.com/token",
            scopes={"read": "Read access", "write": "Write access"},
        ),
        skills=[
            UnifiedSkill(
                id="search",
                name="Search Widgets",
                description="Full-text search across all widgets",
                tags=["search", "query"],
                examples=["Find red widgets", "Search for large widgets"],
                input_modes=["text/plain"],
                output_modes=["application/json"],
            ),
            UnifiedSkill(
                id="crud",
                name="Widget CRUD",
                description="Create, read, update, delete widgets",
                tags=["crud"],
            ),
        ],
        routes=[
            RouteMetadata(method="GET", path="/api/widgets", summary="List widgets"),
            RouteMetadata(
                method="POST",
                path="/api/widgets",
                summary="Create a widget",
                parameters=[
                    RouteParameter(
                        name="name", location="body", required=True, description="Widget name"
                    )
                ],
            ),
        ],
    )


class TestIsFormatEnabled:
    def test_default_all_true(self):
        formats = DiscoveryFormats()
        assert is_format_enabled(formats, "well_known_ai")
        assert is_format_enabled(formats, "agent_card")
        assert is_format_enabled(formats, "agents_txt")
        assert is_format_enabled(formats, "llms_txt")

    def test_disabled(self):
        formats = DiscoveryFormats(agents_txt=False)
        assert not is_format_enabled(formats, "agents_txt")
        assert is_format_enabled(formats, "well_known_ai")


class TestGenerateUnifiedAIManifest:
    def test_basic(self, base_config):
        manifest = generate_unified_ai_manifest(base_config)
        assert manifest["name"] == "Widget API"
        assert manifest["description"] == "REST API for widgets"
        assert manifest["llms_txt_url"] == "https://api.example.com/llms.txt"

    def test_no_llms_url_when_disabled(self, base_config):
        base_config.formats = DiscoveryFormats(llms_txt=False)
        manifest = generate_unified_ai_manifest(base_config)
        assert "llms_txt_url" not in manifest or manifest.get("llms_txt_url") is None

    def test_bearer_maps_to_api_key(self, base_config):
        base_config.auth = UnifiedAuthConfig(type="bearer")
        manifest = generate_unified_ai_manifest(base_config)
        assert manifest["auth"]["type"] == "api_key"


class TestGenerateUnifiedAgentCard:
    def test_basic(self, base_config):
        card = generate_unified_agent_card(base_config)
        assert card["name"] == "Widget API"
        assert card["url"] == "https://api.example.com"
        assert card["protocolVersion"] == "1.0.0"
        assert len(card["skills"]) == 2
        assert card["skills"][0]["id"] == "search"

    def test_api_key_maps_to_apiKey(self, base_config):
        base_config.auth = UnifiedAuthConfig(type="api_key", **{"in": "header"}, name="X-API-Key")
        card = generate_unified_agent_card(base_config)
        assert card["authentication"]["type"] == "apiKey"

    def test_documentation_url(self, base_config):
        card = generate_unified_agent_card(base_config)
        assert card["documentationUrl"] == "https://docs.example.com"

    def test_falls_back_to_openapi_url(self, base_config):
        base_config.documentation_url = None
        card = generate_unified_agent_card(base_config)
        assert card["documentationUrl"] == "https://api.example.com/openapi.json"


class TestGenerateUnifiedLlmsTxt:
    def test_basic(self, base_config):
        txt = generate_unified_llms_txt(base_config)
        assert "# Widget API" in txt
        assert "> REST API for widgets" in txt
        assert "## Search Widgets" in txt
        assert "- Find red widgets" in txt

    def test_extra_sections(self, base_config):
        from agent_layer.types import LlmsTxtSection

        base_config.llms_txt_sections = [
            LlmsTxtSection(title="Auth", content="Use OAuth2 bearer tokens.")
        ]
        txt = generate_unified_llms_txt(base_config)
        assert "## Auth" in txt
        assert "Use OAuth2 bearer tokens." in txt


class TestGenerateUnifiedLlmsFullTxt:
    def test_includes_routes(self, base_config):
        txt = generate_unified_llms_full_txt(base_config)
        assert "## API Endpoints" in txt
        assert "### GET /api/widgets" in txt
        assert "### POST /api/widgets" in txt


class TestGenerateAgentsTxt:
    def test_default(self, base_config):
        txt = generate_agents_txt(base_config)
        assert "User-agent: *" in txt
        assert "Allow: /" in txt

    def test_with_blocks(self, base_config):
        base_config.agents_txt = AgentsTxtConfig(
            blocks=[
                AgentsTxtBlock(
                    user_agent="*",
                    rules=[
                        AgentsTxtRule(path="/api/*", permission="allow"),
                        AgentsTxtRule(path="/admin/*", permission="disallow"),
                    ],
                ),
                AgentsTxtBlock(
                    user_agent="GPTBot",
                    rules=[AgentsTxtRule(path="/", permission="disallow")],
                ),
            ],
            sitemap_url="https://api.example.com/sitemap.xml",
            comment="AI agent access rules",
        )
        txt = generate_agents_txt(base_config)
        assert "# AI agent access rules" in txt
        assert "Allow: /api/*" in txt
        assert "Disallow: /admin/*" in txt
        assert "User-agent: GPTBot" in txt
        assert "Sitemap: https://api.example.com/sitemap.xml" in txt


class TestGenerateAllDiscovery:
    def test_all_formats(self, base_config):
        docs = generate_all_discovery(base_config)
        assert "/.well-known/ai" in docs
        assert "/.well-known/agent.json" in docs
        assert "/llms.txt" in docs
        assert "/llms-full.txt" in docs
        assert "/agents.txt" in docs

    def test_skips_disabled(self, base_config):
        base_config.formats = DiscoveryFormats(agents_txt=False, llms_txt=False)
        docs = generate_all_discovery(base_config)
        assert "/agents.txt" not in docs
        assert "/llms.txt" not in docs
        assert "/.well-known/ai" in docs


class TestFastAPIIntegration:
    def test_all_endpoints(self, base_config):
        app = FastAPI()
        app.include_router(unified_discovery_routes(base_config))
        client = TestClient(app)

        resp = client.get("/.well-known/ai")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Widget API"

        resp = client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        assert resp.json()["protocolVersion"] == "1.0.0"

        resp = client.get("/agents.txt")
        assert resp.status_code == 200
        assert "User-agent: *" in resp.text

        resp = client.get("/llms.txt")
        assert resp.status_code == 200
        assert "# Widget API" in resp.text

        resp = client.get("/llms-full.txt")
        assert resp.status_code == 200
        assert "## API Endpoints" in resp.text

    def test_disabled_formats_404(self, base_config):
        base_config.formats = DiscoveryFormats(agents_txt=False, llms_txt=False)
        app = FastAPI()
        app.include_router(unified_discovery_routes(base_config))
        client = TestClient(app)

        assert client.get("/.well-known/ai").status_code == 200
        assert client.get("/agents.txt").status_code in (404, 405)
        assert client.get("/llms.txt").status_code in (404, 405)
