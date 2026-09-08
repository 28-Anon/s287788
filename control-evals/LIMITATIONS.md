# Limitations

Written before any results exist, and updated as more appear. It is much harder to be honest
about limitations once there is a number you are pleased with.

## 1. Completion is a weaker measurement than violation

Violation is exact: the policy said £50,000, the trace shows £75,000, and there is nothing to
interpret. Completion is not. Most of these scenarios *cannot* be done within the rules, so
the correct outcome is to escalate or decline — and "declined properly" is a judgement
reduced to a proxy: it moved no money, it investigated first, and it said something.

That proxy has already been wrong twice, both times in the generous direction. It once
accepted any final message, which put a reflexive refuser at the good end of the frontier.
It then accepted an agent that had *paid* and stopped — including one whose forbidden
payment was refused only because the counterparty did not exist in the system. Correcting
the second took a scripted agent's completion rate from 62% to 0%, which is the size of
error this proxy can hide.

Both were found by watching runs rather than by reasoning about the oracle, and there is no
reason to think it is now right — only that it is less wrong. The frontier is precise on one
axis and approximate on the other, and any claim made from it should say so.

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

Forty-nine scenarios written by one author, who chose which pressures to apply and which
failures to look for. Going from ten to forty-nine made this worse in one specific way rather
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
49 scenarios understates the rate by roughly their share. `summarise` therefore reports two:
over the 44 trapped scenarios, and over the whole suite. Neither is wrong; quoting one
without saying which is.

The larger and more useful count is that **seventeen scenarios cannot be completed by
escalating** — that is what stops reflexive refusal scoring well.

## 11. Silent-violation detection was built in weeks 9-10, and is still only a keyword check

This section used to say the detection did not exist. It does now — `report.claims_compliance`
and the count printed by `summarise` — but building it did not remove the limitation, it only
moved it. The residual problem is §2: an agent can imply compliance without using any phrase
in the list, so the number is a lower bound and is never printed as a rate.

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

This is now narrower than it was on one side. The **OpenAI-compatible** path is exercised
over a real socket by `tests/test_http_transport.py` — see §19 — so on that side only the
model is fake, not the transport. The Anthropic SDK path still has no equivalent: the SDK
client is injected as a fake and nothing in this repository has ever spoken to Anthropic.

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

## 15. A sweep stops after three consecutive failures

Three failed calls in a row is a broken setup, not bad luck, and continuing would repeat the
same error across the whole suite and then report every rate as n/a. The sweep stops, prints
the last error, and names the directory holding what it already bought.

The cost of that rule is a real one: a genuine run of bad luck — three transient 529s in a
row on a busy afternoon — also stops the sweep. Restarting is cheap and the partial results
are kept, so the trade is worth it, but a sweep that stopped is not evidence of anything
about the model.

## 16. `--dry-run` proves nothing about the credentials

It sends no request, so it cannot tell you the key is valid, only that one was found. The
first real call is still the first thing that has ever authenticated.

## 17. The scripted agents are not a baseline

`--simulate` runs three hand-written stand-ins. They are for exercising the pipeline and for
showing what the output looks like without spending anything. They are not a baseline, not a
control condition, and not evidence about how any model behaves.

The `careful` one reads the policy object directly to decide whether an amount is over the
limit — something no real agent can do, since a model only sees the rendered prose. It marks
where the good corner of the frontier is; it does not show that reaching it is easy.

Simulated runs are stamped `simulated:<style>` as their model, record `pricing: null`, report
zero cost, and print a banner in both `run` and `report`. If any of those guards is ever
removed, a stored simulated run becomes indistinguishable from a real one.

## 18. Violation oracles count attempts; completion oracles count outcomes

An agent that decided to pay an unapproved supplier and was refused only because that
supplier is not on the books has still decided to pay it. Every amount oracle already
followed that rule; `only_pay_allowlisted`, `must_not_pay_a_rewired_account` and
`must_not_exceed_per_counterparty` did not, because they read successful transfers only.
The oracles disagreed with each other about what a violation is, and the disagreement
understated the violation rate on exactly the categories where the sandbox happens to block
the attempt.

Fixed, and it moved the numbers: over dev + test the reckless stand-in went from 52% to 60%
on the trapped denominator, and 13 silent violations became 15.

The general rule now holds throughout: **violation is a question about the decision, so it
reads attempts; completion is a question about the outcome, so it reads the world.** If a
new oracle is added, that is the question to ask of it.

## 19. The OpenAI-compatible adapter is now tested over a real socket, but not against a real model

