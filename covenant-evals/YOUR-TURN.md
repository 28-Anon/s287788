# What's on you

Everything the tooling cannot do, in the order it blocks you. Updated as weeks land.

Weeks 1–3 built the plumbing. Weeks 4–5 built the labelling and split tooling. **Nothing
past this point can run until you do the first three items below**, because there is no
corpus yet — the repository has zero documents in it.

---

## Blocking, in order

### 0. Get it running — 10 minutes, Windows

You are on Windows PowerShell. **These docs no longer use `make` anywhere** — it is a Unix
tool that does not exist on Windows and nothing in this project needs it. The Makefile is
still there as a shortcut for Unix users; ignore it.

Wherever you see `covenant-evals X`, type **`py -m covenant_evals.cli X`** — identical, and
it does not depend on PATH. Or use the wrapper: **`.\dev.ps1 X`**.

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
| `python -m pytest -q` | `py -m pytest -q` |
| `covenant-evals corpus doctor` | `py -m covenant_evals.cli corpus doctor` |
| `covenant-evals corpus status` | `py -m covenant_evals.cli corpus status` |
| `covenant-evals items check` | `py -m covenant_evals.cli items check` |
| `covenant-evals items stats` | `py -m covenant_evals.cli items stats` |
| `covenant-evals splits freeze` | `py -m covenant_evals.cli splits freeze` |
| `covenant-evals corpus search --query '"credit agreement"'` | `py -m covenant_evals.cli corpus search --query '"credit agreement"'` |

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

### 2. Confirm the EDGAR pipeline still works — 30 seconds ✅ done once

```powershell
py -m covenant_evals.cli corpus doctor
```

**This has now been run against the live SEC and passes.** It found two real bugs the test
suite could not: EDGAR returns `root_forms`, not `root_form`, so the parser was silently
recording an empty form for every hit; and the doctor was sampling whatever document sorted
first, which turned out to be an amendment and then a supplement — neither of which has the
structure of an agreement.

Re-run it whenever something stops working, or before trusting a long fetch. On a failure,
`--paste` prints a structure-only block, and where segmentation finds nothing it attaches a
census that says which of the three causes it is: headings not matched, headings matched but
rejected, or the document simply is not an agreement.

### 3. Build the corpus — two commands, then your judgement

```powershell
py -m covenant_evals.cli corpus bootstrap --start 2018-01-01 --dry-run
py -m covenant_evals.cli corpus bootstrap --start 2018-01-01
py -m covenant_evals.cli corpus fetch
py -m covenant_evals.cli corpus sections --check
```

`bootstrap` runs five searches, discards amendments and waivers, ranks what is left,
interleaves the results so no single phrase dominates, and writes up to 25 candidates to the
manifest. It replaces about thirty `corpus add` calls and the accession-copying mistakes
that come with them.

**What it deliberately does not do is decide your corpus.** Everything it adds is marked
PROVISIONAL, and `governing_law` is left empty even though the query that found a document
hints at it — a guess stored in the same field as a checked fact is indistinguishable from
one six weeks later, and the US/English comparison is a headline result.

So after bootstrap, before fetching:

- **delete anything that is not a real credit agreement** — open a few and look
- **set `--governing-law`** once you have read enough of each to actually know
- **replace the provisional note** with why that document is in your corpus

Corpus selection is the largest single source of bias in your results — `docs/LIMITATIONS.md`
says so in writing — and it is the part that has to be yours.

The mix to end up with:

- **25 documents**, at least **5 English-law**
- **3 or 4 amendments**, added deliberately with `corpus search --all`, tagged in the note.
  Week 20 needs them for the amendment_supersession trap
- **two you find genuinely confusing** — they produce the best items

Read every warning `corpus sections --check` prints. If it finds nothing in a document,
`corpus doctor --paste` names which of the three causes it is.

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
covenant-evals items check     # before every commit
covenant-evals items stats     # is the mix right?
```

### 5. Freeze the splits — 5 minutes, once, in week 5

Do this **after** the corpus is complete and **before** you have run anything against it.

```bash
covenant-evals splits freeze
git add data/splits.json && git commit -m "Freeze dev/test/heldout split"
```

Then do not open heldout until week 22. The code will stop you by accident; only you can
stop yourself on purpose.

---

## Standing rules

- **`covenant-evals items check` before every commit.** It re-verifies every item against its
  document — hash, section, citation offsets, and whether the quote is in the section you
  cited.
- **Every four weeks, relabel 30 items blind.** Your self-agreement is the ceiling on every
  number this project will report. Put it in the README.
- **Track spend from the start.** `covenant-evals budget`. The dev loop belongs on Haiku; Opus is for
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
