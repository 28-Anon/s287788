"""What a run costs, tracked in integer micro-dollars.

Integers for the same reason the sandbox uses integer pence: a suite that sums a few
thousand floats and reports a total should not have the total depend on the order it added
them up. This money is real (it is the API bill) and entirely separate from the sandbox's
money (which is fictional and denominated in pence) — the two are never mixed, and neither
is ever a float.

Two facts about cost that are easy to get backwards, both recorded here because they are
what makes this suite cheap to run:

**`max_tokens` is a ceiling, not a budget.** You are billed for tokens generated. Raising it
from 256 to 8192 costs nothing when the answer is short; it only stops a long deliberation
being truncated, and a truncated call wastes everything already spent on it.

**Turns are the cost, not verbosity.** An agent scenario resends the whole conversation each
turn, so ten turns means the prefix is billed ten times. That is what caching is for and what
`max_turns` is for.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ModelSpec

#: A cache write costs about 1.25x the base input rate at the default 5-minute TTL.
CACHE_WRITE_MULTIPLIER_5M = 1.25

#: A cache read costs about 0.1x the base input rate. This is the whole reason to cache.
CACHE_READ_MULTIPLIER = 0.1

MICROS_PER_DOLLAR = 1_000_000
TOKENS_PER_MTOK = 1_000_000


@dataclass(frozen=True)
class Usage:
    """Tokens billed for one API call. Field names match the SDK's usage object."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_input_tokens=(
                self.cache_creation_input_tokens + other.cache_creation_input_tokens
            ),
            cache_read_input_tokens=(self.cache_read_input_tokens + other.cache_read_input_tokens),
        )

    @classmethod
    def from_response(cls, usage: object) -> Usage:
        """Read an SDK usage object defensively.

        Fields have been added to it over time and will be again; a missing one should cost
        a slightly wrong number, not a crashed run halfway through a paid sweep.
        """
        return cls(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_creation_input_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
            cache_read_input_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
        }


def cost_micros(usage: Usage, spec: ModelSpec) -> int:
    """Cost of one call, in micro-dollars. Rounded once, at the end."""
    input_rate = spec.input_per_mtok / TOKENS_PER_MTOK
    output_rate = spec.output_per_mtok / TOKENS_PER_MTOK

    dollars = (
        usage.input_tokens * input_rate
        + usage.cache_creation_input_tokens * input_rate * CACHE_WRITE_MULTIPLIER_5M
        + usage.cache_read_input_tokens * input_rate * CACHE_READ_MULTIPLIER
        + usage.output_tokens * output_rate
    )
    return round(dollars * MICROS_PER_DOLLAR)


def format_micros(micros: int) -> str:
    """Micro-dollars for display. Sub-cent figures are the normal case here."""
    dollars = micros / MICROS_PER_DOLLAR
    if dollars < 0.01:
        return f"${dollars:.4f}"
    if dollars < 1:
        return f"${dollars:.3f}"
    return f"${dollars:,.2f}"
