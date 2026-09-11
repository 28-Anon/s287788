# How this is put together

Read this before the code. It is twelve modules, and the shape is simple once you see it:
**a scenario describes a situation, a runner plays it, and two oracles read what happened.**

```
   scenario                    runner                      oracles
  ┌──────────┐              ┌──────────┐               ┌────────────┐
  │ policy   │─── rendered ─│  agent   │── tool call ──│   world    │
  │ world    │   as prompt  │   loop   │               │ (balances, │
  │ task     │              │          │◄── result ────│  invoices) │
  │ tools    │              └────┬─────┘               └────────────┘
  └──────────┘                   │                            │
                                 │ every call recorded        │
                                 ▼                            ▼
                            ┌─────────┐              violated? completed?
                            │  trace  │──────────────────────►│
                            └─────────┘                       ▼
                                                        report + intervals
```

## The one idea everything else follows from

**Ground truth is defined, not discovered.** You write the policy, so "was a rule broken" is
arithmetic on a record, not a judgement call. Nothing here is labelled by hand and no model
grades anything.

Two consequences worth holding on to:

1. **The trace is what the agent decided. The world is what happened.** They come apart
   whenever a tool lies — a payment gateway that reports an error while the money leaves.
   Violation reads the trace; completion may read the world.
2. **An oracle may only check a rule the agent was told.** If the policy does not forbid
   splitting a payment, an agent that splits one has found a gap in the policy, not broken a
   rule. Testing unstated rules measures whether the model guessed your intent.

## The modules, in the order they matter

| module | what it is |
|---|---|
| `money.py` | Integer pence. Never a float. Everything else depends on this being boring. |
| `policy.py` | The rules, as data. The same object is rendered for the agent and read by the oracle, so a scenario cannot disagree with its own scoring. |
| `world.py` | Balances, counterparties, invoices, a ledger. **It permits violations** — see below. |
| `tools.py` | The tool schemas the agent sees, and the dispatcher that runs them. |
| `trace.py` | Every call and its result. Everything is scored from here. |
| `scenario.py` | Ties the four together and validates the result. |
| `oracles.py` | Reusable checks. Each returns *why* a rule was broken, not just that it was. |
| `scenarios/` | The 49 scenarios themselves, grouped by what they test. |
| `runner.py` | The agent loop. The client is injected, which is why every test runs offline. |
| `guardrails.py` | An optional hard control between the agent and the world. |
| `report.py` | The frontier, and bootstrap intervals clustered by family. |
| `splits.py` | dev / test / heldout, and the lock on heldout. |

Support: `models.py` (per-model request shapes), `budget.py` (cost), `store.py` (stored runs),
`openai_compat.py` + `shapes.py` (non-Anthropic endpoints), `doctor.py` (endpoint checks),
`explain.py` (why each result came out as it did), `simulate.py` (scripted stand-in agents),
`env.py` (finding the API key), `cli.py` (the commands).

## Four decisions that look wrong until you know why

**The world lets violations through.** A £75,000 transfer under a £50,000 policy *succeeds*.
If the tool refused, every scenario would pass and you would be measuring the sandbox's
guardrails instead of the agent's judgement. A real deployment should enforce limits at the
system level too — this measures the layer above it. `guardrails.py` is where you add that
enforcement back, deliberately, to find out how much it was carrying.

**The system prompt is the policy and one sentence of framing.** No "be careful with money",
no "when in doubt, ask". Advice in the prompt moves what is being measured from the model to
the harness.

**Violation counts attempts; completion counts outcomes.** An agent stopped by the sandbox
still decided to act. (One exception, documented in `LIMITATIONS.md`: attempts and
commitments are the same thing only while each attempt is a fresh decision, which retries
after an unknown outcome are not.)

**Confidence intervals resample scenario *families*, not runs.** `limit-001` and `limit-002`
share a policy, a world and an invoice — they are not two independent observations. A
bootstrap over runs would report an interval narrower than the evidence supports.

## The lifecycle of one run

1. `splits.select()` hands out the scenarios for a split. Heldout refuses without a written
   reason and appends to a committed log.
2. `runner.run_scenario()` builds the system prompt from `policy.render(tools)`, sends the
   task, and loops: the model calls a tool, `guardrails` may refuse it, `tools.dispatch()`
   runs it against the world, the result goes back.
3. When the model stops, the scenario's two oracles read the trace and the world.
4. `report.summarise()` turns many runs into rates with intervals; `store.RunSet` writes
   enough to recompute every metric later without paying for the run again.

## Where to look first

- **To understand what is tested** — `scenarios/payments.py`, then `scenarios/harder.py`.
- **To understand the scoring** — `oracles.py`, top to bottom.
- **To understand the caveats** — `LIMITATIONS.md`. It is long on purpose.
- **To add something** — `CONTRIBUTING.md`.
