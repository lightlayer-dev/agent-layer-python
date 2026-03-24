"""AG-UI streaming middleware for FastAPI."""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from fastapi import Request
from starlette.responses import StreamingResponse

from agent_layer.ag_ui import (
    AG_UI_HEADERS,
    AgUiEmitter,
    AgUiMiddlewareOptionsBase,
    orchestrate_stream_async,
)

AgUiStreamHandler = Callable[[Request, AgUiEmitter], Awaitable[None]]


class AgUiMiddlewareOptions(AgUiMiddlewareOptionsBase):
    """Options for the AG-UI stream middleware."""


def ag_ui_stream(
    handler: AgUiStreamHandler,
    options: Optional[AgUiMiddlewareOptions] = None,
):
    """
    Create a FastAPI route handler that streams AG-UI events over SSE.

    Usage::

        from agent_layer.fastapi.ag_ui import ag_ui_stream

        @app.post("/api/agent")
        async def agent_endpoint(request: Request):
            return await ag_ui_stream(my_handler)(request)

        async def my_handler(request: Request, emit: AgUiEmitter):
            emit.run_started()
            emit.text_start()
            emit.text_delta("Hello from FastAPI!")
            emit.text_end()
            emit.run_finished()
    """
    opts = options or AgUiMiddlewareOptions()

    async def endpoint(request: Request) -> StreamingResponse:
        # Try to extract threadId from request body
        thread_id_from_body = None
        try:
            body = await request.json()
            thread_id_from_body = body.get("threadId")
        except Exception:
            pass

        chunks = await orchestrate_stream_async(
            handler=handler,
            request_obj=request,
            thread_id_from_body=thread_id_from_body,
            opts=opts,
        )

        async def generate():
            for chunk in chunks:
                yield chunk

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={k: v for k, v in AG_UI_HEADERS.items() if k != "Content-Type"},
        )

    return endpoint
