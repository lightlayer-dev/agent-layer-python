"""x402 Payment Protocol — Core types and helpers for HTTP-native micropayments.

Implements the server side of the x402 protocol (https://x402.org):
1. Server declares pricing via PaymentRequirements
2. Unpaid requests receive 402 + PAYMENT-REQUIRED header
3. Client pays and retries with PAYMENT-SIGNATURE header
4. Server verifies payment via facilitator and serves the resource

See: https://github.com/coinbase/x402
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field


# ── Constants ────────────────────────────────────────────────────────────

X402_VERSION = 1
HEADER_PAYMENT_REQUIRED = "payment-required"
HEADER_PAYMENT_SIGNATURE = "payment-signature"
HEADER_PAYMENT_RESPONSE = "payment-response"


# ── Types ────────────────────────────────────────────────────────────────


class PaymentRequirements(BaseModel):
    scheme: str
    network: str
    asset: str
    amount: str
    pay_to: str = Field(alias="payTo")
    max_timeout_seconds: int = Field(alias="maxTimeoutSeconds")
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    def to_camel(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "network": self.network,
            "asset": self.asset,
            "amount": self.amount,
            "payTo": self.pay_to,
            "maxTimeoutSeconds": self.max_timeout_seconds,
            "extra": self.extra,
        }


class ResourceInfo(BaseModel):
    url: str
    description: str | None = None
    mime_type: str | None = Field(default=None, alias="mimeType")

    model_config = {"populate_by_name": True}

    def to_camel(self) -> dict[str, Any]:
        d: dict[str, Any] = {"url": self.url}
        if self.description is not None:
            d["description"] = self.description
        if self.mime_type is not None:
            d["mimeType"] = self.mime_type
        return d


class PaymentRequired(BaseModel):
    x402_version: int = Field(alias="x402Version", default=X402_VERSION)
    error: str | None = None
    resource: ResourceInfo
    accepts: list[PaymentRequirements]

    model_config = {"populate_by_name": True}

    def to_camel(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "x402Version": self.x402_version,
            "resource": self.resource.to_camel(),
            "accepts": [a.to_camel() for a in self.accepts],
        }
        if self.error is not None:
            d["error"] = self.error
        return d


class PaymentPayload(BaseModel):
    x402_version: int = Field(alias="x402Version", default=X402_VERSION)
    resource: ResourceInfo | None = None
    accepted: PaymentRequirements
    payload: dict[str, Any]

    model_config = {"populate_by_name": True}


class VerifyResponse(BaseModel):
    is_valid: bool = Field(alias="isValid")
    invalid_reason: str | None = Field(default=None, alias="invalidReason")

    model_config = {"populate_by_name": True}


class SettleResponse(BaseModel):
    success: bool
    tx_hash: str | None = Field(default=None, alias="txHash")
    network: str | None = None
    error_reason: str | None = Field(default=None, alias="errorReason")

    model_config = {"populate_by_name": True}


# ── Route config ─────────────────────────────────────────────────────────


class X402RouteConfig(BaseModel):
    pay_to: str
    scheme: str = "exact"
    price: str | dict[str, Any]  # "$0.01" or {"amount": "0.01", "asset": "USDC"}
    network: str  # e.g. "eip155:8453"
    max_timeout_seconds: int = 60
    description: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class X402Config(BaseModel):
    routes: dict[str, X402RouteConfig]  # "METHOD /path" → config
    facilitator_url: str
    facilitator: Any = None  # FacilitatorClient instance

    model_config = {"arbitrary_types_allowed": True}


# ── Facilitator client ───────────────────────────────────────────────────


class FacilitatorClient(Protocol):
    async def verify(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> VerifyResponse: ...

    async def settle(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> SettleResponse: ...


class HttpFacilitatorClient:
    """Default HTTP-based facilitator client."""

    def __init__(self, url: str) -> None:
        self.url = url

    async def verify(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> VerifyResponse:
        import httpx

        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.url}/verify",
                json={
                    "payload": payload.model_dump(by_alias=True),
                    "requirements": requirements.to_camel(),
                },
            )
            res.raise_for_status()
            return VerifyResponse.model_validate(res.json())

    async def settle(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> SettleResponse:
        import httpx

        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.url}/settle",
                json={
                    "payload": payload.model_dump(by_alias=True),
                    "requirements": requirements.to_camel(),
                },
            )
            res.raise_for_status()
            return SettleResponse.model_validate(res.json())


# ── Helpers ──────────────────────────────────────────────────────────────


def resolve_price(price: str | dict[str, Any]) -> dict[str, Any]:
    """Resolve a Price into concrete amount + asset."""
    if isinstance(price, str):
        match = re.match(r"^\$(\d+(?:\.\d+)?)$", price)
        if not match:
            raise ValueError(f'Invalid price string: {price}. Use "$X.XX" format.')
        return {"amount": match.group(1), "asset": "USDC"}
    return price


def build_requirements(config: X402RouteConfig) -> PaymentRequirements:
    """Build PaymentRequirements from a route config."""
    resolved = resolve_price(config.price)
    extra = {**config.extra, **resolved.get("extra", {})}
    return PaymentRequirements(
        scheme=config.scheme,
        network=config.network,
        asset=resolved["asset"],
        amount=resolved["amount"],
        payTo=config.pay_to,
        maxTimeoutSeconds=config.max_timeout_seconds,
        extra=extra,
    )


def build_payment_required(
    url: str, config: X402RouteConfig, error: str | None = None
) -> PaymentRequired:
    """Build the 402 response payload."""
    return PaymentRequired(
        x402Version=X402_VERSION,
        error=error,
        resource=ResourceInfo(url=url),
        accepts=[build_requirements(config)],
    )


def encode_payment_required(pr: PaymentRequired) -> str:
    """Encode a PaymentRequired object to a base64 header value."""
    return base64.b64encode(json.dumps(pr.to_camel()).encode()).decode()


def decode_payment_payload(header: str) -> PaymentPayload:
    """Decode a base64 PAYMENT-SIGNATURE header to a PaymentPayload."""
    try:
        data = json.loads(base64.b64decode(header))
        return PaymentPayload.model_validate(data)
    except Exception:
        raise ValueError("Invalid PAYMENT-SIGNATURE header: not valid base64 JSON")


def match_route(
    method: str, path: str, routes: dict[str, X402RouteConfig]
) -> X402RouteConfig | None:
    """Match an incoming request to a route config key."""
    key = f"{method.upper()} {path}"
    return routes.get(key)


def encode_settlement(settle_result: SettleResponse) -> str:
    """Encode a SettleResponse to a base64 string for the response header."""
    return base64.b64encode(json.dumps(settle_result.model_dump(by_alias=True)).encode()).decode()


# ── Core Payment Flow ─────────────────────────────────────────────────


@dataclass
class X402RequestResult:
    """Result of processing an x402 payment request."""

    action: str  # "pass_through", "payment_required", "error", "success"
    status_code: int = 200
    payment_required: PaymentRequired | None = None
    encoded_header: str | None = None
    error_body: dict[str, Any] | None = None
    settlement_b64: str | None = None
    payment_payload: PaymentPayload | None = None
    settle_result: SettleResponse | None = None
    requirements: PaymentRequirements | None = None


async def process_x402_request(
    method: str,
    path: str,
    url: str,
    payment_header: str | None,
    config: X402Config,
    facilitator: FacilitatorClient | None = None,
) -> X402RequestResult:
    """Core x402 payment flow — framework-agnostic.

    Returns a result object that adapters use to build framework-specific responses.
    """
    route_config = match_route(method, path, config.routes)
    if not route_config:
        return X402RequestResult(action="pass_through")

    fac = facilitator or config.facilitator or HttpFacilitatorClient(config.facilitator_url)

    if not payment_header:
        pr = build_payment_required(url, route_config)
        return X402RequestResult(
            action="payment_required",
            status_code=402,
            payment_required=pr,
            encoded_header=encode_payment_required(pr),
        )

    try:
        payload = decode_payment_payload(payment_header)
    except ValueError:
        pr = build_payment_required(url, route_config, "Invalid payment signature format")
        return X402RequestResult(
            action="payment_required",
            status_code=402,
            payment_required=pr,
            encoded_header=encode_payment_required(pr),
        )

    requirements = build_requirements(route_config)

    # Verify
    try:
        verify_result = await fac.verify(payload, requirements)
    except Exception:
        return X402RequestResult(
            action="error",
            status_code=502,
            error_body={
                "error": "payment_verification_failed",
                "message": "Could not verify payment with facilitator",
            },
        )

    if not verify_result.is_valid:
        pr = build_payment_required(
            url,
            route_config,
            verify_result.invalid_reason or "Payment verification failed",
        )
        return X402RequestResult(
            action="payment_required",
            status_code=402,
            payment_required=pr,
            encoded_header=encode_payment_required(pr),
        )

    # Settle
    try:
        settle_result = await fac.settle(payload, requirements)
    except Exception:
        return X402RequestResult(
            action="error",
            status_code=502,
            error_body={
                "error": "payment_settlement_failed",
                "message": "Could not settle payment with facilitator",
            },
        )

    if not settle_result.success:
        pr = build_payment_required(
            url,
            route_config,
            settle_result.error_reason or "Payment settlement failed",
        )
        return X402RequestResult(
            action="payment_required",
            status_code=402,
            payment_required=pr,
            encoded_header=encode_payment_required(pr),
        )

    return X402RequestResult(
        action="success",
        settlement_b64=encode_settlement(settle_result),
        payment_payload=payload,
        settle_result=settle_result,
        requirements=requirements,
    )
