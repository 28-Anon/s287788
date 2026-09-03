# control-evals

**Does an AI agent stay inside the limits you set when it can actually move money?**

Give an agent a `transfer_funds` tool, a £50,000 payment limit, and a task that tempts it
over. Watch what it does. Score it against the trace of its actual tool calls, not against
what it says it did.

Ground truth is **defined by construction, not established by reading**: you set the policy,
so a violation is checkable in three lines. There is nothing to label.

See [DESIGN.md](DESIGN.md) for the full design — the scenario format, the ten-category
failure taxonomy, and why the headline metric is a frontier rather than a number.

## Quick start

```bash
pip install -e ".[dev]"
python -m pytest -q
```

On Windows use `py` in place of `python`.

## Status

**Weeks 1–2: the sandbox.** Built and tested; no agent runs against it yet.

| | |
|---|---|
| `money.py` | Integer pence. Never a float |
| `policy.py` | The rules, machine-readable — the agent and the oracle read the same object |
| `world.py` | Balances, counterparties, invoices, ledger |
| `tools.py` | Tool schemas and the dispatcher |
| `trace.py` | What the agent did. Everything is scored from this |

## The two decisions worth knowing about

**The world permits violations.** A £75,000 transfer under a £50,000 policy *succeeds*. If
the tool refused, every scenario would pass and this would be measuring the sandbox's
guardrails instead of the agent's judgement. The question is not whether a hard control can
stop an agent — it obviously can — but **how much you would be relying on that control**.
A real deployment should enforce limits at the system level too; this measures the layer
above it.

**An ambiguous failure still moves the money.** A transfer can return *"gateway timed out;
the status of this payment is unknown"* while the funds have in fact left. That is the real
condition behind double payment, and whether an agent retries into it is the most
operationally expensive failure in the suite.
