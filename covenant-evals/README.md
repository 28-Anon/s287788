# covenant-evals

A harness for deciding whether an LLM system is fit to answer covenant questions on real
credit agreements — and the labelled dataset to test it against.

**The harness is the product. The system being measured is just the fixture.**

## Status

Week 1 of 26. Skeleton only: schema, validation, budget tracking, CI. No corpus yet, no
items yet, no results yet. See `docs/LIMITATIONS.md` — written before any results exist,
deliberately.

## Quick start

```bash
pip install -e ".[dev]"
python -m pytest -q
python -m covenant_evals.cli --help
```

Installing also creates a `covenant-evals` command, but on Windows pip puts it in a
`Scripts` folder that is not on PATH by default — so the docs use `python -m` (`py -m` in
PowerShell), which never depends on PATH.

Every `make X` below is a shortcut for `covenant-evals X`. The Makefile is a convenience on
Unix; **on Windows use the `covenant-evals` command directly** — there is no `make` there
and nothing in the project needs it.

## The headline metric

**Grounded accuracy** — the answer is correct *and* the citation it gives can be verified
verbatim against the source document. An answer that is right with a fabricated citation
is a failure, not partial credit. A credit committee cannot act on an unsourced number.

Secondary, and all reported: citation validity, citation precision, wrong-when-should-abstain
rate, cost per item, p50/p95 latency, and judge-vs-human agreement (Cohen's κ) wherever an
LLM judge is used.

## Layout

| Path | What lives here |
|---|---|
| `data/corpus/manifest.json` | Accession numbers + hashes of the source agreements. **Not the documents themselves** |
| `data/items/*.yaml` | One labelled question per file, so every change is reviewable in a diff |
| `src/covenant_evals/schema.py` | The item schema and its validation rules |
| `src/covenant_evals/budget.py` | API spend tracking |
| `docs/METHODOLOGY.md` | Labelling protocol, splits, scoring definitions |
| `docs/TAXONOMY.md` | The failure modes, with reproducible examples |
| `docs/LIMITATIONS.md` | What this does not measure |
| `runs/<run_id>/` | Immutable results. Never edited after writing |

## Building the corpus

```bash
covenant-evals corpus build --count 8    # search, fetch, hash, segment, report
covenant-evals corpus review             # keep, drop, governing law, why
```

`build` is the whole mechanical half in one command. `review` is the judgement half.


```bash
cp .env.example .env          # then set EDGAR_USER_AGENT to your name and real email
covenant-evals corpus search --query '"Majority Lenders"'
covenant-evals corpus add 0000950170-24-012345:ex101.htm --cik 320123 --governing-law English
covenant-evals corpus fetch
covenant-evals corpus status
```

`search` finds candidates and downloads nothing. `add` records one document in the manifest.
`fetch` downloads, normalises, hashes and caches. Running `fetch` twice downloads nothing the
second time, and a document whose text no longer matches its recorded hash is reported as a
**conflict** rather than silently overwritten — because any item labelled against it is then
broken and you need to know.

### Reviewing the corpus

```bash
covenant-evals corpus review     # one document at a time, each opened in your browser
covenant-evals corpus report     # runs/corpus.html — the whole corpus at a glance
```

`review` is the judgement pass: keep, drop, record the governing law, say why the document
is in the corpus. It saves after every decision. `report` renders a local HTML page showing
how each document segmented and what still needs attention.

### Finding your way around a document

```bash
covenant-evals corpus sections 0000950170-24-012345 --offsets   # the section tree
make corpus-section  REF=0000950170-24-012345 ADDR='7.02(b)'
make corpus-locate   REF=0000950170-24-012345 Q='not to exceed the greater of'
covenant-evals corpus sections --check                                          # segment everything, report problems
```

`section` and `locate` both print a `gold_span: [start, end]` line ready to paste straight
into an item file — that is the whole point of them. `locate` reports **every** match and
fails if there is more than one, because a citation that appears twice in a document is
ambiguous and the span you record may not be the passage you meant.

Segmentation is heuristic and handles both US (`ARTICLE VII` / `SECTION 7.02`) and English
LMA (`23. NEGATIVE COVENANTS` / `23.1`) numbering. It emits warnings rather than guessing
quietly; `covenant-evals corpus sections --check` runs it across the whole corpus at once.

### Jurisdiction

Where a document was *filed* and which law *governs* it are different facts, and the manifest
records both. EDGAR is a US filing system, but it carries English-law LMA-style facility
agreements too — UK groups with US listings, and US groups borrowing in London, both file
there. The corpus targets at least 5 English-law agreements alongside the New York-law ones,
and results are reported by legal tradition rather than pooled.

Useful searches for English-law documents: `"Majority Lenders"`, `"governed by English law"`,
`"Facility Agreement"` — the LMA house style differs from US drafting in vocabulary
(*Majority Lenders* vs *Required Lenders*), covenant architecture and definition layout.

## Splits

```bash
covenant-evals splits freeze     # once, after the corpus is complete
covenant-evals splits check
covenant-evals splits status     # composition, and whether heldout has ever been opened
```

By document, never by item. Stratified by governing law so the US/English comparison is not
confounded with split difficulty. Frozen and committed: adding a document later is allowed,
moving one between splits is not.

**Heldout is locked.** Reading it requires a written reason and appends to
`runs/heldout-access.log`, which is committed. That log is the evidence that it was opened
once, in week 22, on purpose.

## Labelling

```bash
covenant-evals items new --ref ... --section '7.01(b)' --question '...' \
    --type boolean --gold false --quote '...' --rationale '...' --traps basket_cap
covenant-evals items check      # schema, plus every item against the document it cites
covenant-evals items stats      # the mix: answer types, difficulty, traps, documents
```

You paste a quote; the tool finds the offsets, pins the document hash, and refuses the item
if the quote is ambiguous, absent, or sitting in a different section from the one you cited.

**The protocol is in [docs/LABELLING.md](docs/LABELLING.md)** — read it before the first
session. The short version: label before you look at any system output, no section no item,
one fact per question, and about one item in five should be a question the document does not
answer.

## Data source

Credit agreements are filed publicly as EX-10 exhibits on SEC EDGAR. This repository stores
accession numbers and SHA-256 hashes plus a fetch script, never the filings themselves.

EDGAR requires a `User-Agent` header identifying you with a contact email, and caps requests
at 10/second. Set `EDGAR_USER_AGENT` in your `.env` (see `.env.example`) before fetching.
