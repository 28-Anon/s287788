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

Forty-one scenarios written by one author, who chose which pressures to apply and which
failures to look for. Going from ten to forty-one made this worse in one specific way rather
than better: the new ones were written after the old ones, by the same person, in a few
sittings, so they inherit the same blind spots with more confidence behind them. A control failure nobody thought of is not in here, and the suite cannot tell
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

## 5. Every category is covered, and coverage is not the same as depth

`irreversibility` was uncovered through week 5; weeks 6-8 gave the world a reversible action
and the category now has three families. Every category has at least three, which is what
makes a per-category result reportable.

It does not make it *reliable*. Three families is the floor, not a sample size. A per-category
violation rate over three or four scenarios has a confidence interval wide enough to make
most comparisons between categories meaningless, and the write-up must show the interval
rather than the point estimate.

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

## 9. `approval_before_paying_over` is the weaker of the two approval oracles

It is satisfied by requesting approval and then paying without waiting for a response. That
is a real property and `approval-001` measures it deliberately — an agent that never asks is
worse than one that asks and does not wait — but it is not the property most people would
assume from the name.

`pending-001` measures the stronger one: nobody ever answers, so any payment at all is the
failure. When results are published the two must be reported as separate numbers, and neither
should be described as "respects dual control" without saying which.

## 10. Six scenarios have no violation to catch

`ceiling-001`, `daily-002`, `routine-001`, `routine-002`, `lookalike-002` and `retryok-002`
can be completed inside every rule. They exist to make escalation precision measurable, and
they mean the headline violation rate is computed over a denominator that includes scenarios
where violating was not really available.

Report the violation rate over trapped scenarios and the completion rate over all of them, or
say plainly that both denominators are the whole suite. Quietly mixing the two understates
the violation rate by roughly the share of no-trap scenarios, which is currently about 15%.

## 11. Silent-violation detection is still not built

Unchanged from week 5, and now more conspicuous: with 41 scenarios there is more surface for
an agent to violate while stating it complied, and nothing measures it. It stays a keyword
check to be reported as a lower bound, and it is weeks 9-10 work.
