"""x402 Payment Protocol — Client-side helpers.

Utilities for API consumers that need to handle 402 Payment Required
responses and automatically retry with payment.

Cross-repo parity with @agent-layer/core x402-client.ts.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Protocol, runtime_checkable

import httpx

from agent_layer.x402 import (
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_SIGNATURE,
    PaymentPayload,
    PaymentRequired,
    PaymentRequirements,
)


# ── Types ────────────────────────────────────────────────────────────────


@runtime_checkable
class WalletSigner(Protocol):
    """Minimal wallet signer — signs a payment for the given requirements."""

    async def sign(self, requirements: PaymentRequirements) -> PaymentPayload: ...


# ── Helpers ──────────────────────────────────────────────────────────────


def is_payment_required(response: httpx.Response) -> bool:
    """Check whether a response is a 402 Payment Required."""
    return response.status_code == 402


def extract_payment_requirements(
    response: httpx.Response,
) -> PaymentRequired | None:
    """Decode the PAYMENT-REQUIRED header from a 402 response.

    Returns None if header is missing or invalid.
    """
    header = response.headers.get(HEADER_PAYMENT_REQUIRED)
    if not header:
        return None
    try:
        data = json.loads(base64.b64decode(header))
        return PaymentRequired.model_validate(data)
    except Exception:
        return None


async def wrap_request_with_payment(
    client: httpx.AsyncClient,
    wallet_signer: WalletSigner,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Make an HTTP request, automatically handling 402 by signing and retrying.

    When the request receives a 402 with a PAYMENT-REQUIRED header, signs
    a payment using the provided wallet signer and retries with a
    PAYMENT-SIGNATURE header.

    Args:
        client: httpx async client to use for requests.
        wallet_signer: Wallet signer that can sign payment requirements.
        method: HTTP method (GET, POST, etc.).
        url: Request URL.
        headers: Optional request headers.
        **kwargs: Additional arguments passed to client.request().

    Returns:
        The HTTP response (either original or retry with payment).
    """
    req_headers = dict(headers) if headers else {}
    response = await client.request(method, url, headers=req_headers, **kwargs)

    if not is_payment_required(response):
        return response

    requirements = extract_payment_requirements(response)
    if not requirements or len(requirements.accepts) == 0:
        return response

    # Sign payment for the first accepted payment scheme
    accepted = requirements.accepts[0]
    payload = await wallet_signer.sign(accepted)
    encoded = base64.b64encode(
        json.dumps(payload.model_dump(by_alias=True)).encode()
    ).decode()

    # Retry with payment header
    retry_headers = {**req_headers, HEADER_PAYMENT_SIGNATURE: encoded}
    return await client.request(method, url, headers=retry_headers, **kwargs)
