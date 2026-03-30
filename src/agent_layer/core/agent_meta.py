"""
Agent Meta — HTML transforms for agent accessibility.

Injects data-agent-id attributes, ARIA landmarks, and meta tags
into HTML responses to make pages more accessible to AI agents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class AgentMetaConfig:
    """Configuration for agent meta HTML transforms."""

    agent_id_attribute: str = "data-agent-id"
    aria_landmarks: bool = True
    meta_tags: dict[str, str] = field(default_factory=dict)


def transform_html(html: str, config: AgentMetaConfig) -> str:
    """Transform an HTML string with agent-friendly metadata.

    - Injects meta tags into <head>
    - Adds data-agent-id to <body>
    - Adds ARIA role="main" to <main> tags
    """
    attr_name = config.agent_id_attribute

    # Inject meta tags into <head>
    if config.meta_tags and "</head>" in html:
        meta_html = "\n    ".join(
            f'<meta name="{name}" content="{content}">'
            for name, content in config.meta_tags.items()
        )
        html = html.replace("</head>", f"    {meta_html}\n</head>")

    # Add data-agent-id to <body>
    if "<body" in html:
        html = html.replace("<body", f'<body {attr_name}="root"')

    # Add ARIA landmarks
    if config.aria_landmarks and "<main" in html:
        html = re.sub(r"<main(?![^>]*role=)", '<main role="main"', html)

    return html
