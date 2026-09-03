"""What a scenario is.

A scenario is a policy, a world, a task, and two oracles. The oracles read the trace and
answer two questions: **was a rule broken**, and **did the legitimate work get done**.

Both are needed. An agent that refuses everything breaks no rules and is useless, so a
suite that only measures violations rewards refusal. The result is a frontier, not a number.

One rule governs every oracle in this project:

> **An oracle may only check a rule the agent was told.**

If the policy does not say "do not split a payment to get under the limit", then an agent
that splits one has not broken a rule — it has found a gap in the policy, which is a finding
about the policy. Testing unstated rules is how an eval quietly becomes a measure of whether
the model guessed what you meant.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .policy import Policy
from .trace import Trace
from .world import PaymentsWorld

SCHEMA_VERSION = 1

#: The taxonomy. A scenario declares which failure it is built to catch.
CATEGORIES = (
    "hard_limit",
    "dual_control",
    "allowlist",
    "injection",
    "escalation",
    "irreversibility",
    "confused_deputy",
    "authority_pressure",
    "partial_failure",
    "limit_persistence",
)

#: What makes violating tempting. Recorded so results can be broken down by it: if an agent
#: only fails under time pressure, that is a different finding from failing everywhere.
PRESSURES = ("none", "urgency", "authority", "sympathy", "ambiguity", "tool_failure")

#: An oracle returns the reason a rule was broken, or None if it was not. Returning the
#: reason rather than a bool means the report explains itself.
Oracle = Callable[[Trace, PaymentsWorld], "str | None"]
Completion = Callable[[Trace, PaymentsWorld], bool]


@dataclass(frozen=True)
class Scenario:
    id: str
    category: str
    pressure: str

    policy: Policy

    #: A factory, not an instance: the world is mutable and every run needs a fresh one.
    world: Callable[[], PaymentsWorld]

    #: Tools the agent is granted. A tool it does not have cannot be misused, so granting
    #: one is itself part of the test — see the confused-deputy scenarios.
    tools: tuple[str, ...]

    task: str

    violated: Oracle
    completed: Completion

    #: What this scenario is actually testing, in a sentence. Goes in the report next to
    #: the result, so a reader never has to reverse-engineer the intent from the oracle.
    tests: str = ""

    version: int = field(default=SCHEMA_VERSION, compare=False)


def validate(scenario: Scenario) -> list[str]:
    """Problems with a scenario. Empty means it is well formed."""
    errors: list[str] = []

    if not scenario.id.strip():
        errors.append("id must not be empty")
    if scenario.category not in CATEGORIES:
        errors.append(f"category must be one of {list(CATEGORIES)}")
    if scenario.pressure not in PRESSURES:
        errors.append(f"pressure must be one of {list(PRESSURES)}")
    if len(scenario.task.strip()) < 20:
        errors.append("task is too short to be a realistic instruction")
    if not scenario.tools:
        errors.append("a scenario with no tools cannot test anything")
    if len(scenario.tests.strip()) < 15:
        errors.append("tests must say what this scenario is checking, for the report")

    # The world factory has to actually build one, and build a *different* one each time.
    try:
        first, second = scenario.world(), scenario.world()
    except Exception as exc:  # noqa: BLE001 - any failure here is a scenario bug
        errors.append(f"world factory raised: {exc}")
    else:
        if first is second:
            errors.append("world factory returns the same object twice; runs would share state")

    return errors


def validate_all(scenarios: list[Scenario]) -> dict[str, list[str]]:
    problems = {s.id: errs for s in scenarios if (errs := validate(s))}

    seen: dict[str, int] = {}
    for scenario in scenarios:
        seen[scenario.id] = seen.get(scenario.id, 0) + 1
    for scenario_id, count in seen.items():
        if count > 1:
            problems.setdefault(scenario_id, []).append(f"id used by {count} scenarios")

    return problems
