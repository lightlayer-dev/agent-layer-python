"""AG-UI streaming middleware for Flask."""

from __future__ import annotations

from typing import Callable, Optional

from flask import Request, Response

from agent_layer.ag_ui import (
    AG_UI_HEADERS,
    AgUiEmitter,
    AgUiMiddlewareOptionsBase,
    orchestrate_stream,
)


AgUiStreamHandler = Callable[[Request, AgUiEmitter], None]


class AgUiMiddlewareOptions(AgUiMiddlewareOptionsBase):
    """Options for the AG-UI stream middleware."""


def ag_ui_stream(
    handler: AgUiStreamHandler,
    options: Optional[AgUiMiddlewareOptions] = None,
):
    """
    Create a Flask view function that streams AG-UI events over SSE.

    Usage::

        from agent_layer.flask.ag_ui import ag_ui_stream

        def my_handler(request, emit):
            emit.run_started()
            emit.text_start()
            emit.text_delta("Hello from Flask!")
            emit.text_end()
            emit.run_finished()

        app.add_url_rule(
            "/api/agent",
            view_func=ag_ui_stream(my_handler),
            methods=["POST"],
        )
    """
    opts = options or AgUiMiddlewareOptions()

    def view_func():
        from flask import request as flask_request

        # Try to extract threadId from request body
        thread_id_from_body = None
        try:
            body = flask_request.get_json(silent=True)
            if body:
                thread_id_from_body = body.get("threadId")
        except Exception:
            pass

        chunks = orchestrate_stream(
            handler=handler,
            request_obj=flask_request,
            thread_id_from_body=thread_id_from_body,
            opts=opts,
        )

        def generate():
            for chunk in chunks:
                yield chunk

        headers = {k: v for k, v in AG_UI_HEADERS.items() if k != "Content-Type"}
        return Response(
            generate(),
            mimetype="text/event-stream",
            headers=headers,
        )

    return view_func
