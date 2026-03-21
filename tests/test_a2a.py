"""Tests for A2A Agent Card generation and validation."""

from agent_layer.core.a2a import (
    A2AAgentCard,
    A2AAuthScheme,
    A2ACapabilities,
    A2AConfig,
    A2AProvider,
    A2ASkill,
    generate_agent_card,
    validate_agent_card,
)


class TestGenerateAgentCard:
    def test_minimal(self):
        config = A2AConfig(
            card=A2AAgentCard(name="TestAgent", url="https://agent.example.com")
        )
        result = generate_agent_card(config)
        assert result["name"] == "TestAgent"
        assert result["url"] == "https://agent.example.com"
        assert result["protocolVersion"] == "1.0.0"
        assert result["defaultInputModes"] == ["text/plain"]
        assert result["defaultOutputModes"] == ["text/plain"]
        assert result["skills"] == []

    def test_with_skills(self):
        config = A2AConfig(
            card=A2AAgentCard(
                name="TestAgent",
                url="https://agent.example.com",
                skills=[
                    A2ASkill(
                        id="search",
                        name="Web Search",
                        description="Search the web",
                        tags=["search", "web"],
                        examples=["search for cats"],
                    ),
                ],
            )
        )
        result = generate_agent_card(config)
        assert len(result["skills"]) == 1
        assert result["skills"][0]["id"] == "search"
        assert result["skills"][0]["name"] == "Web Search"
        assert result["skills"][0]["description"] == "Search the web"
        assert result["skills"][0]["tags"] == ["search", "web"]

    def test_with_provider(self):
        config = A2AConfig(
            card=A2AAgentCard(
                name="TestAgent",
                url="https://agent.example.com",
                provider=A2AProvider(
                    organization="Example Corp",
                    url="https://example.com",
                ),
            )
        )
        result = generate_agent_card(config)
        assert result["provider"]["organization"] == "Example Corp"
        assert result["provider"]["url"] == "https://example.com"

    def test_with_capabilities(self):
        config = A2AConfig(
            card=A2AAgentCard(
                name="TestAgent",
                url="https://agent.example.com",
                capabilities=A2ACapabilities(
                    streaming=True,
                    push_notifications=True,
                ),
            )
        )
        result = generate_agent_card(config)
        assert result["capabilities"]["streaming"] is True
        assert result["capabilities"]["pushNotifications"] is True
        assert result["capabilities"]["stateTransitionHistory"] is False

    def test_with_authentication(self):
        config = A2AConfig(
            card=A2AAgentCard(
                name="TestAgent",
                url="https://agent.example.com",
                authentication=A2AAuthScheme(
                    type="bearer",
                    location="header",
                    name="Authorization",
                ),
            )
        )
        result = generate_agent_card(config)
        assert result["authentication"]["type"] == "bearer"
        assert result["authentication"]["in"] == "header"
        assert result["authentication"]["name"] == "Authorization"

    def test_full_card(self):
        config = A2AConfig(
            card=A2AAgentCard(
                name="FullAgent",
                url="https://agent.example.com",
                description="A fully featured agent",
                version="2.0.0",
                documentation_url="https://docs.example.com",
                default_input_modes=["text/plain", "application/json"],
                default_output_modes=["text/plain"],
                skills=[
                    A2ASkill(id="s1", name="Skill 1"),
                    A2ASkill(id="s2", name="Skill 2"),
                ],
            )
        )
        result = generate_agent_card(config)
        assert result["description"] == "A fully featured agent"
        assert result["version"] == "2.0.0"
        assert result["documentationUrl"] == "https://docs.example.com"
        assert len(result["skills"]) == 2


class TestValidateAgentCard:
    def test_valid_card(self):
        card = {
            "protocolVersion": "1.0.0",
            "name": "TestAgent",
            "url": "https://agent.example.com",
            "skills": [{"id": "s1", "name": "Skill 1"}],
        }
        errors = validate_agent_card(card)
        assert errors == []

    def test_missing_name(self):
        card = {"url": "https://example.com", "skills": [], "protocolVersion": "1.0.0"}
        errors = validate_agent_card(card)
        assert "name is required" in errors

    def test_missing_url(self):
        card = {"name": "Test", "skills": [], "protocolVersion": "1.0.0"}
        errors = validate_agent_card(card)
        assert "url is required" in errors

    def test_missing_skills(self):
        card = {"name": "Test", "url": "https://example.com", "protocolVersion": "1.0.0"}
        errors = validate_agent_card(card)
        assert "skills is required" in errors

    def test_missing_protocol_version(self):
        card = {"name": "Test", "url": "https://example.com", "skills": []}
        errors = validate_agent_card(card)
        assert "protocolVersion is required" in errors

    def test_invalid_url(self):
        card = {
            "protocolVersion": "1.0.0",
            "name": "Test",
            "url": "ftp://bad",
            "skills": [],
        }
        errors = validate_agent_card(card)
        assert "url must be an HTTP(S) URL" in errors

    def test_skills_not_array(self):
        card = {
            "protocolVersion": "1.0.0",
            "name": "Test",
            "url": "https://example.com",
            "skills": "not an array",
        }
        errors = validate_agent_card(card)
        assert "skills must be an array" in errors

    def test_skill_missing_id(self):
        card = {
            "protocolVersion": "1.0.0",
            "name": "Test",
            "url": "https://example.com",
            "skills": [{"name": "Skill 1"}],
        }
        errors = validate_agent_card(card)
        assert "each skill must have an id" in errors

    def test_skill_missing_name(self):
        card = {
            "protocolVersion": "1.0.0",
            "name": "Test",
            "url": "https://example.com",
            "skills": [{"id": "s1"}],
        }
        errors = validate_agent_card(card)
        assert "each skill must have a name" in errors

    def test_multiple_errors(self):
        card = {}
        errors = validate_agent_card(card)
        assert len(errors) >= 3
