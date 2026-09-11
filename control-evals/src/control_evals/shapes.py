"""The response shape the runner reads, in one place.

`runner.py` reads six things off whatever a client hands back: `content` (a list of blocks
with `.type`, and `.text` or `.id`/`.name`/`.input`), `stop_reason`, and `usage`. That is the
whole contract, and it happens to be the Anthropic SDK's shape.

Writing it down as classes means everything that stands in for a client — the OpenAI-compatible
adapter, the scripted agents, the test fakes — produces the same objects rather than three
separate guesses at what the runner wants. When the contract changes, it changes here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: What `stop_reason` may be, as the runner branches on it.
STOP_REASONS = ("end_turn", "tool_use", "max_tokens", "refusal", "pause_turn")


@dataclass
class Block:
    """One content block. `text` blocks carry text; `tool_use` blocks carry a call."""

    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class Response:
    content: list[Block]
    stop_reason: str
    usage: Usage = field(default_factory=Usage)
