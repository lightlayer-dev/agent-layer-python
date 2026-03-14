"""Generate llms.txt and llms-full.txt content."""

from __future__ import annotations

from agent_layer.types import LlmsTxtConfig, RouteMetadata


def generate_llms_txt(config: LlmsTxtConfig) -> str:
    """Generate llms.txt content from manual config sections."""
    lines: list[str] = [f"# {config.title}"]

    if config.description:
        lines.append("")
        lines.append(f"> {config.description}")

    for section in config.sections:
        lines.append("")
        lines.append(f"## {section.title}")
        lines.append("")
        lines.append(section.content)

    return "\n".join(lines) + "\n"


def generate_llms_full_txt(config: LlmsTxtConfig, routes: list[RouteMetadata]) -> str:
    """Auto-generate llms-full.txt from route metadata."""
    lines: list[str] = [f"# {config.title}"]

    if config.description:
        lines.append("")
        lines.append(f"> {config.description}")

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
                    lines.append(f"- `{param.name}` ({param.location}){required}{desc}")

    return "\n".join(lines) + "\n"
