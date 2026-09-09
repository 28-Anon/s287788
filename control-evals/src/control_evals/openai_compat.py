"""Run the suite against anything that speaks the OpenAI chat-completions API.

That is most things: Ollama and vLLM on your own machine, and OpenRouter, Together, Groq and
Fireworks in the cloud. **The local ones cost nothing**, which is the point — a small model
running on a laptop is a real model making real decisions, and it needs no card.

Two deliberate choices.

**No new dependency.** This talks to the endpoint over `urllib` from the standard library
rather than pulling in the `openai` package. A project someone might clone should not need a
second SDK to try a local model, and the transport is a plain injected callable, so every
test here stays offline.

**The translation is the interesting part**, and it is not symmetric. The two APIs disagree
about where the system prompt lives, how a tool call comes back, how tool results are sent,
and what to call the reason a turn ended. Each mapping below is written out rather than
guessed at, because a silent mistranslation would look exactly like a model behaving badly —
and this suite exists to tell those apart.
"""

from __future__ import annotations

import functools
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .shapes import Block, Response, Usage

#: OpenAI's `finish_reason` to the runner's `stop_reason`. "content_filter" maps to refusal
#: so a filtered turn is recorded as one rather than being scored as a completed run.
FINISH_REASONS = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}

Transport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class OpenAICompatError(RuntimeError):
    """A transport or protocol failure, raised so the runner records it as an error."""


#: Long enough for a large local model to load from disk and answer once. Short enough that a
#: sweep against a machine that cannot run the model fails in minutes rather than hours.
DEFAULT_TIMEOUT_S = 180.0


def _too_slow(url: str, timeout: float) -> OpenAICompatError:
    """The message for a server that accepted the request and never finished answering.

    Worth distinguishing from "could not reach": the connection succeeded, so nothing is
    misconfigured — the model is simply generating slower than the deadline. On a laptop that
    almost always means the weights do not fit in RAM and the machine is swapping.
    """
    return OpenAICompatError(
        f"no response from {url} within {timeout:g}s. The server accepted the request, so it "
        f"is running — the model is just answering too slowly to finish in time. On a local "
        f"endpoint this usually means the model is too large for the RAM available and the "
        f"machine is swapping. Try a smaller model, or raise the deadline with --timeout."
    )


