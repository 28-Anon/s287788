"""One property, checked against inputs nobody sat down and imagined.

Every other test in this project is an **example**: given this input, expect this output.
An example can only catch a bug the author thought of, because the author wrote both halves
— the input and the expectation. When both encode the same wrong belief, the test passes
honestly and proves only that the author was consistent with himself.

That is not a hypothetical. Every fake in this repository sent `{"amount": 18000}`, because
that is what the author believed a model sends. The first real model sent `{"amount":
"18000"}`, and `"18000" > 5000000` is not a comparison Python will make. The **violation
oracle** raised. Violation counts attempts, so a model attempting £120,000 against a £50,000
limit crashed the scorer instead of being recorded — the suite losing the exact finding it
exists to make. 481 example tests were green at the time.

So this file states a **property** instead:

    No oracle may raise. Not on any tool call, with any argument, in any scenario.

The rule and the inputs now come from different places. The author only has to state what
must always be true; he does not have to guess what will break it. That is the one kind of
test that can catch a bug its author did not think of.

`JUNK` is a hand-written list rather than a fuzzing library on purpose — this project takes
no dependency it can avoid — so it is weaker than real property-based testing and should be
extended whenever a real run turns up a new shape. Every entry below is either something a
model has actually sent or the type-confusion next door to it.
"""

import pytest

from control_evals.scenarios import SUITE
from control_evals.tools import dispatch
from control_evals.trace import Trace

#: Values a tool argument might arrive as. `"18000"` and `"£18,000"` are not inventions:
#: llama3.2:3b sent the first, and the second is the misreading that would turn £18,000 into
#: £180 if it were ever parsed rather than refused.
JUNK = ["18000", "£18,000", "", None, -1, 0, True, False, 10**18, 1.5, [], {}, "NaN", "0x10"]

#: Every argument name any tool in the suite takes, so one pass covers all of them.
EVERY_ARGUMENT = (
    "amount",
    "counterparty_id",
    "invoice_id",
    "reference",
    "reason",
    "payment_id",
    "name",
    "account_number",
)


@pytest.mark.parametrize("value", JUNK, ids=repr)
def test_no_oracle_raises_on_any_argument_any_scenario(value):
    """The property. If this fails, a real run somewhere loses a finding to a traceback."""
    for scenario in SUITE:
        world = scenario.world()
        trace = Trace(offered_tools=tuple(scenario.tools))
        for tool in scenario.tools:
            dispatch(world, trace, tool, dict.fromkeys(EVERY_ARGUMENT, value))

        for name, oracle in (("violated", scenario.violated), ("completed", scenario.completed)):
            try:
                oracle(trace, world)
            except Exception as exc:  # noqa: BLE001 — that it raised at all is the failure
                pytest.fail(
                    f"{scenario.id} {name} raised on {value!r}: {type(exc).__name__}: {exc}"
                )


@pytest.mark.parametrize("value", JUNK, ids=repr)
def test_the_world_survives_any_argument_without_raising(value):
    """`dispatch` promises never to raise: a tool that did would end the run, and an agent
    calling a tool wrongly is data about the agent, not a reason to lose the scenario."""
    for scenario in SUITE:
        world = scenario.world()
        trace = Trace(offered_tools=tuple(scenario.tools))
        for tool in scenario.tools:
            result = dispatch(world, trace, tool, dict.fromkeys(EVERY_ARGUMENT, value))
            assert isinstance(result, dict)


@pytest.mark.parametrize("value", JUNK, ids=repr)
def test_no_amount_reaches_the_trace_as_anything_but_an_integer(value):
    """The invariant the oracles are written against, stated where it can be checked.

    Nine call sites do `arguments.get("amount", 0)` and none of them defend themselves. They
    do not have to, as long as this holds.
    """
    for scenario in SUITE:
        world = scenario.world()
        trace = Trace(offered_tools=tuple(scenario.tools))
        for tool in scenario.tools:
            dispatch(world, trace, tool, dict.fromkeys(EVERY_ARGUMENT, value))

        for call in trace.calls:
            if "amount" in call.arguments:
                amount = call.arguments["amount"]
                assert isinstance(amount, int) and not isinstance(amount, bool), (
                    f"{scenario.id} recorded amount={amount!r} ({type(amount).__name__})"
                )
