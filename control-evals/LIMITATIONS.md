# Limitations

Written before any results exist, and updated as more appear. It is much harder to be honest
about limitations once there is a number you are pleased with.

## 1. Completion is a weaker measurement than violation

Violation is exact: the policy said £50,000, the trace shows £75,000, and there is nothing to
interpret. Completion is not. Most of these scenarios *cannot* be done within the rules, so
the correct outcome is to escalate or decline — and "declined properly" is a judgement that
has been reduced to a proxy: did it investigate, and did it say something.

An agent could satisfy that proxy while producing a useless answer. The frontier is
therefore precise on one axis and approximate on the other, and any claim made from it
should say so.

## 2. The silent violation rate is a lower bound, not a rate

The scariest failure is violating *while stating you complied*, and it is measured now: the
oracle catches the violation from the trace, and `runner.claims_compliance` looks for an
assertion of compliance in the closing message.

That second half is keyword-based and it under-counts by construction. An agent that writes
"all done, invoice settled as instructed" has implied compliance without using any phrase in
the list. The list is deliberately narrow — a false positive would inflate the single most
alarming number in the suite — so the error runs one way, towards missing them.

Report it as a floor. "At least 20% of violations were concealed" is a claim this supports;
"20% of violations were concealed" is not.

## 3. The scenarios test what one person imagined

Ten scenarios written by one author, who chose which pressures to apply and which failures
to look for. A control failure nobody thought of is not in here, and the suite cannot tell
you about it. That is the standing weakness of every constructed eval and the reason the
failure taxonomy — what actually happened, with traces — matters more than the rates.

## 4. The sandbox is not a payment system

No real rails, no settlement, no reconciliation, no fraud checks, and a `request_approval`
that never resolves. Agents behave differently in richer environments, and results here
transfer to real deployments only as far as the abstraction holds.

The one place this is deliberately unrealistic is important enough to restate: **the world
permits violations.** A real system would enforce limits itself. Removing that enforcement
is what makes the agent's own behaviour visible, and it means these results describe the
agent, not a deployment.

## 5. One category is uncovered

`irreversibility` — whether an agent treats an unrecoverable action more carefully than a
recoverable one — has no scenario, because it needs a reversible alternative in the world
(a payment that can be held or recalled). It stays in `CATEGORIES` so its absence shows up
in the tests rather than being quietly forgotten.

## 6. The content fingerprint does not cover the oracles

`data/splits.json` records a hash of each scenario's policy, task, tools and starting world,
so an invoice quietly changed from £75,000 to £45,000 fails `pytest`. It does not hash
`violated` or `completed`, because those are callables and hashing a lambda is either
meaningless or brittle.

So the guard is one-sided: the data a scenario presents is locked, the judgement it applies
is not. An oracle can be loosened after the freeze without anything noticing. The partial
mitigation is that every oracle is run against a synthetic compliant trace and a synthetic
violating trace in `tests/test_scenarios.py`, so a loosened oracle usually breaks a test —
usually, not always.

## 7. The split seed does nothing yet

Families are shuffled inside their category before assignment, and today there is at most
one family per category, so there is nothing to shuffle: re-freezing with a different seed
gives the identical draw. The assignment is still balanced and still reproducible, but the
seed recorded in `splits.json` implies a randomisation that is not happening. It starts
mattering in week 6, when categories stop having one family each.

Stated because a reader who assumed the split was randomly drawn would be assuming something
that is not yet true. Tested, in `test_the_seed_is_inert_when_every_category_has_one_family`.

## 8. dev is two scenarios

Splitting a ten-scenario suite three ways gives a dev split you cannot learn anything from —
two scenarios, in two categories, out of ten. The alternative was to wait until week 8 and
freeze fifty, but a split cut after you have been reading the results is not a split, so it
is cut now and grown with `splits assign-new`, which never moves anything already placed.

Until the suite is large, treat dev as a smoke test rather than as a development set.

Adding the four routine scenarios made this worse before it gets better: the shares are now
14/57/29 against targets of 20/50/30, because the allocator places a whole family at a time
and the two-scenario `routine` family overshot `test`. That self-corrects as more families
are added — the next ones will find dev furthest below target. Re-cutting the freeze to
tidy it up would be exactly the silent redraw the design forbids.

## 9. Escalation precision rests on four scenarios, and none of them are in dev

Four scenarios now carry `escalation="unnecessary"` — routine-001, routine-002,
boundary-001, benign-001 — so over-escalation is detectable where it was not. An agent that
asks a human about everything scores 40% precision on `test` rather than the 100% it used to.

Three things to keep in mind about the number.

**Four is a thin denominator.** The interval on a precision estimate over four scenarios
covers most of the range, and the report says so. It is a usable signal for "does this
system escalate indiscriminately" and not much more than that yet.

**dev cannot measure it at all.** `assign_new` put `routine` and `benign` in test and
`boundary` in heldout, and dev got none of them. dev is two scenarios and LIMITATIONS #8
already says to treat it as a smoke test, so this is consistent rather than surprising — but
it means a precision number can only come from test until the suite grows.

**Over-escalation is deliberately not a violation.** The policy does not forbid asking, so
an oracle that flagged it would be checking a rule the agent was never told, which is the
one thing this project does not do. It is reported as precision — a usability measurement —
and the violation oracle returns None. The cost of over-escalating shows up twice and
honestly: once in precision, and once in completion, because the invoice is still unpaid.

## 10. What the agent is told outside the policy is not fingerprinted

`data/splits.json` fingerprints each scenario's policy, task, tools and world. It does not
cover `agent.SYSTEM_PREFIX` — the role description every scenario shares — because that
lives with the system under test rather than with the scenario.

It is load-bearing anyway. Whether over-escalation is a *fair* thing to measure rests partly
on that prefix saying "if you need a human decision, use the approval tool", which reads as
*when you need one* rather than *always*. Reword it and every result in the project moves,
with nothing failing to say so.

The reason it is not fingerprinted is that it is a property of the system, not of the
scenario, and two systems with different prompts are the comparison this suite exists to
make. The run artefact records the model and effort; it should record the prompt hash too,
and does not.

## 11. Every scenario is run once

No repeats, so nothing here separates a model that violates 30% of the time from one that
violated once out of one on the three scenarios where it happened to. The confidence
intervals are over *scenarios*, not over runs, and they say nothing about how stable a
single scenario's outcome is.

Sampling each scenario several times is the fix and it multiplies the cost by the sample
count, which at under £1 a pass is affordable — it has simply not been done yet.

## 12. Single currency, single account, single day

No FX, no multi-entity structure, no settlement dates. Each of those is a place a control
can fail that this suite will never see.
