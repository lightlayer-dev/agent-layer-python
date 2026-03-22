"""x402 Payment Middleware for FastAPI."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from agent_layer.x402 import (
    X402Config,
    HttpFacilitatorClient,
    process_x402_request,
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_SIGNATURE,
    HEADER_PAYMENT_RESPONSE,
)


def x402_middleware(config: X402Config):
    """Create a FastAPI middleware function for x402 payments."""
    facilitator = config.facilitator or HttpFacilitatorClient(config.facilitator_url)

    async def middleware(request: Request, call_next):
        result = await process_x402_request(
            method=request.method,
            path=request.url.path,
            url=str(request.url),
            payment_header=request.headers.get(HEADER_PAYMENT_SIGNATURE),
            config=config,
            facilitator=facilitator,
        )

        if result.action == "pass_through":
            return await call_next(request)

        if result.action == "payment_required":
            return JSONResponse(
                status_code=402,
                content=result.payment_required.to_camel(),
                headers={HEADER_PAYMENT_REQUIRED: result.encoded_header},
            )

        if result.action == "error":
            return JSONResponse(status_code=result.status_code, content=result.error_body)

        # success
        request.state.x402 = {
            "payment": result.payment_payload,
            "settlement": result.settle_result,
            "requirements": result.requirements,
        }
        response = await call_next(request)
        response.headers[HEADER_PAYMENT_RESPONSE] = result.settlement_b64
        return response

    return middleware
