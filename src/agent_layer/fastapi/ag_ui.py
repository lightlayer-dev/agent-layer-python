"""AG-UI streaming middleware for FastAPI."""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from fastapi import Request
from starlette.responses import StreamingResponse

from agent_layer.ag_ui import AG_UI_HEADERS, AgUiEmitter

AgUiStreamHandler = Callable[[Request, AgUiEmitter], Awaitable[None]]


class AgUiMiddlewareOptions:
    """Options for the AG-UI stream middleware."""

    def __init__(
        self,
        *,
        thread_id: Optional[str] = None,
        run_id: Optional[str] = None,
        on_error: Optional[Callable[[Exception, AgUiEmitter], None]] = None,
    ):
        self.thread_id = thread_id
        self.run_id = run_id
        self.on_error = on_error


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
        chunks: list[str] = []

        # Try to extract threadId from request body
        thread_id = opts.thread_id
        if thread_id is None:
            try:
                body = await request.json()
                thread_id = body.get("threadId")
            except Exception:
                pass

        emitter = AgUiEmitter(
            lambda chunk: chunks.append(chunk),
            thread_id=thread_id,
            run_id=opts.run_id,
        )

        try:
            await handler(request, emitter)
        except Exception as err:
            if opts.on_error:
                opts.on_error(err, emitter)
            else:
                emitter.run_error(str(err))

        async def generate():
            for chunk in chunks:
                yield chunk

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={k: v for k, v in AG_UI_HEADERS.items() if k != "Content-Type"},
        )

    return endpoint
