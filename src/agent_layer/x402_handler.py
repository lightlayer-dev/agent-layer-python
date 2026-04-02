"""Framework-agnostic x402 payment flow handler.

Extracts the duplicated verify/settle flow from all framework adapters.

Mirrors the TypeScript x402-handler.ts in agent-layer-ts.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any

from agent_layer.x402 import (
    X402Config,
    FacilitatorClient,
    HttpFacilitatorClient,
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    match_route,
    build_payment_required,
    encode_payment_required,
    decode_payment_payload,
    build_requirements,
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_RESPONSE,
)


@dataclass
class X402Skip:
    """Route doesn't require payment — continue normally."""

    action: str = "skip"


@dataclass
class X402PaymentRequired:
    """Payment is required or payment failed."""

    action: str = "payment_required"
    status: int = 402
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None


@dataclass
class X402Success:
    """Payment was verified and settled successfully."""

    action: str = "success"
    headers: dict[str, str] = field(default_factory=dict)
    payment: PaymentPayload | None = None
    settlement: SettleResponse | None = None
    requirements: PaymentRequirements | None = None


@dataclass
class X402Error:
    """Facilitator is unreachable or settlement fails."""

    action: str = "error"
    status: int = 502
    body: dict[str, str] = field(default_factory=dict)


X402FlowResult = X402Skip | X402PaymentRequired | X402Success | X402Error


async def handle_x402(
    method: str,
    path: str,
    url: str,
    payment_signature_header: str | None,
    config: X402Config,
) -> X402FlowResult:
    """Process a complete x402 payment flow.

    Args:
        method: HTTP method
        path: Request path
        url: Full request URL
        payment_signature_header: Value of the x-payment header
        config: x402 configuration
    """
    facilitator: FacilitatorClient = (
        config.facilitator if config.facilitator else HttpFacilitatorClient(config.facilitator_url)
    )

    # Check if this route requires payment
    route_config = match_route(method, path, config.routes)
    if not route_config:
        return X402Skip()

    # No payment header — return 402 with requirements
    if not payment_signature_header:
        payment_required = build_payment_required(url, route_config)
        encoded = encode_payment_required(payment_required)
        return X402PaymentRequired(
            status=402,
            headers={HEADER_PAYMENT_REQUIRED: encoded},
            body=payment_required,
        )

    # Decode payment payload
    try:
        payload = decode_payment_payload(payment_signature_header)
    except Exception:
        payment_required = build_payment_required(
            url, route_config, "Invalid payment signature format"
        )
        return X402PaymentRequired(
            status=402,
            headers={HEADER_PAYMENT_REQUIRED: encode_payment_required(payment_required)},
            body=payment_required,
        )

    requirements = build_requirements(route_config)

    # Verify with facilitator
    try:
        verify_result = await facilitator.verify(payload, requirements)
    except Exception:
        return X402Error(
            status=502,
            body={
                "error": "payment_verification_failed",
                "message": "Could not verify payment with facilitator",
            },
        )

    if not verify_result.is_valid:
        payment_required = build_payment_required(
            url,
            route_config,
            verify_result.invalid_reason or "Payment verification failed",
        )
        return X402PaymentRequired(
            status=402,
            headers={HEADER_PAYMENT_REQUIRED: encode_payment_required(payment_required)},
            body=payment_required,
        )

    # Settle payment
    try:
        settle_result = await facilitator.settle(payload, requirements)
    except Exception:
        return X402Error(
            status=502,
            body={
                "error": "payment_settlement_failed",
                "message": "Could not settle payment with facilitator",
            },
        )

    if not settle_result.success:
        payment_required = build_payment_required(
            url,
            route_config,
            settle_result.error_reason or "Payment settlement failed",
        )
        return X402PaymentRequired(
            status=402,
            headers={HEADER_PAYMENT_REQUIRED: encode_payment_required(payment_required)},
            body=payment_required,
        )

    # Payment successful
    settlement_json = json.dumps(settle_result.__dict__ if hasattr(settle_result, "__dict__") else settle_result)
    settlement_response = base64.b64encode(settlement_json.encode()).decode()

    return X402Success(
        headers={HEADER_PAYMENT_RESPONSE: settlement_response},
        payment=payload,
        settlement=settle_result,
        requirements=requirements,
    )
