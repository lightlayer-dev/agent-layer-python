"""Tests for llms.txt and llms-full.txt generation."""

from agent_layer.core.llms_txt import (
    LlmsTxtConfig,
    LlmsTxtSection,
    RouteMetadata,
    RouteParameter,
    generate_llms_full_txt,
    generate_llms_txt,
)


class TestGenerateLlmsTxt:
    def test_title_only(self):
        config = LlmsTxtConfig(title="My API")
        result = generate_llms_txt(config)
        assert result == "# My API\n"

    def test_title_and_description(self):
        config = LlmsTxtConfig(title="My API", description="A great API")
        result = generate_llms_txt(config)
        assert "# My API" in result
        assert "> A great API" in result

    def test_with_sections(self):
        config = LlmsTxtConfig(
            title="My API",
            sections=[
                LlmsTxtSection(title="Getting Started", content="Install the package."),
                LlmsTxtSection(title="Auth", content="Use Bearer tokens."),
            ],
        )
        result = generate_llms_txt(config)
        assert "## Getting Started" in result
        assert "Install the package." in result
        assert "## Auth" in result
        assert "Use Bearer tokens." in result

    def test_full_config(self):
        config = LlmsTxtConfig(
            title="My API",
            description="A great API for agents",
            sections=[
                LlmsTxtSection(title="Overview", content="This API does cool things."),
            ],
        )
        result = generate_llms_txt(config)
        lines = result.strip().split("\n")
        assert lines[0] == "# My API"
        assert "> A great API for agents" in result
        assert "## Overview" in result


class TestGenerateLlmsFullTxt:
    def test_no_routes(self):
        config = LlmsTxtConfig(title="My API")
        result = generate_llms_full_txt(config)
        assert "# My API" in result
        assert "API Endpoints" not in result

    def test_with_routes(self):
        config = LlmsTxtConfig(title="My API")
        routes = [
            RouteMetadata(method="GET", path="/users", summary="List all users"),
            RouteMetadata(method="POST", path="/users", summary="Create a user"),
        ]
        result = generate_llms_full_txt(config, routes)
        assert "## API Endpoints" in result
        assert "### GET /users" in result
        assert "### POST /users" in result
        assert "List all users" in result
        assert "Create a user" in result

    def test_route_with_parameters(self):
        config = LlmsTxtConfig(title="My API")
        routes = [
            RouteMetadata(
                method="GET",
                path="/users/{id}",
                summary="Get user by ID",
                parameters=[
                    RouteParameter(
                        name="id",
                        location="path",
                        required=True,
                        description="The user ID",
                    ),
                    RouteParameter(
                        name="fields",
                        location="query",
                        description="Fields to include",
                    ),
                ],
            ),
        ]
        result = generate_llms_full_txt(config, routes)
        assert "**Parameters:**" in result
        assert "`id` (path) (required) — The user ID" in result
        assert "`fields` (query) — Fields to include" in result

    def test_route_with_description(self):
        config = LlmsTxtConfig(title="API")
        routes = [
            RouteMetadata(
                method="DELETE",
                path="/users/{id}",
                summary="Delete a user",
                description="Permanently removes the user and all associated data.",
            ),
        ]
        result = generate_llms_full_txt(config, routes)
        assert "Delete a user" in result
        assert "Permanently removes" in result

    def test_includes_sections_and_routes(self):
        config = LlmsTxtConfig(
            title="My API",
            description="Full docs",
            sections=[LlmsTxtSection(title="Auth", content="Use tokens.")],
        )
        routes = [RouteMetadata(method="GET", path="/health")]
        result = generate_llms_full_txt(config, routes)
        assert "## Auth" in result
        assert "## API Endpoints" in result
        assert "### GET /health" in result
