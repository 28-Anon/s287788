"""A canned client, so the whole pipeline can be exercised without spending anything.

covenant-evals had the same thing for the same reason: the first time you run a harness end
to end should not also be the first time you pay for it. `run --dry-run` uses this to prove
the path works — splits, agent loop, oracles, metrics, report — on a machine with no API key
at all, which is most of the machines this project gets developed on.

The numbers it produces are **not results**. A client that always declines has a 0% violation
rate by construction, which is exactly the degenerate corner the frontier exists to expose,
and seeing the report say so is a useful thing to look at before a real run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DECLINE = (
    "I have looked at this and I cannot complete it within the payment authority I was "
    "given, so I have not moved any money."
)


@dataclass
class _Text:
    text: str
    type: str = "text"


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class _Response:
    content: list[Any]
    stop_reason: str = "end_turn"
    usage: _Usage = field(default_factory=_Usage)
    stop_details: Any = None


class _Messages:
    def __init__(self, message: str) -> None:
        self.message = message
        self.calls = 0

    def create(self, **kwargs: Any) -> _Response:
        self.calls += 1
        return _Response(content=[_Text(self.message)])


class DecliningClient:
    """Answers every scenario by declining, without calling a tool. Costs nothing."""

    def __init__(self, message: str = DECLINE) -> None:
        self.messages = _Messages(message)
