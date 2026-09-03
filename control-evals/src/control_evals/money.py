"""Money is integer pence. Never a float.

0.1 + 0.2 != 0.3 in binary floating point, and a payments eval that reports a violation
because of a rounding artefact is worse than no eval. Every amount in this project is an
integer number of minor units, and the only place that changes is the display helpers here.
"""

from __future__ import annotations

import re

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
