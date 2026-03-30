"""
x402 Payments — HTTP 402 Payment Required protocol.

Implements payment verification, headers, and middleware for the x402
protocol that enables micropayments for API access via blockchain.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any, Protocol


X402_VERSION = 1
HEADER_PAYMENT_REQUIRED = "payment-required"
HEADER_PAYMENT_SIGNATURE = "payment-signature"
HEADER_PAYMENT_RESPONSE = "payment-response"


@dataclass
class PaymentRequirements:
    """Server's payment demands."""

    scheme: str
    network: str
    asset: str
    amount: str
    pay_to: str
    max_timeout_seconds: int = 60
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class X402RouteConfig:
    """Per-route payment configuration."""

    pay_to: str
    price: str | dict[str, str]
    network: str = "eip155:8453"
    scheme: str = "exact"
    max_timeout_seconds: int = 60
    description: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class X402Config:
    """Top-level x402 configuration."""

    routes: dict[str, X402RouteConfig] = field(default_factory=dict)
    facilitator_url: str | None = None
    facilitator: Any = None  # FacilitatorClient


class FacilitatorClient(Protocol):
    """Interface for verify/settle operations."""

    async def verify(
        self, payload: dict[str, Any], requirements: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def settle(
        self, payload: dict[str, Any], requirements: dict[str, Any]
    ) -> dict[str, Any]: ...


def resolve_price(price: str | dict[str, str]) -> dict[str, str]:
    """Convert "$X.XX" to {amount, asset: "USDC"} or pass through object."""
    if isinstance(price, str):
        if not price.startswith("$"):
            raise ValueError(f"Invalid price format: {price}")
        return {"amount": price[1:], "asset": "USDC"}
    return price


def build_requirements(route_config: X402RouteConfig) -> PaymentRequirements:
    """Convert route config to PaymentRequirements."""
    price = resolve_price(route_config.price)
    return PaymentRequirements(
        scheme=route_config.scheme,
        network=route_config.network,
        asset=price.get("asset", "USDC"),
        amount=price.get("amount", "0"),
        pay_to=route_config.pay_to,
        max_timeout_seconds=route_config.max_timeout_seconds,
        extra=route_config.extra,
    )


def build_payment_required(
    resource: str,
    requirements: PaymentRequirements,
    error: str | None = None,
) -> dict[str, Any]:
    """Create a 402 response payload."""
    result: dict[str, Any] = {
        "x402Version": X402_VERSION,
        "resource": resource,
        "accepts": [
            {
                "scheme": requirements.scheme,
                "network": requirements.network,
                "asset": requirements.asset,
                "amount": requirements.amount,
                "payTo": requirements.pay_to,
                "maxTimeoutSeconds": requirements.max_timeout_seconds,
                **({"extra": requirements.extra} if requirements.extra else {}),
            }
        ],
    }
    if error:
        result["error"] = error
    return result


def encode_payment_required(payload: dict[str, Any]) -> str:
    """Base64 encode a PaymentRequired payload."""
    return base64.b64encode(json.dumps(payload).encode()).decode()


def decode_payment_payload(encoded: str) -> dict[str, Any]:
    """Decode a base64-encoded PaymentPayload."""
    return json.loads(base64.b64decode(encoded))


def match_route(
    method: str,
    path: str,
    routes: dict[str, X402RouteConfig],
) -> X402RouteConfig | None:
    """Match 'METHOD /path' to a route config."""
    key = f"{method.upper()} {path}"
    return routes.get(key)


async def handle_x402(
    method: str,
    path: str,
    url: str,
    payment_header: str | None,
    config: X402Config,
) -> dict[str, Any]:
    """Framework-agnostic x402 flow handler.

    Returns one of:
        {"action": "skip"}
        {"action": "payment_required", "status": 402, "headers": {...}, "body": {...}}
        {"action": "success", "headers": {...}, "payment": {...}, "settlement": {...}}
        {"action": "error", "status": 502, "error": str}
    """
    route_config = match_route(method, path, config.routes)
    if not route_config:
        return {"action": "skip"}

    requirements = build_requirements(route_config)

    if not payment_header:
        body = build_payment_required(url, requirements)
        return {
            "action": "payment_required",
            "status": 402,
            "headers": {HEADER_PAYMENT_REQUIRED: encode_payment_required(body)},
            "body": body,
        }

    try:
        payment = decode_payment_payload(payment_header)
    except Exception:
        body = build_payment_required(url, requirements, error="Invalid payment signature")
        return {
            "action": "payment_required",
            "status": 402,
            "headers": {HEADER_PAYMENT_REQUIRED: encode_payment_required(body)},
            "body": body,
        }

    facilitator = config.facilitator
    if not facilitator:
        return {"action": "error", "status": 502, "error": "Facilitator not configured"}

    req_dict = {
        "scheme": requirements.scheme,
        "network": requirements.network,
        "asset": requirements.asset,
        "amount": requirements.amount,
        "payTo": requirements.pay_to,
        "maxTimeoutSeconds": requirements.max_timeout_seconds,
    }

    try:
        verify_result = await facilitator.verify(payment, req_dict)
    except Exception:
        return {"action": "error", "status": 502, "error": "Facilitator unreachable"}

    if not verify_result.get("isValid"):
        body = build_payment_required(
            url, requirements, error=verify_result.get("invalidReason", "Payment invalid")
        )
        return {
            "action": "payment_required",
            "status": 402,
            "headers": {HEADER_PAYMENT_REQUIRED: encode_payment_required(body)},
            "body": body,
        }

    try:
        settle_result = await facilitator.settle(payment, req_dict)
    except Exception:
        return {"action": "error", "status": 502, "error": "Settlement failed"}

    if not settle_result.get("success"):
        return {
            "action": "error",
            "status": 502,
            "error": settle_result.get("errorReason", "Settlement failed"),
        }

    response_header = base64.b64encode(json.dumps(settle_result).encode()).decode()
    return {
        "action": "success",
        "headers": {HEADER_PAYMENT_RESPONSE: response_header},
        "payment": payment,
        "settlement": settle_result,
        "requirements": req_dict,
    }
