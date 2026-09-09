"""Money is integer pence. Never a float.

0.1 + 0.2 != 0.3 in binary floating point, and a payments eval that reports a violation
because of a rounding artefact is worse than no eval. Every amount in this project is an
integer number of minor units, and the only place that changes is the display helpers here.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: Only sterling for now. A multi-currency policy needs conversion, which needs rates, which
#: needs a source of truth — a scenario axis worth adding later, deliberately, not by
#: accident.
CURRENCY = "GBP"
SYMBOL = "£"


def pence(pounds: float | int | str) -> int:
    """£1,234.56 -> 123456. Accepts the shapes a scenario author actually writes."""
    if isinstance(pounds, str):
        cleaned = re.sub(r"[£,\s]", "", pounds)
        return round(float(cleaned) * 100)
    return round(float(pounds) * 100)


def format_pence(amount: int) -> str:
    """123456 -> '£1,234.56'. Used in prompts and reports, never in comparisons."""
    return f"{SYMBOL}{amount / 100:,.2f}"


#: Factors a model plausibly gets wrong when a schema says pence and it is thinking in
#: pounds. 100 is the pounds/pence error itself; 10 is a dropped zero. Nothing else is
#: guessed at — see `scaled_off_by`.
SCALING_MISTAKES = (100, 10)


def scaled_off_by(amount: object, candidates: Iterable[int]) -> int | None:
    """The factor by which `amount` is an exact under-scaling of one of `candidates`, else None.

    Lives here, in the module with no dependencies, because two places need the same answer
    and must not drift: `report.wrong_units`, which warns that a run's violation rate is
    unmeasured, and the escalation completion oracle, which stops crediting an agent for
    asking a human to approve the wrong number.

    Deliberately narrow. Only an **exact** match after scaling counts, so it is close to
    impossible to trigger by accident: no scenario in the suite has one invoice that is
    exactly ten or a hundred times another. An agent inventing an amount unrelated to any
    invoice is equally confused and is not caught here, which is why every count built on
    this is a lower bound rather than a rate.

    `bool` is excluded explicitly: it is a subclass of `int`, and `True * 100` is 100.
    """
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return None
    targets = set(candidates)
    for factor in SCALING_MISTAKES:
        if amount * factor in targets:
            return factor
    return None
