"""A real HTTP server that speaks chat-completions, for testing the real transport.

Every other test injects a fake transport, which means `http_transport` itself — urllib, the
headers, the JSON encoding, the error paths — has never run. That is exactly the gap that
left covenant-evals' EDGAR client unvalidated, and it is closeable without a model: what is
untested is the plumbing, not the intelligence.

So this is a real socket serving real HTTP on localhost. It cannot tell you anything about
how a model behaves. It can tell you the adapter would survive talking to one, including the
three server behaviours that are known to differ in the wild:

* `finish_reason: "stop"` returned alongside tool calls
* `content` returned as a list of parts rather than a string
* tool arguments that are not valid JSON

A model that produced those would look like a badly behaved agent if the adapter mishandled
them, which is the confusion this whole project exists to prevent.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class Behaviour:
    """What the server should do. Set before starting, read on each request."""

    def __init__(self, replies=None, status=200, quirk=""):
        self.replies = list(replies or [])
        self.status = status
        self.quirk = quirk
        self.requests: list[dict] = []


def _handler(behaviour: Behaviour):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: A002 - silence the default stderr logging
            pass

        def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's interface
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            behaviour.requests.append(
                {"path": self.path, "headers": dict(self.headers), "body": body}
            )

            if behaviour.status != 200:
                payload = json.dumps({"error": {"message": "upstream said no"}}).encode()
                self.send_response(behaviour.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            reply = behaviour.replies.pop(0) if behaviour.replies else _text("done")
            payload = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def _text(content: str, finish: str = "stop") -> dict:
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": finish}
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 8},
    }


def text_reply(content: str = "done") -> dict:
    return _text(content)


def parts_reply(content: str) -> dict:
    """Some servers return content as a list of parts rather than a plain string."""
    reply = _text("")
    reply["choices"][0]["message"]["content"] = [{"type": "text", "text": content}]
    return reply


def tool_reply(name: str, arguments, finish: str = "tool_calls", call_id: str = "c1") -> dict:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": raw},
                        },
                    ],
                },
                "finish_reason": finish,
            }
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 20},
    }


class LocalEndpoint:
    """A context manager that runs the server on a free port and hands back its base URL."""

    def __init__(self, *replies, status: int = 200):
        self.behaviour = Behaviour(replies=list(replies), status=status)
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> LocalEndpoint:
        self._server = HTTPServer(("127.0.0.1", 0), _handler(self.behaviour))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def base_url(self) -> str:
        assert self._server is not None
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    @property
    def requests(self) -> list[dict]:
        return self.behaviour.requests
