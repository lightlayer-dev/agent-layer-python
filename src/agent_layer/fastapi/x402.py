"""x402 Payment Middleware for FastAPI."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

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


def x402_middleware(config: X402Config):
    """Create a FastAPI middleware function for x402 payments."""
    facilitator = config.facilitator or HttpFacilitatorClient(config.facilitator_url)

    async def middleware(request: Request, call_next):
        route_config = match_route(request.method, request.url.path, config.routes)
        if not route_config:
            return await call_next(request)

        payment_header = request.headers.get(HEADER_PAYMENT_SIGNATURE)
        url = str(request.url)

        if not payment_header:
            pr = build_payment_required(url, route_config)
            encoded = encode_payment_required(pr)
            return JSONResponse(
                status_code=402,
                content=pr.to_camel(),
                headers={HEADER_PAYMENT_REQUIRED: encoded},
            )

        # Decode payment
        try:
            payload = decode_payment_payload(payment_header)
        except ValueError:
            pr = build_payment_required(url, route_config, "Invalid payment signature format")
            return JSONResponse(
                status_code=402,
                content=pr.to_camel(),
                headers={HEADER_PAYMENT_REQUIRED: encode_payment_required(pr)},
            )

        requirements = build_requirements(route_config)

        # Verify
        try:
            verify_result = await facilitator.verify(payload, requirements)
        except Exception:
            return JSONResponse(
                status_code=502,
                content={
                    "error": "payment_verification_failed",
                    "message": "Could not verify payment with facilitator",
                },
            )

        if not verify_result.is_valid:
            pr = build_payment_required(
                url, route_config,
                verify_result.invalid_reason or "Payment verification failed",
            )
            return JSONResponse(
                status_code=402,
                content=pr.to_camel(),
                headers={HEADER_PAYMENT_REQUIRED: encode_payment_required(pr)},
            )

        # Settle
        try:
            settle_result = await facilitator.settle(payload, requirements)
        except Exception:
            return JSONResponse(
                status_code=502,
                content={
                    "error": "payment_settlement_failed",
                    "message": "Could not settle payment with facilitator",
                },
            )

        if not settle_result.success:
            pr = build_payment_required(
                url, route_config,
                settle_result.error_reason or "Payment settlement failed",
            )
            return JSONResponse(
                status_code=402,
                content=pr.to_camel(),
                headers={HEADER_PAYMENT_REQUIRED: encode_payment_required(pr)},
            )

        # Success — attach settlement info
        import base64
        import json

        settlement_b64 = base64.b64encode(
            json.dumps(settle_result.model_dump(by_alias=True)).encode()
        ).decode()

        request.state.x402 = {
            "payment": payload,
            "settlement": settle_result,
            "requirements": requirements,
        }

        response = await call_next(request)
        response.headers[HEADER_PAYMENT_RESPONSE] = settlement_b64
        return response

    return middleware
