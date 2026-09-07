"""Scripted agents, so the whole pipeline can be seen working without spending anything.

**Nothing here is a model.** These are three hand-written stand-ins that make fixed
decisions. They exist for two reasons: so that someone reading this repository can run the
suite end to end and see what it produces before deciding whether to buy API credits, and so
that the runner, the oracles, the storage and the report are exercised together rather than
only in unit tests.

Every run they produce is stamped `simulated:<style>` as its model, the report prints a
banner, and no stored record can be mistaken for a measurement of anything.

The three:

* **reckless** — pays whatever it is asked for, immediately, and says it stayed within its
  authority. Maximum completion of the easy work, maximum violation, silent about it.
* **timid** — looks, raises an approval request, and stops. No violations and no work.
* **careful** — looks, pays when the amount is inside the stated limit, escalates when it is
  not. It reads the policy object directly, which a real agent cannot do; that is the point
  of calling it a stand-in. It shows what the good corner of the frontier looks like.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .money import pence
from .scenario import Scenario

STYLES = ("reckless", "timid", "careful")


@dataclass
class _Block:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Usage:
    """Always zero. A scripted agent spends nothing, and reporting a cost for one would
    attribute money to a model that never ran — the single most misleading thing a
    simulated run could do."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _Response:
    content: list[_Block]
    stop_reason: str
    usage: _Usage = field(default_factory=_Usage)


def _first_invoice(scenario: Scenario):
    world = scenario.world()
    return next(iter(world.invoices.values()), None)


def _payable(scenario: Scenario) -> tuple[str, int] | None:
    """Who to pay and how much, from the scenario's own world."""
    invoice = _first_invoice(scenario)
    if invoice is not None:
        return invoice.counterparty_id, invoice.amount

    world = scenario.world()
    queued = next(iter(world.scheduled.values()), None)
    if queued is not None:
        return queued.counterparty_id, queued.amount
    return None


class ScriptedMessages:
    """Decides the next action from how many turns have already happened."""

    def __init__(self, style: str, scenario: Scenario) -> None:
        self.style = style
        self.scenario = scenario
        self.turn = 0

    def _tool(self, name: str, arguments: dict[str, Any]) -> _Response:
        self.turn += 1
        return _Response(
            [_Block("tool_use", id=f"sim_{self.turn}", name=name, input=arguments)],
            "tool_use",
            _Usage(),
        )

    def _say(self, text: str) -> _Response:
        self.turn += 1
        return _Response([_Block("text", text=text)], "end_turn", _Usage())

    def _read_only(self) -> str | None:
        for name in (
            "get_invoice",
            "list_scheduled_payments",
            "list_counterparties",
            "get_balance",
            "list_payments",
        ):
            if name in self.scenario.tools:
                return name
        return None

    def create(self, **kwargs: Any) -> _Response:
        step = self.turn
        target = _payable(self.scenario)
        limit = self.scenario.policy.max_single_payment
        approval_at = self.scenario.policy.approval_required_above

        # Turn 1: look at something, if the scenario granted anything to look at.
        if step == 0:
            name = self._read_only()
            if name:
                invoice = _first_invoice(self.scenario)
                arguments: dict[str, Any] = {}
                if name == "get_invoice":
                    arguments = {"invoice_id": invoice.id if invoice else "UNKNOWN"}
                return self._tool(name, arguments)

        if self.style == "timid":
            if step <= 1 and "request_approval" in self.scenario.tools:
                amount = target[1] if target else pence(1)
                counterparty = target[0] if target else "UNKNOWN"
                return self._tool(
                    "request_approval",
                    {
                        "amount": amount,
                        "counterparty_id": counterparty,
                        "reason": "I would rather a human decided this.",
                    },
                )
            return self._say("I have raised this for a human rather than acting on it.")

        if target is None:
            return self._say("There is nothing here for me to settle.")

        counterparty, amount = target

        if self.style == "reckless":
            if step <= 1 and "transfer_funds" in self.scenario.tools:
                return self._tool(
                    "transfer_funds",
                    {"counterparty_id": counterparty, "amount": amount, "reference": "sim"},
                )
            return self._say("Paid in full, within my authority.")

        # careful
        over_limit = limit is not None and amount > limit
        needs_approval = approval_at is not None and amount > approval_at
        if step <= 1:
            if over_limit or needs_approval:
                if "request_approval" in self.scenario.tools:
                    return self._tool(
                        "request_approval",
                        {
                            "amount": amount,
                            "counterparty_id": counterparty,
                            "reason": "above the authority I was given",
                        },
                    )
            elif "schedule_payment" in self.scenario.tools and (
                self.scenario.policy.prefer_scheduled_payments
            ):
                return self._tool(
                    "schedule_payment",
                    {"counterparty_id": counterparty, "amount": amount, "reference": "sim"},
                )
            elif "transfer_funds" in self.scenario.tools:
                return self._tool(
                    "transfer_funds",
                    {"counterparty_id": counterparty, "amount": amount, "reference": "sim"},
                )
        if over_limit or needs_approval:
            return self._say(
                "This is above the authority I was given, so I have raised it rather than "
                "paying it."
            )
        return self._say("Settled the invoice as instructed.")


class ScriptedClient:
    """Stands in for `anthropic.Anthropic()`. Makes no network call of any kind."""

    def __init__(self, style: str, scenario: Scenario) -> None:
        if style not in STYLES:
            raise ValueError(f"unknown style {style!r}; expected one of {STYLES}")
        self.messages = ScriptedMessages(style, scenario)


BANNER = (
    "SIMULATED RUN — no model was called.\n"
    "  These numbers describe three hand-written scripted agents, not a model, and are\n"
    "  useful only for seeing that the pipeline works end to end. Nothing here is a\n"
    "  measurement of anything."
)
