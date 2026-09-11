"""The scenario suite.

Split across modules by what they test rather than by when they were written, except for
`payments.py`, which keeps the original ten exactly as they were. Those ten are the ones
the split was frozen against and the ones the write-up compares everything else to; moving
or editing them would quietly change what a past result meant.
"""

from ..scenario import Scenario
from . import adversarial, authorisation, harder, limits, operations, payments

SUITE: tuple[Scenario, ...] = (
    payments.SUITE
    + limits.SUITE
    + authorisation.SUITE
    + adversarial.SUITE
    + operations.SUITE
    + harder.SUITE
)


def by_id(scenario_id: str) -> Scenario | None:
    return next((s for s in SUITE if s.id == scenario_id), None)


def by_category(category: str) -> tuple[Scenario, ...]:
    return tuple(s for s in SUITE if s.category == category)


def by_pressure(pressure: str) -> tuple[Scenario, ...]:
    return tuple(s for s in SUITE if s.pressure == pressure)


__all__ = ["SUITE", "by_category", "by_id", "by_pressure"]
