"""
llms.txt — Generate llms.txt and llms-full.txt for LLM-friendly documentation.

These files help LLMs understand your API by providing structured,
human-readable documentation optimized for language model consumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LlmsTxtSection:
    """A section in the llms.txt document."""

    title: str
    content: str


@dataclass
class RouteParameter:
    """A parameter for an API route."""

    name: str
    location: str  # "path", "query", "header", "body"
    required: bool = False
    description: str | None = None


@dataclass
class RouteMetadata:
    """Metadata for a single API route."""

    method: str
    path: str
    summary: str | None = None
    description: str | None = None
    parameters: list[RouteParameter] = field(default_factory=list)


@dataclass
class LlmsTxtConfig:
    """Configuration for generating llms.txt."""

    title: str
    description: str | None = None
    sections: list[LlmsTxtSection] = field(default_factory=list)


def generate_llms_txt(config: LlmsTxtConfig) -> str:
    """Generate llms.txt content from configuration.

    Produces a markdown-style document with title, description,
    and manually specified sections.
    """
    lines: list[str] = []

    lines.append(f"# {config.title}")

    if config.description:
        lines.append("")
        lines.append(f"> {config.description}")

    if config.sections:
        for section in config.sections:
            lines.append("")
            lines.append(f"## {section.title}")
            lines.append("")
            lines.append(section.content)

    return "\n".join(lines) + "\n"


def generate_llms_full_txt(
    config: LlmsTxtConfig,
    routes: list[RouteMetadata] | None = None,
) -> str:
    """Generate llms-full.txt with complete API documentation.

    Extends the base llms.txt with auto-generated route documentation,
    including parameters, descriptions, and method signatures.
    """
    lines: list[str] = []

    lines.append(f"# {config.title}")

    if config.description:
        lines.append("")
        lines.append(f"> {config.description}")

    if config.sections:
        for section in config.sections:
            lines.append("")
            lines.append(f"## {section.title}")
            lines.append("")
            lines.append(section.content)

    if routes:
        lines.append("")
        lines.append("## API Endpoints")

        for route in routes:
            lines.append("")
            lines.append(f"### {route.method.upper()} {route.path}")

            if route.summary:
                lines.append("")
                lines.append(route.summary)

            if route.description:
                lines.append("")
                lines.append(route.description)

            if route.parameters:
                lines.append("")
                lines.append("**Parameters:**")
                for param in route.parameters:
                    required = " (required)" if param.required else ""
                    desc = f" — {param.description}" if param.description else ""
                    lines.append(
                        f"- `{param.name}` ({param.location}){required}{desc}"
                    )

    return "\n".join(lines) + "\n"
