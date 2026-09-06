"""A fake Anthropic client, shared by every test that drives the agent loop.

A plain module rather than a test module. Importing helpers out of `test_runner` worked
locally and broke in CI, for a reason worth writing down: `python -m pytest` puts the working
directory on `sys.path` and bare `pytest` does not, so `from tests.test_runner import ...`
resolved on my machine and raised ModuleNotFoundError on the runner. The divergence, not the
import, was the bug — `pythonpath` in pyproject.toml now makes both invocations identical.

The fake mimics the SDK's response object closely enough that the loop cannot tell the
difference: content blocks with `.type`, tool_use blocks with `.id`/`.name`/`.input`, a
`.stop_reason` and a `.usage`. That is also its standing risk — if the SDK's shape changes,
these tests keep passing while a real sweep breaks, which is why `runner.py` reads every
response field defensively and why LIMITATIONS.md says the first real sweep is what actually
validates the integration.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeBlock:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeUsage:
    input_tokens: int = 1000
    output_tokens: int = 200
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class FakeResponse:
    content: list[FakeBlock]
    stop_reason: str
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeMessages:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.script:
            # A model stuck in a read loop — the realistic "never stops" case, and the one
            # the turn cap exists for. A real response with stop_reason "tool_use" always
            # carries a tool_use block, so the fake carries one too.
            return FakeResponse(
                [FakeBlock("tool_use", id=f"tu_{len(self.calls)}", name="get_balance")],
                "tool_use",
            )
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class FakeClient:
    def __init__(self, *script):
        self.messages = FakeMessages(script)


def say(text, stop="end_turn"):
    return FakeResponse([FakeBlock("text", text)], stop)


def call(tool, arguments, block_id="tu_1", text=""):
    blocks = [FakeBlock("tool_use", id=block_id, name=tool, input=arguments)]
    if text:
        blocks.insert(0, FakeBlock("text", text))
    return FakeResponse(blocks, "tool_use")
