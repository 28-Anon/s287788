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

## 6. Single currency, single account, single day

No FX, no multi-entity structure, no settlement dates. Each of those is a place a control
can fail that this suite will never see.
