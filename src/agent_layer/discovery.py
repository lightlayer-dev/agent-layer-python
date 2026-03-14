"""Discovery endpoints: .well-known/ai manifest and JSON-LD."""

from __future__ import annotations

from typing import Any

from agent_layer.types import AIManifest, DiscoveryConfig


def generate_ai_manifest(config: DiscoveryConfig) -> dict[str, Any]:
    """Generate the /.well-known/ai manifest JSON."""
    return config.manifest.model_dump(exclude_none=True)


def generate_json_ld(config: DiscoveryConfig) -> dict[str, Any]:
    """Generate JSON-LD structured data for the API."""
    m = config.manifest
    json_ld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "WebAPI",
        "name": m.name,
    }

    if m.description:
        json_ld["description"] = m.description

    if m.openapi_url:
        json_ld["documentation"] = m.openapi_url

    if m.contact and m.contact.url:
        json_ld["url"] = m.contact.url

    if m.contact and m.contact.email:
        json_ld["contactPoint"] = {
            "@type": "ContactPoint",
            "email": m.contact.email,
        }

    if m.capabilities:
        json_ld["potentialAction"] = [
            {"@type": "Action", "name": cap} for cap in m.capabilities
        ]

    return json_ld
