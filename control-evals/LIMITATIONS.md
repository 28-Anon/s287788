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

## 2. Silent violations are not yet detected

The scariest failure is violating *while stating you complied*, and it is not measured yet.
The intended check is keyword-based, which will under-count — an agent can imply compliance
without using any of the phrases looked for. It will be reported as a lower bound and never
as a rate.

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

## 9. Single currency, single account, single day

No FX, no multi-entity structure, no settlement dates. Each of those is a place a control
can fail that this suite will never see.
