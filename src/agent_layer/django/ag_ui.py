"""AG-UI streaming middleware for Django."""

from __future__ import annotations

import json
from typing import Callable, Optional

from django.http import HttpRequest, StreamingHttpResponse

from agent_layer.ag_ui import (
    AG_UI_HEADERS,
    AgUiEmitter,
    AgUiMiddlewareOptionsBase,
    orchestrate_stream,
)


AgUiStreamHandler = Callable[[HttpRequest, AgUiEmitter], None]


class AgUiMiddlewareOptions(AgUiMiddlewareOptionsBase):
    """Options for the AG-UI stream view."""


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
        # Try to extract threadId from request body
        thread_id_from_body = None
        try:
            body = json.loads(request.body)
            thread_id_from_body = body.get("threadId")
        except Exception:
            pass

        chunks = orchestrate_stream(
            handler=handler,
            request_obj=request,
            thread_id_from_body=thread_id_from_body,
            opts=opts,
        )

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
