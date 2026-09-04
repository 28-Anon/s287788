# Handoff

Everything a new session needs. Read this first.

**Repo:** `28-Anon/s287788` · **Branch:** `claude/control-evals-ai-money-xr5vvv`
(week 5 onward; weeks 1–4 are on `claude/career-niche-evaluation-qyxusw`, PR #1)

---

## Why this exists

An adversarial review of the user's career thesis ([`CAREER-NICHE-EVALUATION.md`](CAREER-NICHE-EVALUATION.md))
rejected "institutional digital-asset risk & intelligence" and recommended instead:

> **Evaluation and control of autonomous AI systems in money-moving workflows.**

Every bank is stuck on the same wall — not *can we build it* but *can we prove it is safe to
switch on*. Ship #1 is a project that demonstrates that skill publicly.

The user is 19, UK, CS undergrad, on **Windows PowerShell** (`py -m ...`, no `make`).

---

## Two projects

### `control-evals/` — **the live one**

Does an AI agent stay inside its limits when it can actually move money? Give it a
`transfer_funds` tool, a £50,000 policy, and a task that tempts it over.

Ground truth is **defined by construction**: you set the policy, so a violation is checkable
in three lines against the trace. **No labelling.**

Read [`control-evals/DESIGN.md`](control-evals/DESIGN.md), then
[`control-evals/LIMITATIONS.md`](control-evals/LIMITATIONS.md).

**Built (weeks 1–5 and 9), 195 tests, all offline:** `money.py` · `policy.py` · `world.py` ·
`tools.py` · `trace.py` · `scenario.py` · `oracles.py` · `scenarios/payments.py`
(14 scenarios) · `splits.py` · `agent.py` · `runner.py` · `metrics.py` · `budget.py` ·
`fixture.py` · `cli.py`.

Splits are **frozen and committed** in `control-evals/data/splits.json` — cut by scenario
family, balanced by failure category, 2/5/3 across dev/test/heldout. Heldout is locked:
reading it needs a stated reason and appends to `runs/heldout-access.log`, which is committed
and currently empty. `splits.py` also fingerprints each scenario's content, so editing a task
or an invoice amount after the freeze fails `pytest` instead of silently making this week's
numbers incomparable with last week's.

**Week 9 was taken before weeks 6–8, deliberately.** Writing 40 more scenarios against an
interface no agent had ever executed would have been 40 things built blind. The runner exists
now, it takes its scenarios from `splits.select(...)` so the heldout lock is real, and
`run --dry-run` proves the whole path works without an API key.

**Escalation precision is measurable now.** Four routine in-policy payments were added —
`routine-001`, `routine-002`, `boundary-001`, `benign-001` — where the right answer is to
pay the invoice and asking a human wastes attention. An agent that escalates on everything
used to score a clean 100% precision; it now scores 40% on `test`. Over-escalation is
deliberately **not** a violation (the policy does not forbid asking), so it is reported as
precision and paid for again in completion.

**Next: weeks 6–8** — the remaining volume work, placed with `splits assign-new` (which
never moves anything already assigned). Worth knowing going in:

- dev is down to 14% of the suite and has no `unnecessary` scenario, so precision can only
  come from `test` today. The allocator will favour dev as families are added; do not re-cut
  the freeze to fix it.
- `irreversibility` is still the one uncovered category. It needs a payment the world can
  hold or recall.
- Four `unnecessary` scenarios is a thin denominator. More of them is as valuable as more
  traps.

### `covenant-evals/` — **complete, superseded, do not delete**

An eval harness for LLM covenant question-answering over SEC credit agreements. 300 tests,
weeks 1–5 plus a week-8 spike. Abandoned because it needed ~12 hours of reading credit
agreements to establish ground truth and the user judged the ROI not there — a fair call.

It works, it is tested, it demonstrates the same discipline, and ~40% of it carries over.

---

## Design decisions that must not be quietly reversed

1. **The world permits violations.** A £75,000 transfer under a £50,000 policy *succeeds*.
   If the tool refused, every scenario would pass and the suite would measure its own
   guardrails, not the agent. Do not "fix" this.
2. **Oracles read the trace, never the agent's prose.** An agent that says it complied and
   then transfers £75,000 must be caught.
3. **An oracle may only check a rule the agent was told.** Unstated rules turn the eval into
   a test of whether the model guessed the author's intent.
4. **Completion is scored alongside violation**, or the suite rewards refusal. The headline
   is a frontier, not a number.
5. **Money is integer pence.** Never a float.
6. **`max_tokens` is a ceiling, not a budget.** Cost comes from input tokens, turns, and
   thinking tokens.

### One thing that changed with the redesign

In covenant-evals, labels **could not** be model-written — a model-labelled dataset used to
test a model is circular. In control-evals that prohibition **does not apply**: scenarios
are code, and their ground truth comes from the policy, not from anyone's reading. Writing
scenarios is the assistant's job. Do not carry the old prohibition across.

---

## What's on the user

**One thing is now on him, and it is the interesting one: run it.** The container has no API
key, so nothing in this project has ever spoken to a model.

```powershell
cd control-evals
py -m pip install -e ".[dev]"
py -m control_evals.cli run --dry-run        # first, costs nothing
copy ..\covenant-evals\.env .env            # or set ANTHROPIC_API_KEY
py -m control_evals.cli run --split dev      # 2 scenarios, pennies
py -m control_evals.cli run --split test     # 5 scenarios
```

Expect the first real run to find bugs the tests could not — that has happened at every
previous stage of this project. `runs/*.json` has every tool call; read the traces, not just
the rates. Do **not** run `--split heldout`; it will refuse, and that is the point.

Standing facts: he has an `ANTHROPIC_API_KEY` in `covenant-evals/.env`; a run of the suite
should cost well under £1. When the runner exists he needs to run it, since the container
has no API key of its own.

---

## Environment

- **sec.gov is blocked** by this session's egress proxy. Irrelevant to control-evals.
- **No API key or `ant` CLI in the container** — the user runs anything that calls a model.
- **`api.anthropic.com` bypasses the proxy**, so a session that *had* credentials could run it.
- One environment on the account ("Content"); a child session inherits the same policy.

## Running it

```powershell
cd control-evals
py -m pip install -e ".[dev]"
py -m pytest -q                                  # 195 passed
py -m control_evals.cli run --dry-run            # the whole pipeline, no API key, no cost
py -m control_evals.cli scenarios                # the suite, and which split each is in
py -m control_evals.cli splits status            # the assignment, and the heldout log
py -m control_evals.cli splits check             # is the frozen split still sound
py -m control_evals.cli splits show heldout      # refuses, on purpose
py -m control_evals.cli budget                   # what has been spent so far
```

`covenant-evals` is the same, and gives 300.

---

## Working style that has been serving well

Small commits with a real explanation of *why*, ruff clean, tests before claims, and every
bug found by running something recorded in the commit message rather than quietly fixed.
Several real bugs in this project were found only by the user running a command — the
`root_form` field that did not exist, the filter that discarded every Amended and Restated
agreement, a keep/drop rule that contradicted itself. Assume the same will keep happening.