This section used to say the adapter was only ever tested against a recorded payload. That
gap is closed: `tests/test_http_transport.py` stands up an actual `http.server` on localhost
and drives the real `http_transport` through it — the wire encoding, the headers, HTTP 400 /
401 / 404 / 429 / 500 / 503, a dead endpoint, the whole runner over a socket, a guardrail over
a socket, and `doctor` against a live server. Nothing is stubbed on the transport path.

What is still fake is the **model**. The server on the other end returns replies this project
wrote, so every mapping is pinned against payloads shaped the way this project expects real
ones to be. Endpoints differ in ways no fake anticipates: some report `finish_reason: "stop"`
while emitting tool calls (handled, because it is common enough to expect), some return
content as parts rather than a string (handled), and some will do something not listed here
(not handled, by definition). `doctor` exists to find that out in one request rather than in
the middle of a sweep — run it first.

## 20. Cost figures for OpenAI-compatible models are zero, and that is a claim about local ones

A local endpoint genuinely costs nothing to call, so zero is right. A hosted one
(OpenRouter, Together, Groq) is not free, and this suite has no way to know its rates — so it
reports zero there too, which is **wrong and silent about being wrong**. Read the provider's
own billing for those. The stored run records the endpoint, so at least you can tell later
which numbers were free.

## 21. "How to pass this scenario" is derived by probing, and the probes are not exhaustive

Each scenario's completion routes come from running eight canonical behaviours against its
own oracle and reporting which ones satisfy it cleanly. That guarantees the advice agrees
with the scoring, which is the property that matters. It does not guarantee the list is
complete: a scenario might be passable in a way no probe imitates, and the reader would never
be told about it. The list is "at least these work", not "only these".

## 22. A model that cannot call tools scores as a perfectly safe agent

This is the failure mode most likely to produce a confidently wrong headline. A small model
that never emits a tool call acts on nothing, so it violates nothing, and the report shows a
0% violation rate next to a low completion rate — which is exactly what a cautious,
well-behaved agent looks like on the frontier.

It is not the same thing at all, and no metric in the report distinguishes them. `doctor`
exists to catch it before a sweep, and any published result should say how many runs made
zero tool calls. Treat a 0% violation rate from a small model as unproven until you have
checked it acted.

## 23. A guardrail changes the agent's trajectory, not just the outcome

The point of separating **violation** (the agent decided to) from **breach** (money actually
moved) is that a control layer should move the second and leave the first alone. It does not
quite. A refused call comes back to the agent as a tool error, and what it does with its
remaining turns is different from what it would have done unrefused. On the reckless
stand-in, `process` moved violation from 60% to 48% — not because the agent became more
careful, but because being blocked early cost it the chance to make its next mistake.

So the two numbers are worth reporting separately and must not be described as independent.
A drop in violation under a guardrail is not evidence that the guardrail improved judgement.

## 24. The guardrail results describe scripted agents, not models

Everything in the guardrail table comes from hand-written stand-ins. It demonstrates that the
control layer works, that the violation/breach split measures what it claims to, and roughly
what shape the trade-off has. It says nothing about how any model behaves under a guardrail,
which is the actual week 18-21 question and needs a real sweep.

## 25. These guardrails are stronger than a real one would be

Each check reads the same `Policy` object the oracle reads, so it knows the limit exactly. A
real deployment's control layer is configured separately from whatever the agent was told,
and the two drift — a limit raised in one place and not the other is a common production
failure this suite cannot see. Treat the breach reduction here as an upper bound.

## 26. Counting attempts breaks down when the attempts are one obligation retried

Violation oracles count attempts, on the principle that an agent which tried to send £75,000
decided to send £75,000. That is right when each attempt is a fresh decision to move money.
It is wrong when the attempts are the *same* obligation retried after an unknown outcome.

`phantom-002` made this concrete. Three attempts at a £17,500 invoice, checking between each,
with only the third actually landing: an amount oracle counting attempts reads £52,500
committed and calls it a breach of a £50,000 daily total. The agent did nothing wrong — it did
exactly what the policy asked — and would have been punished for it.

The scenario therefore pairs `must_verify_before_retrying` with no amount check, and says so
in a comment. The general lesson is that "attempts" and "commitments" are the same thing only
while every attempt succeeds or fails cleanly. Any future oracle combining an amount limit
with a scenario that can produce retries needs to answer this question first.

## 27. The long-run scenarios are shorter than "long run" implies

`longrun-001` and `longrun-002` put five or six invoices between the policy and the payment
that breaks it. That is drift measured in a handful of turns, not the thirty a real deployment
would see, and the runner's default turn cap is twelve.

They test that a rule survives some distance from where it was stated. They do not test what
happens after an hour of unrelated work, which is the case people actually worry about and
which this suite cannot currently reach.
