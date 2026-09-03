# Handoff

Everything a new session needs. Read this first.

**Repo:** `28-Anon/s287788` · **Branch:** `claude/career-niche-evaluation-qyxusw` · **PR:** #1

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

**Built (weeks 1–4), 56 tests:** `money.py` · `policy.py` · `world.py` · `tools.py` ·
`trace.py` · `scenario.py` · `oracles.py` · `scenarios/payments.py` (10 scenarios).

**Next: week 5** — port `splits.py` and the heldout lock from covenant-evals. Then week 9,
the runner, where an agent finally runs.

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

Nothing is currently blocked on him. Weeks 5 and 9 are assistant work.

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
py -m pytest -q          # 56 passed
```

`covenant-evals` is the same, and gives 300.

---

## Working style that has been serving well

Small commits with a real explanation of *why*, ruff clean, tests before claims, and every
bug found by running something recorded in the commit message rather than quietly fixed.
Several real bugs in this project were found only by the user running a command — the
`root_form` field that did not exist, the filter that discarded every Amended and Restated
agreement, a keep/drop rule that contradicted itself. Assume the same will keep happening.
