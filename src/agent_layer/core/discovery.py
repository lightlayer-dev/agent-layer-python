"""
Discovery — Generate /.well-known/ai manifest and JSON-LD structured data.

Enables machine-readable API discovery for AI agents via the
.well-known/ai convention and Schema.org JSON-LD.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIManifestAuth:
    """Authentication info for the AI manifest."""

    type: str  # "oauth2", "api_key", "bearer", "none"
    authorization_url: str | None = None
    token_url: str | None = None
    scopes: dict[str, str] = field(default_factory=dict)


@dataclass
class AIManifestContact:
    """Contact info for the AI manifest."""

    email: str | None = None
    url: str | None = None


@dataclass
class AIManifest:
    """The .well-known/ai manifest document."""

    name: str
    description: str | None = None
    openapi_url: str | None = None
    llms_txt_url: str | None = None
    auth: AIManifestAuth | None = None
    contact: AIManifestContact | None = None
    capabilities: list[str] = field(default_factory=list)


@dataclass
class DiscoveryConfig:
    """Configuration for the discovery endpoints."""

    manifest: AIManifest
    openapi_spec: dict[str, Any] | None = None


def generate_ai_manifest(config: DiscoveryConfig) -> dict[str, Any]:
    """Generate the /.well-known/ai manifest as a dictionary.

    Returns a JSON-serializable dictionary representing the AI manifest.
    """
    result: dict[str, Any] = {"name": config.manifest.name}

    if config.manifest.description:
        result["description"] = config.manifest.description
    if config.manifest.openapi_url:
        result["openapi_url"] = config.manifest.openapi_url
    if config.manifest.llms_txt_url:
        result["llms_txt_url"] = config.manifest.llms_txt_url
    if config.manifest.auth:
        auth: dict[str, Any] = {"type": config.manifest.auth.type}
        if config.manifest.auth.authorization_url:
            auth["authorization_url"] = config.manifest.auth.authorization_url
        if config.manifest.auth.token_url:
            auth["token_url"] = config.manifest.auth.token_url
        if config.manifest.auth.scopes:
            auth["scopes"] = config.manifest.auth.scopes
        result["auth"] = auth
    if config.manifest.contact:
        contact: dict[str, str] = {}
        if config.manifest.contact.email:
            contact["email"] = config.manifest.contact.email
        if config.manifest.contact.url:
            contact["url"] = config.manifest.contact.url
        if contact:
            result["contact"] = contact
    if config.manifest.capabilities:
        result["capabilities"] = config.manifest.capabilities

    return result


def generate_json_ld(config: DiscoveryConfig) -> dict[str, Any]:
    """Generate JSON-LD structured data for the API.

    Returns a Schema.org WebAPI JSON-LD object for SEO and
    machine-readable discovery.
    """
    json_ld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "WebAPI",
        "name": config.manifest.name,
    }

    if config.manifest.description:
        json_ld["description"] = config.manifest.description

    if config.manifest.openapi_url:
        json_ld["documentation"] = config.manifest.openapi_url

    if config.manifest.contact and config.manifest.contact.url:
        json_ld["url"] = config.manifest.contact.url

    if config.manifest.contact and config.manifest.contact.email:
        json_ld["contactPoint"] = {
            "@type": "ContactPoint",
            "email": config.manifest.contact.email,
        }

    if config.manifest.capabilities:
        json_ld["potentialAction"] = [
            {"@type": "Action", "name": cap} for cap in config.manifest.capabilities
        ]

    return json_ld
