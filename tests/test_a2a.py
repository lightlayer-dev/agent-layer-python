"""Tests for A2A Agent Card generation."""

import pytest

from agent_layer.a2a import (
    A2AAgentCard,
    A2AConfig,
    A2ASkill,
    A2AProvider,
    A2ACapabilities,
    A2AAuthScheme,
    generate_agent_card,
    validate_agent_card,
)


@pytest.fixture
def minimal_config():
    return A2AConfig(
        card=A2AAgentCard(
            name="test-agent",
            url="https://example.com/agent",
            skills=[A2ASkill(id="search", name="Web Search", description="Search the web")],
        )
    )


class TestGenerateAgentCard:
    def test_minimal_config(self, minimal_config):
        card = generate_agent_card(minimal_config)
        assert card["name"] == "test-agent"
        assert card["url"] == "https://example.com/agent"
        assert card["protocolVersion"] == "1.0.0"
        assert len(card["skills"]) == 1
        assert card["skills"][0]["id"] == "search"

    def test_default_modes(self, minimal_config):
        card = generate_agent_card(minimal_config)
        assert card["defaultInputModes"] == ["text/plain"]
        assert card["defaultOutputModes"] == ["text/plain"]

    def test_custom_modes(self):
        config = A2AConfig(
            card=A2AAgentCard(
                name="test",
                url="https://example.com",
                default_input_modes=["application/json"],
                default_output_modes=["application/json", "text/plain"],
                skills=[A2ASkill(id="x", name="X")],
            )
        )
        card = generate_agent_card(config)
        assert card["defaultInputModes"] == ["application/json"]
        assert card["defaultOutputModes"] == ["application/json", "text/plain"]

    def test_optional_fields(self):
        config = A2AConfig(
            card=A2AAgentCard(
                name="test",
                url="https://example.com",
                description="A test agent",
                version="2.1.0",
                provider=A2AProvider(organization="LightLayer", url="https://lightlayer.dev"),
                documentation_url="https://docs.example.com",
                capabilities=A2ACapabilities(streaming=True, push_notifications=False),
                authentication=A2AAuthScheme(type="apiKey", **{"in": "header"}, name="X-Agent-Key"),
                skills=[A2ASkill(id="x", name="X")],
            )
        )
        card = generate_agent_card(config)
        assert card["description"] == "A test agent"
        assert card["version"] == "2.1.0"
        assert card["provider"]["organization"] == "LightLayer"
        assert card["capabilities"]["streaming"] is True
        assert card["authentication"]["type"] == "apiKey"
        assert card["authentication"]["in"] == "header"

    def test_skill_tags_and_examples(self):
        config = A2AConfig(
            card=A2AAgentCard(
                name="test",
                url="https://example.com",
                skills=[
                    A2ASkill(
                        id="translate",
                        name="Translation",
                        tags=["nlp", "i18n"],
                        examples=["Translate hello to French"],
                        input_modes=["text/plain"],
                        output_modes=["text/plain"],
                    )
                ],
            )
        )
        card = generate_agent_card(config)
        assert card["skills"][0]["tags"] == ["nlp", "i18n"]
        assert card["skills"][0]["examples"] == ["Translate hello to French"]

    def test_camel_case_keys(self, minimal_config):
        card = generate_agent_card(minimal_config)
        assert "protocolVersion" in card
        assert "defaultInputModes" in card
        assert "defaultOutputModes" in card
        # No snake_case keys
        assert "protocol_version" not in card
        assert "default_input_modes" not in card


class TestValidateAgentCard:
    def test_valid_card(self):
        errors = validate_agent_card(
            {
                "name": "test",
                "url": "https://example.com",
                "protocolVersion": "1.0.0",
                "skills": [{"id": "x", "name": "X"}],
            }
        )
        assert errors == []

    def test_missing_name(self):
        errors = validate_agent_card(
            {"url": "https://x.com", "protocolVersion": "1.0.0", "skills": []}
        )
        assert "name is required" in errors

    def test_missing_url(self):
        errors = validate_agent_card({"name": "x", "protocolVersion": "1.0.0", "skills": []})
        assert "url is required" in errors

    def test_invalid_url(self):
        errors = validate_agent_card(
            {"name": "x", "url": "ftp://bad", "protocolVersion": "1.0.0", "skills": []}
        )
        assert "url must be an HTTP(S) URL" in errors

    def test_missing_skills(self):
        errors = validate_agent_card(
            {"name": "x", "url": "https://x.com", "protocolVersion": "1.0.0"}
        )
        assert "skills is required" in errors

    def test_skill_missing_id(self):
        errors = validate_agent_card(
            {
                "name": "x",
                "url": "https://x.com",
                "protocolVersion": "1.0.0",
                "skills": [{"id": "", "name": ""}],
            }
        )
        assert "each skill must have an id" in errors
        assert "each skill must have a name" in errors
