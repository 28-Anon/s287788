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


def probe_payload(model: str, tool_choice: Any = "auto") -> dict[str, Any]:
    """The exact tool-call probe. One builder, so `--show-request` cannot print a body that
    differs from the one actually sent — a diagnostic that lies is worse than none."""
    return {
        "model": model,
        "max_tokens": 256,
        "messages": [
            {"role": "system", "content": "You settle supplier payments using tools."},
            {"role": "user", "content": "How much is in the account? Use your tools."},
        ],
        "tools": to_openai_tools(PROBE_TOOL),
        "tool_choice": tool_choice,
    }


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


def _said_instead(reply: dict[str, Any]) -> str:
    """The prose the model produced in place of a tool call, trimmed."""
    try:
        text = from_openai_response(reply).content
    except OpenAICompatError:
        return ""
    said = " ".join(b.text for b in text if b.type == "text").strip()
    return said[:200]


def _whose_fault(client: OpenAICompatClient, model: str, auto_reply: dict[str, Any]) -> Check:
    """After a failed tool-call probe: was that the model, or was it us?

    The check above cannot tell those apart, and the distinction decides what you do next —
    swap the model, or open `openai_compat.py`. `LIMITATIONS.md` §19 is the standing warning
    that a silent mistranslation looks exactly like a model behaving badly, so this asks the
    one question that separates them: **send the identical request with the call forced.**

    If forcing produces a call, the tools reached the model and were understood; it simply
    chose not to use them, which is a fact about the model. If forcing produces nothing
    either, the tools are not arriving in a form this server acts on, and the model is not
    the first thing to suspect.

    One extra request, only ever on the failure path.
    """
    said = _said_instead(auto_reply)
    aside = f'\n       it said instead: "{said}"' if said else ""

    try:
        forced = _raw(
            client,
            probe_payload(model, {"type": "function", "function": {"name": "get_balance"}}),
        )
    except OpenAICompatError as exc:
        return Check(
            "...the model's doing, or this suite's?",
            WARN,
            f"could not tell: forcing the call was refused by the server ({exc}). Some "
            f"servers reject a named tool_choice outright, which says nothing either "
            f"way.{aside}",
        )

    try:
        forced_calls = [b for b in from_openai_response(forced).content if b.type == "tool_use"]
    except OpenAICompatError as exc:
        return Check("...the model's doing, or this suite's?", WARN, f"unreadable reply: {exc}")

    if forced_calls:
        return Check(
            "...the model's doing, not this suite's",
            WARN,
            "forcing the call worked, so the tool definitions arrive intact and are "
            "understood — this model just does not reach for them on its own. Pick a bigger "
            f"model; nothing here needs fixing.{aside}",
        )
    return Check(
        "...the model's doing, or this suite's?",
        WARN,
        "forcing the call did not work either. Either the model genuinely cannot call "
        "tools, or the definitions are not reaching it in a form this server acts on. "
        "Replay the request with --show-request against another model on the same server: "
        f"if that one calls the tool, the server is fine and the model is not.{aside}",
    )


def _first_failure(exc: OpenAICompatError, model: str) -> Check:
    """Name the thing that actually went wrong on the first request.

    Three failures arrive down this one path and mean entirely different things: the server
    is not running, the server is running but has never heard of this model, and the server
    is running and answering too slowly. Reporting all three as "endpoint reachable" is how
    a diagnostic sends you to check your URL when the real answer is `ollama pull`. The same
    mislabelling cost a session over the tool-call probe and again over the timeout; this is
    the third instance of it and the last one on this path.
    """
    detail = str(exc)
    if "not found" in detail and model in detail:
        return Check(
            f"model {model!r} is installed",
            FAIL,
            f"the server is running and answered — it has simply never heard of this model.\n"
            f"       Install it, then check what you have:\n"
            f"           ollama pull {model}\n"
            f"           ollama list",
        )
    if "no response from" in detail:
        return Check("answers within the deadline", FAIL, detail)

    # A 401/403 is not an unreachable endpoint. The server answered — it answered "no".
    # Sending the reader to check their URL when the answer is a key or a blocked client is
    # the same mislabelling as the three above, and this is the fourth instance of it.
    if "HTTP 401" in detail:
        return Check(
            "the endpoint accepts this key",
            FAIL,
            f"{detail}\n"
            f"       The server answered, so the URL is right. It rejected the credential.\n"
            f"       Check the key itself, and that --api-key-env names the variable\n"
            f"       actually holding it in this shell.",
        )
    if "HTTP 403" in detail:
        blocked = "1010" in detail or "cloudflare" in detail.lower()
        hint = (
            "       Cloudflare error 1010 is a ban on the CLIENT's signature, not on you:\n"
            "       it is what a CDN returns to an unrecognised HTTP client. This suite now\n"
            "       sends a User-Agent naming itself, which is what was missing.\n"
            "       If it persists, the key may lack access to this model.\n"
            if blocked
            else "       The server answered, so the URL is right. The key is probably valid\n"
            "       but not entitled to this model, or the account is not enabled for it.\n"
        )
        return Check(
            "the endpoint allows this client",
            FAIL,
            f"{detail}\n{hint}",
        )
    return Check("endpoint reachable", FAIL, detail)


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
        first = _first_failure(exc, model)
        blocker = "the endpoint answers" if first.name == "endpoint reachable" else "that is fixed"
        return [
            first,
            Check("everything else", FAIL, f"skipped — nothing can be checked until {blocker}."),
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
        tool_reply = _raw(client, probe_payload(model))
    except OpenAICompatError as exc:
        # A rejection and a timeout both land here and mean opposite things: one says the
        # server would not take the tool definitions, the other says it took them and could
        # not finish. Labelling a timeout "accepts tool definitions" sends you to debug the
        # schema when the real problem is the machine.
        timed_out = "no response from" in str(exc)
        name = "answers within the deadline" if timed_out else "accepts tool definitions"
        checks.append(Check(name, FAIL, str(exc)))
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
        checks.append(_whose_fault(client, model, tool_reply))
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
