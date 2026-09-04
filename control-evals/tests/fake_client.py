"""A fake Anthropic client, so the agent loop is tested without a network or a key.

Scripted rather than clever: you hand it the turns you want the model to take, and it hands
them back one per call. That makes it possible to write a test for "the agent claims it
complied and then transfers £75,000" and know exactly what is being asserted.

It records every request, which is how the caching and tool-choice tests check what was
actually sent rather than trusting the code that sent it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    name: str
    input: dict[str, Any]
    id: str = "tu_1"
    type: str = "tool_use"


@dataclass
class FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 20
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class FakeResponse:
    content: list[Any]
    stop_reason: str
    usage: FakeUsage = field(default_factory=FakeUsage)
    stop_details: Any = None


@dataclass
class StopDetails:
    category: str = "cyber"
    explanation: str = ""


class FakeMessages:
    def __init__(self, turns: list[FakeResponse]) -> None:
        self.turns = list(turns)
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        # Snapshot the message list. The agent mutates it in place across turns, so storing
        # the reference would make every recorded request show the final state — and a test
        # asserting "the tool results went out in one message" would be asserting nothing.
        recorded = dict(kwargs)
        recorded["messages"] = list(kwargs.get("messages", []))
        self.requests.append(recorded)
        if not self.turns:
            raise AssertionError(
                "the agent asked for more turns than the script provides; either the loop "
                "is not stopping or the test needs another turn"
            )
        return self.turns.pop(0)


class FakeClient:
    def __init__(self, turns: list[FakeResponse]) -> None:
        self.messages = FakeMessages(turns)


class ExplodingClient:
    """Raises on the first call, to test that a failure is a result and not a crash."""

    class _Messages:
        def create(self, **kwargs: Any) -> Any:
            raise RuntimeError("connection reset")

    def __init__(self) -> None:
        self.messages = self._Messages()


# -- shorthand for building scripts ------------------------------------------------


def says(text: str) -> FakeResponse:
    """A final turn: the agent talks and stops."""
    return FakeResponse(content=[TextBlock(text)], stop_reason="end_turn")


def calls(name: str, arguments: dict[str, Any], *, text: str = "", block_id: str = "tu_1"):
    """A tool-calling turn, optionally with text alongside it."""
    content: list[Any] = []
    if text:
        content.append(TextBlock(text))
    content.append(ToolUseBlock(name=name, input=arguments, id=block_id))
    return FakeResponse(content=content, stop_reason="tool_use")


def calls_many(pairs: list[tuple[str, dict[str, Any]]]) -> FakeResponse:
    """One assistant turn containing several tool calls, as parallel tool use produces."""
    return FakeResponse(
        content=[
            ToolUseBlock(name=name, input=arguments, id=f"tu_{i}")
            for i, (name, arguments) in enumerate(pairs)
        ],
        stop_reason="tool_use",
    )


def refuses(category: str = "cyber") -> FakeResponse:
    return FakeResponse(
        content=[], stop_reason="refusal", stop_details=StopDetails(category=category)
    )
