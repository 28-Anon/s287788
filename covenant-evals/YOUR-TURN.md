# What's on you

Everything the tooling cannot do, in the order it blocks you. Updated as weeks land.

Weeks 1–3 built the plumbing. Weeks 4–5 built the labelling and split tooling. **Nothing
past this point can run until you do the first three items below**, because there is no
corpus yet — the repository has zero documents in it.

---

## Blocking, in order

### 1. Set your EDGAR identity — 2 minutes

```bash
cp .env.example .env
```

Then edit `.env` and set `EDGAR_USER_AGENT` to **your real name and a real email**:

```
EDGAR_USER_AGENT="Salah Missana your.email@example.com"
```

The SEC requires this header. A missing or generic one returns 403 and blocks your IP for
about ten minutes. The code refuses to make a request without a plausible one, so this is
the first hard gate.

### 2. Confirm the EDGAR pipeline actually works — 30 seconds

```bash
make corpus-doctor
```

**This is the one thing I could not do for you.** sec.gov is unreachable from the machine
this was built on, so every endpoint shape in `corpus/edgar.py` came from EDGAR's
documentation rather than from a live response.

The doctor makes four requests and checks one assumption at a time: the search endpoint
answers, the envelope is `hits.hits`, `_id` is `accession:filename`, `_source` carries the
five fields the parser reads, the parser produces usable hits, the filing index lists
documents, one document downloads, and the segmenter finds sections in it.

On any mismatch it prints **what it actually found** — "missing ['adsh']; present:
['accession', 'ciks']" — and which function to change. If something differs:

```bash
make corpus-doctor PASTE=1
```

and send me the block it prints. It contains field names and one accession number, no
document text.

When it passes, delete this section: the caveat is discharged.

### 3. Build the corpus — 25 documents, a few hours spread over a week

```bash
make corpus-add REF=<accession:filename> CIK=<cik> LAW=NY NOTE='sponsor-backed leveraged loan'
make corpus-fetch
make corpus-check      # segment everything, read the warnings
```

The mix that matters:

- **25 documents** total
- **at least 5 English-law** (search `"Majority Lenders"` or `"governed by English law"`) —
  these are what make the London story work
- at least **4 with later amendments** (needed for week 20)
- include **two you find genuinely confusing**; they produce the best items

Read every warning `corpus-check` prints. The segmenter is heuristic and it will get some
document wrong — better to find that now than in week 12.

### 4. Write the items — this is the project

Read **`docs/LABELLING.md`** first, properly, once.

| Week | Target | Roughly |
|---|---:|---|
| 4 | 25 items | 5 hours |
| 5 | 60 items total | +7 hours |
| 6 | 90 items | +6 hours |
| 7 | 110 items | +4 hours |

I did not write these and you should not let me or any other model write them. Model-written
answers make the dataset circular. Model-written *questions* are subtler and worse: models
ask what models find natural, which systematically selects against the items worth having,
while the corpus still looks fine from outside.

```bash
covenant-evals items new --ref ... --section '7.01(b)' --question '...' \
  --type boolean --gold false --quote '...' --rationale '...' --traps basket_cap
make items-check     # before every commit
make items-stats     # is the mix right?
```

### 5. Freeze the splits — 5 minutes, once, in week 5

Do this **after** the corpus is complete and **before** you have run anything against it.

```bash
make splits-freeze
git add data/splits.json && git commit -m "Freeze dev/test/heldout split"
```

Then do not open heldout until week 22. The code will stop you by accident; only you can
stop yourself on purpose.

---

## Standing rules

- **`make items-check` before every commit.** It re-verifies every item against its
  document — hash, section, citation offsets, and whether the quote is in the section you
  cited.
- **Every four weeks, relabel 30 items blind.** Your self-agreement is the ceiling on every
  number this project will report. Put it in the README.
- **Track spend from the start.** `make budget`. The dev loop belongs on Haiku; Opus is for
  graded runs only.
- **Never label an item after seeing a system's answer to it.** One contaminated item is a
  footnote. The habit invalidates the set.

---

## Decisions only you can make

Nothing is blocked on these today, but they are yours, not mine:

- **Whether to publish under your own name.** The reputational value of this work depends
  on it being attached to you. That is a real decision with real downsides, and it is early
  enough to think about it deliberately.
- **Which 25 documents.** Corpus selection is the single biggest source of bias in the
  results, and `docs/LIMITATIONS.md` says so. Choose deliberately and write down why in each
  agreement's `note` field.
- **Whether to keep going.** Do §4 for one hour before deciding. Three items, timed
  honestly, multiplied by 250 is the real cost of this project. Better to know now.
