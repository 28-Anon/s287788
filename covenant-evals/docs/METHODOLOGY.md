# Methodology

## The schema

**Frozen in week 4 at SCHEMA_VERSION 1.** The fields, their types and their rules are in
`src/covenant_evals/schema.py`; `tests/test_schema.py::test_the_schema_is_frozen` fails on
any silent change to the field set.

Three fields were added at the freeze, each because the schema as drafted could not express
something the corpus needs:

- **`unit`**, required for numeric answers. "35000000" is unscoreable without knowing
  whether it is dollars, a percentage of EBITDA, or a ratio.
- **`enum_options`**, required for enum answers. Without a closed set to choose from, an
  enum is free text with a label on it.
- **`dispute_note`**, required when `review_status: disputed`. Disputed items are excluded
  from headline scores rather than deleted, because a question that turned out to be
  arguable is a finding about the document, not a mistake to hide.

To change any of this, follow the protocol at the top of `schema.py`. It exists because a
five-minute edit can otherwise cost weeks of labelling.

### Two levels of checking

`items check` runs both:

1. **Schema** — the item against itself. Types match, vocabularies are respected, an
   abstain item has nothing to cite.
2. **Corpus** — the item against the document it cites. The hash still matches, the section
   still resolves, the quote is verbatim at those offsets, and the quote sits **inside** the
   section the item claims. That last one catches the perfect-looking item that quotes the
   right sentence from the wrong clause.

CI runs level 1 on every push. Level 2 needs the cache on disk, so run it locally before
committing labels — `make items-check`.

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

Frozen in week 5 and committed as `data/splits.json`. Assignment is **by document, never by
item**: two questions about the same clause, one in dev and one in test, are not independent
— tune against the first and you have tuned against the second.

| Split | Target share of text | Use |
|---|---:|---|
| `dev` | 16% | Iterate freely. Look at individual items constantly |
| `test` | 56% | Graded runs. Look at aggregates only |
| `heldout` | 28% | Opened once, in week 22 |

**Stratified by governing law.** If dev were all New York-law and heldout all English-law, a
drop between them would be indistinguishable from the split simply being harder — and the
English-law comparison is one of the results this project exists to produce.

Assignment is greedy on `char_count` rather than item count, because at freeze time most
documents have no items yet. It is deterministic given the seed, which is recorded, so the
whole assignment can be reproduced from the manifest.

**Adding is allowed; moving is not.** Documents fetched after the freeze are placed by
`splits assign-new`, which never disturbs an existing assignment. `splits freeze` refuses to
run a second time. `splits check` catches unassigned documents, documents that left the
corpus, and the manifest disagreeing with `splits.json` (which is authoritative).

### The heldout lock

Discipline will not hold for seventeen weeks, so the lock is mechanical. Every read of the
heldout split goes through `splits.require_open`, which:

- passes `dev` and `test` through silently;
- refuses `heldout` outright unless given a reason of at least ten characters — a
  one-word reason is how a lock gets defeated by accident;
- appends every access to `runs/heldout-access.log`, which is **committed**.

That log is the artefact. When the results are published, it is the evidence that the
heldout split was opened once, in week 22, deliberately. Nobody else publishes that, and it
is worth more to a careful reader than a high score.

The week 8 runner must call `require_open` before evaluating anything. It is already wired
into `items export`, so it is live and tested rather than a promise.

### Export never carries gold

`items export` emits `id`, `doc`, `section`, `question`, `answer_type` — and nothing else.
The system under test never receives the answer, the citation or the rationale, and the
export path is structurally incapable of emitting them. Scoring reads the item files
directly instead.

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

**Bootstrap by resampling documents, not items.** Items from one agreement are not
independent: they share a text, a drafting style, a definitions section and one author's
habits. Resampling items treats twelve questions about document 4 as twelve observations
when they are closer to one, which produces intervals that are far too narrow. For any
claim about credit agreements rather than about these particular ones, the effective sample
size is nearer the document count than the item count. See
[CORPUS-DESIGN.md](CORPUS-DESIGN.md) §6.

## The judge

<!-- Week 15. Fill in with per-answer-type Cohen's kappa between the judge and hand-scoring
     of 60 stratified items. If kappa < 0.6 for a category, the judge is not fit for it —
     record that and fall back to programmatic scoring for that category. -->

## Open decisions

- **Week 7: citations vs structured outputs.** The API's native citation mode and its
  structured-output format are mutually exclusive. Decide empirically which gives better
  citation verification, and record the evidence here.
- **Week 8: does prompt caching survive the batch API?** Measure; do not assume.
