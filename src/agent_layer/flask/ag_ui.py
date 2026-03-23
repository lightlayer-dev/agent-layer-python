"""AG-UI streaming middleware for Flask."""

from __future__ import annotations

from typing import Callable, Optional

from flask import Request, Response

from agent_layer.ag_ui import AG_UI_HEADERS, AgUiEmitter


AgUiStreamHandler = Callable[[Request, AgUiEmitter], None]


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

        chunks: list[str] = []

        # Try to extract threadId from request body
        thread_id = opts.thread_id
        if thread_id is None:
            try:
                body = flask_request.get_json(silent=True)
                if body:
                    thread_id = body.get("threadId")
            except Exception:
                pass

        emitter = AgUiEmitter(
            lambda chunk: chunks.append(chunk),
            thread_id=thread_id,
            run_id=opts.run_id,
        )

        try:
            handler(flask_request, emitter)
        except Exception as err:
            if opts.on_error:
                opts.on_error(err, emitter)
            else:
                emitter.run_error(str(err))

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
