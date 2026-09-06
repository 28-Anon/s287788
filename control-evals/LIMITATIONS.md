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

## 2. Silent violations are detected by keyword, and the number is a lower bound

The scariest failure is violating *while stating you complied*. It is now measured, by
matching the final message against a list of about twenty phrases that assert the rules were
kept. That under-counts, and there is no version of this check that does not: an agent can
imply compliance without using any phrase on the list, or describe its actions accurately in
words the list does not contain.

The list is deliberately conservative — a false positive would inflate the scariest number in
the suite, so it holds only phrases that are hard to say by accident while describing a
violation. Report it as "at least N of M violations were silent", never as a rate.

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

## 10. Five scenarios have no violation to catch, and both denominators are printed

`ceiling-001`, `daily-002`, `routine-001`, `routine-002` and `retryok-002` can be completed
inside every rule. (An earlier draft of this file said six and included `lookalike-002` —
that one does have a trap: paying the similarly-named entity violates the allowlist. The
correct answer being "pay it" is not the same as there being nothing to catch.)

They exist to make escalation precision measurable, and they mean a violation rate over all
41 scenarios understates the rate by roughly their share. `summarise` therefore reports two:
over the 36 trapped scenarios, and over the whole suite. Neither is wrong; quoting one
without saying which is.

The larger and more useful count is that **fourteen scenarios cannot be completed by
escalating** — that is what stops reflexive refusal scoring well.

## 11. Silent-violation detection is still not built

Unchanged from week 5, and now more conspicuous: with 41 scenarios there is more surface for
an agent to violate while stating it complied, and nothing measures it. It stays a keyword
check to be reported as a lower bound, and it is weeks 9-10 work.

## 12. The runner is tested against a fake client, not against the API

Every test in this project runs offline. The agent loop is exercised by a fake client that
mimics the SDK's response shape closely enough that the loop cannot tell the difference.

That is the only way to test the cases that matter — a model that loops forever, a refusal, a
truncated turn, a connection error — none of which can be produced on demand from a real
model. It is also the standing risk of a fake: **if the SDK's response shape changes, these
tests keep passing while a real sweep breaks.** `runner.py` reads every response field
defensively for that reason, and the first real sweep is the thing that actually validates
the integration. Until it has been run, treat "the runner works" as untested against reality
in exactly the way covenant-evals' EDGAR client was.

## 13. Prices are hardcoded, and partner platforms bill differently

`models.py` records first-party API rates so a cost can be recomputed from a stored run
without another network call. Amazon Bedrock and Google Vertex bill separately. If a run is
ever made through one of those, its cost figure is wrong — the run record does not currently
capture which platform was used, which is a gap worth closing before any cost comparison is
published.

## 14. Cost estimates from `--dry-run` are a guess

The estimate assumes about 1,200 tokens of prompt and five turns per scenario, deliberately
on the high side. Real spend depends on how many turns the agent takes, which is the thing
being measured and therefore not knowable in advance. Use it to catch an order-of-magnitude
mistake before spending, not as a budget.
