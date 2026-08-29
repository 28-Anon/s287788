# Failure taxonomy

The catalogue of ways systems fail on these documents. **This is the most valuable output of
the project** — anyone can publish a scoreboard; almost nobody publishes a careful account
of *how* a class of system fails and how often.

Empty until week 12, when the first error analysis runs. Eight to twelve entries at the end
is a strong result. Two means you did not look hard enough; thirty means the categories are
too fine and should be merged.

## Entry format

Every entry has all five fields. An entry without a reproducible example is an opinion, not
a finding.

### `trap_name` — one-line description

**What happens.** Two or three sentences on the mechanism, not the symptom.

**Example.** Item `cov-NNNN`, run `<run_id>`. The question, the gold answer, what the system
said instead, and the citation it gave.

**Frequency.** How often across the test split, with a confidence interval.

**Fixable?** Whether prompting, retrieval or scaffolding removes it, or whether it is
structural. Say which you tried.

**Why it matters.** What would go wrong if this reached a real credit decision.
