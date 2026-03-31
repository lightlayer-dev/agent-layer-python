"""x402 Payment Middleware for Django."""

from __future__ import annotations

from typing import Any, Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from agent_layer.async_utils import run_async_in_sync
from agent_layer.x402 import (
    X402Config,
    HttpFacilitatorClient,
    process_x402_request,
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_SIGNATURE,
    HEADER_PAYMENT_RESPONSE,
)


class X402PaymentMiddleware:
    """Django middleware for x402 HTTP-native micropayments.

    Configure via Django settings::

        AGENT_LAYER_X402 = {
            "facilitator_url": "https://x402.org/facilitator",
            "routes": {
                "GET /api/weather": {
                    "pay_to": "0x1234...",
                    "price": "$0.001",
                    "network": "eip155:8453",
                },
            },
        }
    """

    def __init__(self, get_response: Callable[..., Any]) -> None:
        self.get_response = get_response
        x402_settings = getattr(settings, "AGENT_LAYER_X402", {})
        self.config = X402Config(**x402_settings)
        self.facilitator = self.config.facilitator or HttpFacilitatorClient(
            self.config.facilitator_url
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        payment_header = request.META.get(
            f"HTTP_{HEADER_PAYMENT_SIGNATURE.upper().replace('-', '_')}"
        )

        result = run_async_in_sync(
            process_x402_request(
                method=request.method,
                path=request.path,
                url=request.build_absolute_uri(),
                payment_header=payment_header,
                config=self.config,
                facilitator=self.facilitator,
            )
        )

        if result.action == "pass_through":
            return self.get_response(request)

        if result.action == "payment_required":
            response = JsonResponse(result.payment_required.to_camel(), status=402)
            response[HEADER_PAYMENT_REQUIRED] = result.encoded_header
            return response

        if result.action == "error":
            return JsonResponse(result.error_body, status=result.status_code)

        # success
        request.x402 = {  # type: ignore[attr-defined]
            "payment": result.payment_payload,
            "settlement": result.settle_result,
            "requirements": result.requirements,
        }
        response = self.get_response(request)
        response[HEADER_PAYMENT_RESPONSE] = result.settlement_b64
        return response
