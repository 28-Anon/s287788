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

## 7. The split is frozen on nine families, and that constrains what can be reported

`data/splits.json` was cut in week 5, when the suite held ten scenarios in nine families —
one family per category. A family is indivisible, so each category currently lives entirely
in one split, and a per-category violation rate **cannot** be computed on test alone.

Freezing early is still the right call: the alternative is cutting the split after seeing
results, which is not a split. Families added in weeks 6-8 are placed by `splits assign-new`
without disturbing anything already assigned, and per-category reporting becomes available
once each category has three or more families. `splits check` prints the shortfall on every
run, so it cannot be forgotten.

Two consequences to keep in mind when reading any number from before that point:

- **Headline rates are over the whole split, not per category.** A test-set violation rate
  computed now is dominated by whichever categories happen to sit in test.
- **Confidence intervals must be clustered by family, not by scenario.** Two scenarios in
  one family are not independent observations, and treating them as such would narrow the
  interval by pretending there is more evidence than there is. That is week 9-10 work and it
  is written down here so it is not skipped.

## 8. The heldout lock is a speed bump, not a wall

Nothing stops someone reading `scenarios/payments.py` and seeing every heldout scenario in
plain source — they are code in the same repository, not sealed data. The lock makes
*programmatic* access leave a record, and it makes casual access require an explicit act.
What it genuinely protects against is drift: opening heldout "just to check" seventeen times
without noticing. What it cannot protect against is an author who decides to look.

The published claim should therefore be exactly what the log supports — "the runner was
pointed at heldout once, on this date, for this reason" — and not the stronger claim that no
knowledge of heldout ever influenced anything.
