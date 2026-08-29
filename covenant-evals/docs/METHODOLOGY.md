# Methodology

## Labelling protocol

1. Read the clause before writing the question. Questions invented without reading produce
   items whose answers are not actually in the document.
2. Record the section. **No section, no item.**
3. Write the gold answer, the verbatim citation, and the character span, *before* running
   any system on the question.
4. Mark the traps that make the item hard, using only the vocabulary in
   `src/covenant_evals/schema.py`. Add new traps there first.
5. Set `review_status: single` on first pass. Promote to `double_checked` only after
   re-reading on a different day.
6. Every four weeks, relabel 30 random items blind and record self-agreement. That number
   is the ceiling on every score this project reports, and it goes in the README.

## Splits

Frozen in week 5, by **document** not by item — every item from one agreement lives in one
split, or answers leak between splits.

| Split | Target size | Use |
|---|---:|---|
| `dev` | ~40 | Iterate freely. Look at individual items constantly |
| `test` | ~140 | Graded runs. Look at aggregates only |
| `heldout` | ~70 | Opened once, in week 22. Not before |

## Scoring

**Grounded accuracy (headline).** The answer matches gold *and* the citation the system
returned appears verbatim in the source document *and* overlaps the gold span. All three, or
it does not count.

**Citation validity.** Does the quoted span exist verbatim in the source at all — separate
from whether it is the right one. Distinguishes fabrication from misdirection.

**Citation precision.** Overlap between returned span and gold span.

**Wrong-when-should-abstain.** On `answer_type: abstain` items, the share where the system
gave a confident answer instead of declining. Reported separately and never averaged into
accuracy: in regulated use a confident wrong answer is worse than no answer.

**Cost and latency.** Dollars per item, p50 and p95 latency, on every run.

All rates are reported with bootstrap 95% confidence intervals. With n=140, an interval is
roughly ±8 percentage points — publishing a bare "84.2%" without that is a leaderboard, not
an evaluation.

## The judge

<!-- Week 15. Fill in with per-answer-type Cohen's kappa between the judge and hand-scoring
     of 60 stratified items. If kappa < 0.6 for a category, the judge is not fit for it —
     record that and fall back to programmatic scoring for that category. -->

## Open decisions

- **Week 7: citations vs structured outputs.** The API's native citation mode and its
  structured-output format are mutually exclusive. Decide empirically which gives better
  citation verification, and record the evidence here.
- **Week 8: does prompt caching survive the batch API?** Measure; do not assume.
