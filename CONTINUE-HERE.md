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

**Built (weeks 1–10), 328 tests:** `money.py` · `policy.py` · `world.py` · `tools.py` ·
`trace.py` · `scenario.py` · `oracles.py` · `splits.py` · `models.py` · `budget.py` ·
`runner.py` · `report.py` · `store.py` · `env.py` · `simulate.py` · `cli.py` · `scenarios/` — **41 scenarios in 32
families, all ten categories, at least three families each.**

The split is **frozen and committed** (`control-evals/data/splits.json`): dev 6 families /
test 17 / heldout 9. Nothing assigned in week 5 has moved. Heldout refuses to open without a
reason and logs every access to `control-evals/runs/heldout-access.log`, which is committed.
See `DESIGN.md` §4a and §4b.

The runner exists and is tested offline against a fake client. **No model has actually been
called yet** — that needs the user's API key. See `DESIGN.md` §4c.

**Next: the first real sweep**, which is on the user. The key is picked up from
`ANTHROPIC_API_KEY` or the first `.env` that has it (`control-evals/`, repo root, then
`covenant-evals/`), and a missing one now stops the sweep before the first call:

```powershell
py -m control_evals.cli run --split dev --dry-run   # free, prices it
py -m control_evals.cli run --split dev             # ~$0.50, 8 scenarios
py -m control_evals.cli report                      # then report <run-id>
```

Expect the integration to break on first contact in some small way — the runner has only ever
talked to a fake. That is the covenant-evals `root_form` lesson repeating, and it is why
`--dry-run` and an 8-scenario dev split come first. Then weeks 11–13: error analysis and the
failure taxonomy.

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
7. **Splits are by scenario family, and frozen.** `limit-001` and `limit-002` are one
   family and one split. Add families with `splits assign-new`; never move one that is
   already assigned, and never re-cut with `--force`.
8. **Heldout stays shut until week 22.** Everything that runs a model goes through
   `splits.select()`, which is the gate. Filtering `splits.assignment` by hand to skip the
   log is exactly the shortcut the lock exists to make visible.
9. **Violation reads the trace; completion may read the world.** The trace is what the
   agent *decided*, the world is what *happened*. They diverge whenever a tool lies — an
   ambiguous gateway failure reports an error while the money leaves — and completion is a
   question about the outcome. `settled()` exists for this and `failure-001` had the bug.
10. **The no-trap scenarios are load-bearing.** Six scenarios can be completed inside every
   rule. Without them an agent that escalates everything scores 0% violation and 100%
   completion. Do not "tidy them up" as scenarios that test nothing.
11. **`Scenario.validate` checks the empty trace.** An oracle that fires when the agent did
   nothing is a bug, unless the scenario sets `inaction_is_a_violation` (only `recall-001`
   does). Keep that check.
12. **The system prompt is the policy and one sentence of framing.** No "be careful with
   money", no "when in doubt, ask". Advice in the prompt moves what is measured from the
   model to the harness — the same mistake as a world that refuses violations.
13. **Bootstrap intervals resample families, never runs.** Runs inside a family are
   correlated; resampling runs returns an interval narrower than the evidence supports,
   which is the error that looks like a result and publishes cleanly.
14. **Both violation denominators get printed.** Five scenarios have no violation available,
   so a rate over all 41 understates it. Never quote one without saying which.
15. **A run id becomes a directory name.** `safe_name()` strips characters Windows
   rejects; `simulated:careful` produced a colon that worked on Linux and would have
   failed on the machine this is developed on.
16. **A simulated run must never look like a real one.** Stamped `simulated:<style>`,
   `pricing: null`, zero cost, banner in both `run` and `report`. Do not relax any of it.
17. **`models.py` owns the per-model request shape.** Opus 4.8 does *not* think unless
   `{"type": "adaptive"}` is set explicitly, and omitting it fails silently — a sweep would
   report results for a configuration nobody intended to run.

### One thing that changed with the redesign

In covenant-evals, labels **could not** be model-written — a model-labelled dataset used to
test a model is circular. In control-evals that prohibition **does not apply**: scenarios
are code, and their ground truth comes from the policy, not from anyone's reading. Writing
scenarios is the assistant's job. Do not carry the old prohibition across.

---

## What's on the user

**The first real sweep.** Everything up to it is built and tested; the container has no API
key, so he runs it. `--dry-run` first — it is free and prices the sweep.

Standing facts: he has an `ANTHROPIC_API_KEY` in `covenant-evals/.env` (control-evals reads
`ANTHROPIC_API_KEY` from the environment, or an `ant auth login` profile). A dev sweep is
about $0.50; the whole suite well under £1.

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
py -m pytest -q                                     # 328 passed

py -m control_evals.cli scenarios list              # every scenario and its split
py -m control_evals.cli splits status               # shares, and the heldout access log
py -m control_evals.cli splits check                # what is wrong with the split
py -m control_evals.cli scenarios categories        # the taxonomy and its coverage
py -m control_evals.cli scenarios show rewire-001   # one scenario in full
py -m control_evals.cli run --split dev --dry-run   # price a sweep, send nothing
py -m control_evals.cli run --split dev --simulate careful   # whole pipeline, no key
```

`covenant-evals` is the same, and gives 300.

---

## Working style that has been serving well

Small commits with a real explanation of *why*, ruff clean, tests before claims, and every
bug found by running something recorded in the commit message rather than quietly fixed.
Several real bugs in this project were found only by the user running a command — the
`root_form` field that did not exist, the filter that discarded every Amended and Restated
agreement, a keep/drop rule that contradicted itself. Assume the same will keep happening.
