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
uv sync                      # or: pip install -e ".[dev]"
make test                    # run the test suite
make validate                # validate every item file against the schema
make budget                  # what this project has cost so far
```

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
cp .env.example .env          # then set EDGAR_USER_AGENT to your name and real email
make corpus-search Q='"Majority Lenders"'
make corpus-add REF=0000950170-24-012345:ex101.htm CIK=320123 LAW=English
make corpus-fetch
make corpus-status
```

`search` finds candidates and downloads nothing. `add` records one document in the manifest.
`fetch` downloads, normalises, hashes and caches. Running `fetch` twice downloads nothing the
second time, and a document whose text no longer matches its recorded hash is reported as a
**conflict** rather than silently overwritten — because any item labelled against it is then
broken and you need to know.

### Jurisdiction

Where a document was *filed* and which law *governs* it are different facts, and the manifest
records both. EDGAR is a US filing system, but it carries English-law LMA-style facility
agreements too — UK groups with US listings, and US groups borrowing in London, both file
there. The corpus targets at least 5 English-law agreements alongside the New York-law ones,
and results are reported by legal tradition rather than pooled.

Useful searches for English-law documents: `"Majority Lenders"`, `"governed by English law"`,
`"Facility Agreement"` — the LMA house style differs from US drafting in vocabulary
(*Majority Lenders* vs *Required Lenders*), covenant architecture and definition layout.

## Data source

Credit agreements are filed publicly as EX-10 exhibits on SEC EDGAR. This repository stores
accession numbers and SHA-256 hashes plus a fetch script, never the filings themselves.

EDGAR requires a `User-Agent` header identifying you with a contact email, and caps requests
at 10/second. Set `EDGAR_USER_AGENT` in your `.env` (see `.env.example`) before fetching.
