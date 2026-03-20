"""x402 Payment Middleware for Django."""

from __future__ import annotations

import asyncio
import base64
import json

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from agent_layer.x402 import (
    X402Config,
    HttpFacilitatorClient,
    match_route,
    build_payment_required,
    encode_payment_required,
    decode_payment_payload,
    build_requirements,
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

    def __init__(self, get_response):
        self.get_response = get_response
        x402_settings = getattr(settings, "AGENT_LAYER_X402", {})
        self.config = X402Config(**x402_settings)
        self.facilitator = self.config.facilitator or HttpFacilitatorClient(
            self.config.facilitator_url
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        route_config = match_route(request.method, request.path, self.config.routes)
        if not route_config:
            return self.get_response(request)

        payment_header = request.META.get(
            f"HTTP_{HEADER_PAYMENT_SIGNATURE.upper().replace('-', '_')}"
        )
        url = request.build_absolute_uri()

        if not payment_header:
            pr = build_payment_required(url, route_config)
            response = JsonResponse(pr.to_camel(), status=402)
            response[HEADER_PAYMENT_REQUIRED] = encode_payment_required(pr)
            return response

        try:
            payload = decode_payment_payload(payment_header)
        except ValueError:
            pr = build_payment_required(url, route_config, "Invalid payment signature format")
            response = JsonResponse(pr.to_camel(), status=402)
            response[HEADER_PAYMENT_REQUIRED] = encode_payment_required(pr)
            return response

        requirements = build_requirements(route_config)

        try:
            verify_result = asyncio.run(self.facilitator.verify(payload, requirements))
        except Exception:
            return JsonResponse(
                {
                    "error": "payment_verification_failed",
                    "message": "Could not verify payment with facilitator",
                },
                status=502,
            )

        if not verify_result.is_valid:
            pr = build_payment_required(
                url, route_config,
                verify_result.invalid_reason or "Payment verification failed",
            )
            response = JsonResponse(pr.to_camel(), status=402)
            response[HEADER_PAYMENT_REQUIRED] = encode_payment_required(pr)
            return response

        try:
            settle_result = asyncio.run(self.facilitator.settle(payload, requirements))
        except Exception:
            return JsonResponse(
                {
                    "error": "payment_settlement_failed",
                    "message": "Could not settle payment with facilitator",
                },
                status=502,
            )

        if not settle_result.success:
            pr = build_payment_required(
                url, route_config,
                settle_result.error_reason or "Payment settlement failed",
            )
            response = JsonResponse(pr.to_camel(), status=402)
            response[HEADER_PAYMENT_REQUIRED] = encode_payment_required(pr)
            return response

        settlement_b64 = base64.b64encode(
            json.dumps(settle_result.model_dump(by_alias=True)).encode()
        ).decode()

        request.x402 = {  # type: ignore[attr-defined]
            "payment": payload,
            "settlement": settle_result,
            "requirements": requirements,
        }

        response = self.get_response(request)
        response[HEADER_PAYMENT_RESPONSE] = settlement_b64
        return response
