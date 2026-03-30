"""Tests for agent meta module."""

from agent_layer.core.agent_meta import AgentMetaConfig, transform_html


class TestTransformHtml:
    def test_injects_agent_id(self):
        html = "<html><body><p>Hello</p></body></html>"
        result = transform_html(html, AgentMetaConfig())
        assert 'data-agent-id="root"' in result

    def test_injects_meta_tags(self):
        html = "<html><head><title>Test</title></head><body></body></html>"
        config = AgentMetaConfig(meta_tags={"ai-purpose": "api-docs"})
        result = transform_html(html, config)
        assert 'name="ai-purpose"' in result
        assert 'content="api-docs"' in result

    def test_adds_aria_landmarks(self):
        html = "<html><body><main><p>Content</p></main></body></html>"
        result = transform_html(html, AgentMetaConfig())
        assert 'role="main"' in result

    def test_no_modify_non_html(self):
        data = '{"key": "value"}'
        result = transform_html(data, AgentMetaConfig())
        # No <body> or <main> tags, so nothing should change
        assert result == data

    def test_custom_attribute(self):
        html = "<html><body><p>Hi</p></body></html>"
        config = AgentMetaConfig(agent_id_attribute="data-bot-id")
        result = transform_html(html, config)
        assert 'data-bot-id="root"' in result
        assert "data-agent-id" not in result

    def test_aria_disabled(self):
        html = "<html><body><main><p>Content</p></main></body></html>"
        config = AgentMetaConfig(aria_landmarks=False)
        result = transform_html(html, config)
        assert 'role="main"' not in result

    def test_preserves_existing_role(self):
        html = '<html><body><main role="navigation"><p>Nav</p></main></body></html>'
        result = transform_html(html, AgentMetaConfig())
        # Should not add role="main" if role= already exists
        assert result.count("role=") == 1

    def test_multiple_meta_tags(self):
        html = "<html><head></head><body></body></html>"
        config = AgentMetaConfig(meta_tags={"agent-api": "https://api.example.com", "agent-version": "1.0"})
        result = transform_html(html, config)
        assert 'name="agent-api"' in result
        assert 'name="agent-version"' in result
