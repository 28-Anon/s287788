# What's on you

Everything the tooling cannot do, in the order it blocks you. Updated as weeks land.

Weeks 1–3 built the plumbing. Weeks 4–5 built the labelling and split tooling. **Nothing
past this point can run until you do the first three items below**, because there is no
corpus yet — the repository has zero documents in it.

---

## Blocking, in order

### 0. Get it running — 10 minutes, Windows

You are on Windows PowerShell, where `make` does not exist. It is a Unix shortcut, not part
of the project — **every `make X` in these docs has an exact equivalent: `covenant-evals X`.**

```powershell
# Python 3.11+ — check you have it
py --version

# Clone somewhere you keep code, not your home folder
cd $HOME\Documents
git clone https://github.com/28-Anon/s287788.git
cd s287788
git checkout claude/career-niche-evaluation-qyxusw
cd covenant-evals

# Install the project and its tools. The -e means edits take effect immediately.
py -m pip install -e ".[dev]"

# Prove it works
py -m pytest -q
py -m covenant_evals.cli --help
```

`py -m pytest -q` should report **192 passed**. If it does, the project runs on your machine.

### Why `py -m` and not just `pytest`

pip installs `pytest.exe` and `covenant-evals.exe` into a `Scripts` folder that Windows does
not put on PATH by default — it warns about this during install and it is easy to miss:

```
WARNING: The script covenant-evals.exe is installed in
'C:\Users\...\Python\pythoncore-3.14-64\Scripts' which is not on PATH.
```

`py -m <module>` never depends on PATH, so **these docs use that form throughout.** It is
the more reliable habit on Windows regardless.

If you would rather type `covenant-evals` directly, add that folder to PATH — take the exact
path out of the warning pip printed:

```powershell
# this session only
$env:Path += ";C:\Users\salah\AppData\Local\Python\pythoncore-3.14-64\Scripts"

# permanently, then restart the terminal
$scripts = "C:\Users\salah\AppData\Local\Python\pythoncore-3.14-64\Scripts"
[Environment]::SetEnvironmentVariable(
    "Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";$scripts", "User")
```

| Docs say | On Windows type |
|---|---|
| `make test` | `py -m pytest -q` |
| `make corpus-doctor` | `py -m covenant_evals.cli corpus doctor` |
| `make corpus-status` | `py -m covenant_evals.cli corpus status` |
| `make items-check` | `py -m covenant_evals.cli items check` |
| `make items-stats` | `py -m covenant_evals.cli items stats` |
| `make splits-freeze` | `py -m covenant_evals.cli splits freeze` |
| `make corpus-search Q='"credit agreement"'` | `py -m covenant_evals.cli corpus search --query '"credit agreement"'` |

With the Scripts folder on PATH, `py -m covenant_evals.cli` shortens to `covenant-evals`.

### 1. Set your EDGAR identity — 2 minutes

```powershell
Copy-Item .env.example .env
notepad .env
```

Set `EDGAR_USER_AGENT` to **your real name and a real email**:

```
EDGAR_USER_AGENT="Salah Missana your.email@example.com"
```

⚠️ **Notepad will try to save it as `.env.txt`.** In the Save dialog set "Save as type" to
"All Files", or run `Get-ChildItem -Force` afterwards and confirm the file is called exactly
`.env`. A file named `.env.txt` is silently ignored and you will get a confusing 403.

The SEC requires this header. A missing or generic one returns 403 and blocks your IP for
about ten minutes, so the code refuses to make a request without a plausible one.

**Then check it, before touching the network:**

```powershell
py -m covenant_evals.cli config check
```

It makes no network calls. It confirms the file is found, catches a `.env.txt` next to it,
runs your User-Agent through the same validation EDGAR would, and confirms `.env` is
gitignored so your email is never committed. Your address is masked in the output, so the
result is safe to paste anywhere.

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
