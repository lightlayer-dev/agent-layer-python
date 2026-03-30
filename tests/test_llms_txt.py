"""Tests for llms.txt generation."""

from agent_layer.llms_txt import generate_llms_txt, generate_llms_full_txt
from agent_layer.types import LlmsTxtConfig, LlmsTxtSection, RouteMetadata, RouteParameter


class TestGenerateLlmsTxt:
    def test_basic(self):
        txt = generate_llms_txt(LlmsTxtConfig(title="My API"))
        assert txt.startswith("# My API\n")

    def test_with_description(self):
        txt = generate_llms_txt(LlmsTxtConfig(title="X", description="A cool API"))
        assert "> A cool API" in txt

    def test_with_sections(self):
        txt = generate_llms_txt(
            LlmsTxtConfig(
                title="X",
                sections=[LlmsTxtSection(title="Auth", content="Use Bearer tokens.")],
            )
        )
        assert "## Auth" in txt
        assert "Use Bearer tokens." in txt


class TestGenerateLlmsFullTxt:
    def test_includes_routes(self):
        txt = generate_llms_full_txt(
            LlmsTxtConfig(title="API"),
            routes=[RouteMetadata(method="GET", path="/users", summary="List users")],
        )
        assert "### GET /users" in txt
        assert "List users" in txt

    def test_route_parameters(self):
        txt = generate_llms_full_txt(
            LlmsTxtConfig(title="API"),
            routes=[
                RouteMetadata(
                    method="POST",
                    path="/users",
                    parameters=[
                        RouteParameter(
                            name="name", location="body", required=True, description="User name"
                        )
                    ],
                )
            ],
        )
        assert "`name` (body)" in txt
        assert "(required)" in txt
        assert "User name" in txt

    def test_empty_routes(self):
        txt = generate_llms_full_txt(LlmsTxtConfig(title="API"), routes=[])
        assert "API Endpoints" not in txt
