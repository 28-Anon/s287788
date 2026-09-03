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
py -m covenant_evals.cli corpus bootstrap --start 2018-01-01
py -m covenant_evals.cli corpus review
py -m covenant_evals.cli corpus fetch
py -m covenant_evals.cli corpus report
```

**`bootstrap`** runs five searches, discards amendments and waivers, and writes up to 25
candidates to the manifest. It replaces about thirty `corpus add` calls.

**`corpus review` is where you actually decide.** It walks the candidates one at a time,
**opens each filing in your browser** — where a contract is properly readable, with its
tables and formatting — and asks four things in the terminal: keep, drop or skip; which law
governs it; and why it is in your corpus. It saves after every decision, so quitting halfway
keeps what you have done. Answer `q` whenever you want to stop.

That is the judgement task. Everything bootstrap adds is marked PROVISIONAL and its
`governing_law` is left empty on purpose — a guess stored in the field a checked fact goes
in is indistinguishable from a fact six weeks later, and the US/English comparison is a
headline result.

**`corpus report`** writes `runs/corpus.html` and opens it: every document, how it
segmented, what is unreviewed, which law, which split, a link to each filing, and a
plain-English diagnosis for anything the segmenter could not read. Twenty-five documents
with section trees is not something to read down a terminal. It is a local file and nothing
leaves your machine.

#### What you are deciding in `review`

A **skim, about a minute each.** One question: **does this document restrict what the
borrower may do?** You are not reading it properly — that comes in weeks 4–7.

| | |
|---|---|
| **keep** `k` | It has restrictions you could write a question about |
| **drop** `d` | No restrictions at all. Or it is an amendment, waiver, supplement, guarantee, security agreement, pledge or intercreditor agreement — attached to a loan, not the loan |
| **skip** `s` | You cannot tell in a minute. It comes back next time |
| **quit** `q` | Stop. Everything decided so far is saved |

**Full reference: [docs/DOCUMENT-TYPES.md](docs/DOCUMENT-TYPES.md)** — every title you will
meet on EDGAR, with keep or drop and why. Worth one read before you start.

**Ctrl+F is the whole technique.** Two searches settle almost every document:

- **"Negative Covenants"** — or `"shall not incur"`, or `"Restricted Payments"`. If none of
  them appear, there is nothing to ask questions about, so drop it. This is the real test.
- **"governed by"** — lands on the governing law clause, near the end. "the State of New
  York" → `1`. "England and Wales" → `2`.

**Length is a preference, not a rule.** A 300-page syndicated agreement gives more items and
harder ones — chained definitions, baskets, carve-outs. A 20-page bilateral loan agreement
with a real covenants section is still worth keeping, and two or three of them are actively
useful: they are the easy end of the difficulty range, and an eval where every item is hard
tells you as little as one where every item is easy. Note them as such.

What length does tell you is how many questions you will get out of it. If you cannot
imagine eight non-trivial questions in there, it is probably not worth a slot.

#### The note

One line, written for yourself in six weeks. It does three jobs: it tells you what is in a
document when you come to pick one to label, it lets results be reported by deal type and
legal tradition, and collectively the notes become the honest account of how the corpus was
selected that `docs/LIMITATIONS.md` promises.

Say **what kind of deal**, **which tradition**, and **anything notable**:

```
US leveraged loan, sponsor-backed, full covenant package
English law LMA senior facilities, real estate borrower
Investment-grade revolver, light covenants — useful as an easy contrast
Asset-based revolver (ABL), borrowing base mechanics
BDC fund-level facility, unusual asset coverage covenants
REIT credit facility, heavy financial covenant section
Reserve-based lending, mining borrower, commodity price definitions
Amendment kept deliberately for the week 20 supersession trap
Very heavily defined-term chained — expect this one to be hard
```

Two that are no use: *"credit agreement"* (says nothing you did not already know) and
*"looks good"* (says nothing at all).

Honest uncertainty is fine and better than a confident guess: *"probably US leveraged loan,
did not read far enough to be sure"* is a perfectly good note. You can edit any of them
later in `data/corpus/manifest.json`.

**Do not agonise.** Nothing here is final — you can drop a document later, and the corpus is
not fixed until you freeze the splits in week 5. A wrong keep costs you one skim; a wrong
drop costs you nothing at all, because bootstrap will find more.

The mix to end up with:

- **25 documents**, at least **5 English-law**
- **3 or 4 amendments** added deliberately with `corpus search --all` and tagged in the
  note; week 20 needs them for the amendment_supersession trap
- **two you find genuinely confusing** — they produce the best items

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
