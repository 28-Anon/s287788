"""Check an endpoint in fifteen seconds, before spending an hour on a sweep.

Ported in spirit from covenant-evals' `corpus doctor`, which existed for the same reason:
the code was written against documentation, and documentation is not a server. Everything
this suite believes about an OpenAI-compatible endpoint is an assumption until something
checks it, and finding out during scenario 14 of 29 is the expensive way.

Each check states the assumption, exercises it with one small request, and on failure says
what the server actually sent. A model that fails the tool-call check is not broken — plenty
of small models cannot call tools reliably, and that is a fact worth knowing before you read
their violation rate as a finding about control.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .openai_compat import (
    OpenAICompatClient,
    OpenAICompatError,
    from_openai_response,
    to_openai_tools,
)

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"

#: A tool simple enough that any model able to call tools at all should manage it.
PROBE_TOOL = [
    {
        "name": "get_balance",
        "description": "The current balance of the operating account, in pence.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {},
            "required": [],
        },
    }
]


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""

    def __str__(self) -> str:
        head = f"[{self.status:<4}] {self.name}"
        return f"{head}\n       {self.detail}" if self.detail else head


def _raw(client: OpenAICompatClient, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {client.api_key}"} if client.api_key else {}
    return client.transport(client.url, headers, payload)


def run_checks(client: OpenAICompatClient, model: str) -> list[Check]:
    """Every assumption this suite makes about a chat-completions endpoint."""
    checks: list[Check] = []

    # 1. Is anything there at all.
    try:
        reply = _raw(
            client,
            {
                "model": model,
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
            },
        )
    except OpenAICompatError as exc:
        return [
            Check("endpoint reachable", FAIL, str(exc)),
            Check(
                "everything else",
                FAIL,
                "skipped — nothing can be checked until the endpoint answers.",
            ),
        ]
    checks.append(Check(f"endpoint reachable at {client.url}", PASS))

    # 2. Does it come back in the shape the runner reads.
    try:
        response = from_openai_response(reply)
    except OpenAICompatError as exc:
        checks.append(
            Check(
                "response has the expected shape",
                FAIL,
                f"{exc}\n       server sent: {json.dumps(reply)[:300]}",
            )
        )
        return checks

    text = next((b.text for b in response.content if b.type == "text"), "")
    if text.strip():
        checks.append(Check("model answers in text", PASS, f'said: "{text.strip()[:60]}"'))
    else:
        checks.append(
            Check(
                "model answers in text",
                WARN,
                "the reply carried no text. Some models return reasoning only; the runner "
                "will record an empty final message, which fails every 'declined properly' "
                "check.",
            )
        )

    # 3. Token accounting — without it every cost and every turn figure is blank.
    if response.usage.input_tokens or response.usage.output_tokens:
        checks.append(
            Check(
                "reports token usage",
                PASS,
                f"in {response.usage.input_tokens}, out {response.usage.output_tokens}",
            )
        )
    else:
        checks.append(
            Check(
                "reports token usage",
                WARN,
                "no usage returned, so cost and token figures will read zero. Harmless for a "
                "local model, misleading for a hosted one.",
            )
        )

    # 4. The one that actually decides whether a sweep is worth running.
    try:
        tool_reply = _raw(
            client,
            {
                "model": model,
                "max_tokens": 256,
                "messages": [
                    {"role": "system", "content": "You settle supplier payments using tools."},
                    {"role": "user", "content": "How much is in the account? Use your tools."},
                ],
                "tools": to_openai_tools(PROBE_TOOL),
                "tool_choice": "auto",
            },
        )
    except OpenAICompatError as exc:
        checks.append(Check("accepts tool definitions", FAIL, str(exc)))
        return checks
    checks.append(Check("accepts tool definitions", PASS))

    tool_response = from_openai_response(tool_reply)
    calls = [b for b in tool_response.content if b.type == "tool_use"]
    if not calls:
        checks.append(
            Check(
                "model actually calls a tool",
                FAIL,
                "it was given get_balance and asked for the balance, and called nothing. "
                "This model cannot drive the suite: every scenario will end at turn one with "
                "no tool calls, and its violation rate will be zero for the wrong reason.",
            )
        )
        return checks

    call = calls[0]
    checks.append(Check("model actually calls a tool", PASS, f"called {call.name}"))

    if call.name != "get_balance":
        checks.append(Check("calls the tool by its right name", FAIL, f"asked for {call.name!r}"))
    else:
        checks.append(Check("calls the tool by its right name", PASS))

    if "__unparsable_arguments__" in call.input:
        checks.append(
            Check(
                "tool arguments parse as JSON",
                FAIL,
                f"sent: {call.input['__unparsable_arguments__']}. The runner records this as "
                "an attempted call, so a sweep will run — but every call will be rejected by "
                "the dispatcher.",
            )
        )
    else:
        checks.append(Check("tool arguments parse as JSON", PASS))

    # Read the RAW finish_reason, not the translated one. The adapter already corrects
    # "stop" to "tool_use" when blocks are present, so inspecting its output would only ever
    # confirm my own correction and could never detect the quirk in the server.
    raw_finish = (tool_reply.get("choices") or [{}])[0].get("finish_reason")
    if raw_finish in ("tool_calls", "function_call"):
        checks.append(Check("signals that the turn is not over", PASS))
    else:
        checks.append(
            Check(
                "signals that the turn is not over",
                WARN,
                f"server sent finish_reason {raw_finish!r} while emitting a tool call. "
                "Handled — the blocks are trusted over the reason — but worth knowing, and "
                "it means this server's finish_reason cannot be relied on elsewhere.",
            )
        )

    return checks


def verdict(checks: list[Check]) -> tuple[int, str]:
    """Exit code and a one-line summary. Warnings do not fail."""
    failed = [c for c in checks if c.status == FAIL]
    warned = [c for c in checks if c.status == WARN]
    if failed:
        return 1, f"{len(failed)} check(s) failed — a sweep would not tell you anything useful."
    if warned:
        return 0, f"usable, with {len(warned)} thing(s) to keep in mind."
    return 0, "everything this suite assumes about the endpoint holds. Go ahead and sweep."
