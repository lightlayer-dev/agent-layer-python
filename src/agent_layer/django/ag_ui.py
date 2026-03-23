"""AG-UI streaming middleware for Django."""

from __future__ import annotations

from typing import Callable, Optional

from django.http import HttpRequest, StreamingHttpResponse

from agent_layer.ag_ui import AG_UI_HEADERS, AgUiEmitter


AgUiStreamHandler = Callable[[HttpRequest, AgUiEmitter], None]


class AgUiMiddlewareOptions:
    """Options for the AG-UI stream view."""

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
    Create a Django view function that streams AG-UI events over SSE.

    Usage::

        from agent_layer.django.ag_ui import ag_ui_stream

        def my_handler(request, emit):
            emit.run_started()
            emit.text_start()
            emit.text_delta("Hello from Django!")
            emit.text_end()
            emit.run_finished()

        urlpatterns = [
            path("api/agent", ag_ui_stream(my_handler)),
        ]
    """
    opts = options or AgUiMiddlewareOptions()

    def view(request: HttpRequest) -> StreamingHttpResponse:
        import json

        chunks: list[str] = []

        # Try to extract threadId from request body
        thread_id = opts.thread_id
        if thread_id is None:
            try:
                body = json.loads(request.body)
                thread_id = body.get("threadId")
            except Exception:
                pass

        emitter = AgUiEmitter(
            lambda chunk: chunks.append(chunk),
            thread_id=thread_id,
            run_id=opts.run_id,
        )

        try:
            handler(request, emitter)
        except Exception as err:
            if opts.on_error:
                opts.on_error(err, emitter)
            else:
                emitter.run_error(str(err))

        def generate():
            for chunk in chunks:
                yield chunk

        response = StreamingHttpResponse(
            generate(),
            content_type="text/event-stream",
        )
        for key, value in AG_UI_HEADERS.items():
            if key != "Content-Type":
                response[key] = value
        return response

    return view