def http_transport(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """POST JSON, get JSON. The whole network surface of this module."""
    request = urllib.request.Request(  # noqa: S310 - url is operator-supplied, not user input
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as handle:  # noqa: S310
            return json.loads(handle.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise OpenAICompatError(f"HTTP {exc.code} from {url}: {detail}") from None
    except urllib.error.URLError as exc:
        # A timeout while *connecting* arrives wrapped in URLError; one while *reading* the
        # response arrives bare, below. Both are the same condition to whoever is waiting.
        if isinstance(exc.reason, TimeoutError):
            raise _too_slow(url, timeout) from None
        raise OpenAICompatError(
            f"could not reach {url}: {exc.reason}. If this is Ollama, is `ollama serve` running?"
        ) from None
    except TimeoutError:
        # The read timed out. Before this was caught, the traceback escaped all the way to the
        # command line — forty lines of urllib internals in place of the one sentence that
        # says what to do. A diagnostic tool that stack-traces has failed at its only job.
        raise _too_slow(url, timeout) from None


def transport_with_timeout(seconds: float) -> Transport:
    """`http_transport` with its own deadline, for `--timeout`."""
    return functools.partial(http_transport, timeout=seconds)


# ---------------------------------------------------------------------------
# Anthropic shape -> OpenAI shape
# ---------------------------------------------------------------------------


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`input_schema` becomes `parameters`, wrapped in a function envelope."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        }
        for tool in tools
    ]


def to_openai_messages(
    system: list[dict[str, Any]] | str, messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Flatten Anthropic's block structure into OpenAI's flatter message list.

    Three shapes have to be handled, and the third is the one people get wrong: Anthropic
    returns tool results as blocks inside a *user* message, while OpenAI wants one message
    per result with `role: "tool"`.
    """
    out: list[dict[str, Any]] = []

    if system:
        text = system if isinstance(system, str) else "\n\n".join(b.get("text", "") for b in system)
        if text.strip():
            out.append({"role": "system", "content": text})

    for message in messages:
        role = message["role"]
        content = message["content"]

        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        if role == "assistant":
            text_parts, calls = [], []
            for block in content:
                kind = getattr(block, "type", None) or (
                    block.get("type") if isinstance(block, dict) else None
                )
                if kind == "text":
                    text_parts.append(_field(block, "text"))
                elif kind == "tool_use":
                    calls.append(
                        {
                            "id": _field(block, "id"),
                            "type": "function",
                            "function": {
                                "name": _field(block, "name"),
                                "arguments": json.dumps(_field(block, "input") or {}),
                            },
                        }
                    )
            entry: dict[str, Any] = {"role": "assistant", "content": "\n".join(text_parts) or None}
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
            continue

        # A user message carrying tool results becomes one "tool" message per result.
        plain: list[str] = []
        for block in content:
            kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if kind == "tool_result":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": block.get("content", ""),
                    }
                )
            elif kind == "text":
                plain.append(_field(block, "text"))
        if plain:
            out.append({"role": "user", "content": "\n".join(plain)})

    return out


def _field(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


# ---------------------------------------------------------------------------
# OpenAI shape -> the runner's shape
# ---------------------------------------------------------------------------


def from_openai_response(payload: dict[str, Any]) -> Response:
    """Read one chat completion back into the blocks the runner expects."""
    choices = payload.get("choices") or []
    if not choices:
        raise OpenAICompatError(f"no choices in response: {json.dumps(payload)[:300]}")

    message = choices[0].get("message") or {}
    blocks: list[Block] = []

    text = message.get("content")
    if isinstance(text, list):
        # Some servers return content parts rather than a plain string.
        text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
    if text:
        blocks.append(Block(type="text", text=str(text)))

    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        blocks.append(
            Block(
                type="tool_use",
                id=str(call.get("id") or f"call_{len(blocks)}"),
                name=str(function.get("name") or ""),
                input=_parse_arguments(function.get("arguments")),
            )
        )

    finish = choices[0].get("finish_reason") or ""
    stop_reason = FINISH_REASONS.get(finish, "end_turn")
    # Some servers report "stop" even when they emitted tool calls. The blocks are the
    # truth: if it asked for a tool, the turn is not over.
    if stop_reason == "end_turn" and any(b.type == "tool_use" for b in blocks):
        stop_reason = "tool_use"

    usage = payload.get("usage") or {}
    return Response(
        content=blocks,
        stop_reason=stop_reason,
        usage=Usage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            cache_read_input_tokens=int(
                (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
            ),
        ),
    )


def _parse_arguments(raw: Any) -> dict[str, Any]:
    """Arguments arrive as a JSON *string*, and small models get that string wrong.

    A malformed one is returned as an empty call rather than raised: the dispatcher will
    reject it, the trace will record what was attempted, and a model that cannot produce
    valid arguments is a finding rather than a crashed sweep.
    """
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"__unparsable_arguments__": str(raw)[:200]}
    return parsed if isinstance(parsed, dict) else {"__unexpected_arguments__": parsed}


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------


@dataclass
class _Messages:
    client: OpenAICompatClient

    def create(self, **kwargs: Any) -> Response:
        return self.client.complete(**kwargs)


@dataclass
class OpenAICompatClient:
    """Stands in for `anthropic.Anthropic()`, talking to a chat-completions endpoint."""

    base_url: str
    api_key: str = ""
    transport: Transport = http_transport
    messages: _Messages = field(init=False)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self.messages = _Messages(self)

    @property
    def url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    def complete(
        self,
        *,
        model: str,
        max_tokens: int,
        system: Any = "",
        messages: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        **_ignored: Any,
    ) -> Response:
        """`_ignored` swallows `thinking` and `output_config`, which have no equivalent here.

        Silently, and on purpose: `models.py` already declines to send them for a non-Anthropic
        provider, so anything arriving here is a caller mistake rather than a request the
        endpoint could honour.
        """
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": to_openai_messages(system, messages or []),
        }
        if tools:
            payload["tools"] = to_openai_tools(tools)
            payload["tool_choice"] = "auto"

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        return from_openai_response(self.transport(self.url, headers, payload))
