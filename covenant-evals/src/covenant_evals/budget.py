"""API spend tracking.

Cost discipline is a deliverable of this project, not an afterthought. A control that costs
£4 per document does not ship, so cost-per-item is a result you report alongside accuracy.

Every API call should end with a call to record(). Nothing here talks to the network.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

SPEND_LOG = Path(__file__).resolve().parents[2] / "runs" / "spend.jsonl"

# ---------------------------------------------------------------------------
# Pricing, in US dollars per million tokens.
#
# Source: Anthropic pricing documentation, checked 2026-08-29.
# VERIFY THESE BEFORE RELYING ON THEM. Prices change and this file will not notice.
# ---------------------------------------------------------------------------

PRICING: dict[str, dict[str, float]] = {
    "claude-opus-5": {"input": 5.0, "output": 25.0},
    "claude-sonnet-5": {"input": 2.0, "output": 10.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}

#: Reading from the prompt cache costs a fraction of the normal input rate.
CACHE_READ_MULTIPLIER = 0.1

#: Writing to the prompt cache costs slightly more than normal input, for the default
#: 5-minute time to live. The 1-hour TTL is priced differently — check the docs before
#: using it, do not assume this constant applies.
CACHE_WRITE_MULTIPLIER_5M = 1.25


@dataclass
class Usage:
    """Token counts from one API response.

    Field names match the `usage` object the API returns, so you can construct this
    directly from a response without renaming anything.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


def cost_usd(model: str, usage: Usage) -> float:
    """Cost of a single call, in dollars.

    Raises KeyError for an unknown model — deliberately. Silently pricing an unknown model
    at zero is how a budget quietly stops being true.
    """
    if model not in PRICING:
        raise KeyError(f"no pricing for model {model!r}; add it to PRICING and cite a source")

    rates = PRICING[model]
    per_token_in = rates["input"] / 1_000_000
    per_token_out = rates["output"] / 1_000_000

    return (
        usage.input_tokens * per_token_in
        + usage.output_tokens * per_token_out
        + usage.cache_read_input_tokens * per_token_in * CACHE_READ_MULTIPLIER
        + usage.cache_creation_input_tokens * per_token_in * CACHE_WRITE_MULTIPLIER_5M
    )


def cache_hit_rate(usage: Usage) -> float:
    """Share of input tokens served from the cache, 0.0 to 1.0.

    If this is 0.0 across repeated runs over the same document, caching is not working:
    something in your prompt prefix is varying between calls. A timestamp, an unsorted
    json.dumps, a reordered tool list. Find it — it is the difference between a $16 run
    and an $80 one.
    """
    total_input = usage.input_tokens + usage.cache_read_input_tokens
    if total_input == 0:
        return 0.0
    return usage.cache_read_input_tokens / total_input


def record(model: str, usage: Usage, *, note: str = "", log: Path | None = None) -> float:
    """Append one call to the spend log and return what it cost."""
    amount = cost_usd(model, usage)
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "cost_usd": round(amount, 6),
        "note": note,
        **asdict(usage),
    }
    path = log or SPEND_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return amount


def summary(log: Path | None = None) -> dict[str, object]:
    """Totals for `make budget`. Returns zeros rather than failing on a missing log."""
    path = log or SPEND_LOG
    if not path.exists():
        return {"calls": 0, "total_usd": 0.0, "by_model": {}}

    calls = 0
    total = 0.0
    by_model: dict[str, dict[str, float]] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        calls += 1
        total += entry["cost_usd"]
        bucket = by_model.setdefault(entry["model"], {"calls": 0, "usd": 0.0})
        bucket["calls"] += 1
        bucket["usd"] = round(bucket["usd"] + entry["cost_usd"], 6)

    return {"calls": calls, "total_usd": round(total, 4), "by_model": by_model}
