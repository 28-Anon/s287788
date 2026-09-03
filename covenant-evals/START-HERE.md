# Start here

Plain English. No jargon that isn't explained on the spot. Read this before the README.

---

## 1. What is this project, in one sentence?

You are building **a test** — like an exam paper with a marking scheme — that checks whether
an AI can read a loan contract and answer questions about it *without making things up*.

That's it. The AI isn't the thing you're building. **The exam is the thing you're building.**

## 2. Why is that worth doing?

Banks and lenders are trying to put AI into jobs where it moves or risks real money. They are
all stuck at the same place. Not "can we build it" — anyone can build it. They're stuck at
**"how do we prove it's safe enough to switch on?"**

Almost nobody knows how to answer that. It's the bottleneck. If you're one of the people who
can, you're valuable — and you get more valuable as AI gets better, not less, because a more
capable system that nobody can check is a bigger problem, not a smaller one.

So the project isn't really about loan contracts. It's a demonstration that you can build the
thing that decides whether an AI system is trustworthy. Loan contracts are just the arena you
do it in, chosen because the documents are free and public.

## 3. What's a "credit agreement" and a "covenant"?

A **credit agreement** is the contract behind a big business loan. Often 100+ pages. Companies
in the US have to file them publicly with the financial regulator (the SEC), so they're free
to download — which is the entire reason we're using them.

A **covenant** is a promise inside that contract. Usually a restriction: *"the borrower will
not take on more than £X of extra debt"*, *"the borrower will keep its debt below 4× its
earnings"*.

The questions you'll be asking are the kind a credit analyst gets paid to answer:

> *"Can this company borrow another $50 million without asking us first?"*

Sounds simple. It isn't — the answer is usually spread across three clauses, two of which
redefine words used in the third, and there's often an exception hidden in a sub-paragraph
that flips the answer completely. **That's exactly why it's a good test.**

## 4. What does the AI have to do, and how do you mark it?

You give the AI the contract and the question. It answers, and it must **quote the exact bit
of the contract that proves its answer**.

Your marking rule, which is the one opinionated decision in the whole project:

> **Right answer + fake quote = FAIL.** Not partial credit. A fail.

Why so harsh? Because in the real world nobody acts on an answer they can't check. If the AI
says "no, they can't borrow more" and points at a paragraph that doesn't exist, you have
learned nothing — you just got lucky. This is called **grounded accuracy** and it's your
headline score.

## 5. The jargon, decoded

| Term | What it actually means |
|---|---|
| **Eval / harness** | The exam and the marking scheme. The code that asks the questions and scores the answers |
| **Item** | One question, with its correct answer and the quote that proves it. You'll write ~250 of these by hand |
| **Gold / ground truth** | The correct answer, as decided by you reading the contract carefully |
| **Corpus** | The pile of contracts you're testing against (25 of them) |
| **Splits** | Dividing your questions into three piles so you can't fool yourself — see below |
| **Abstain** | Questions where the honest answer is *"the contract doesn't say"*. AI systems hate admitting this and will confidently invent an answer. Catching that is one of your best results |
| **Trap** | A label for *why* a question is hard, e.g. "the answer depends on a definition that points at another definition" |
| **The judge** | Using an AI to help mark answers that are too wordy to check automatically |
| **Cohen's κ (kappa)** | A number from 0 to 1 measuring how often two markers agree. You use it to check whether the AI judge marks like you do. If it doesn't, you can't trust it |
| **Prompt caching** | The API charges much less if you send it the same contract repeatedly, as long as you send it the same way each time. This is the difference between a $16 test run and an $80 one |

## 6. The three piles (splits) — why this matters more than it looks

Split your questions into three groups:

- **dev (~40)** — you look at these constantly while building. Fair game.
- **test (~140)** — you check your score on these, but don't stare at individual questions.
- **heldout (~70)** — **you do not look at these at all until week 22.** Locked in a drawer.

Here's the reason. If you keep tweaking your system until it does well on questions you can
see, you haven't built something that reads contracts — you've built something that does well
on *your 250 questions*. It's the difference between a student who learned the subject and one
who memorised last year's paper.

The heldout pile is the real exam. The gap between your test score and your heldout score
tells you how much you were fooling yourself. **That gap is one of the most interesting
things you'll publish**, whatever it turns out to be.

## 7. What's in the repo right now

Nothing that does any AI yet. Deliberately. This week is just the foundations:

| File | What it does, plainly |
|---|---|
| `src/covenant_evals/schema.py` | The rules a question must follow to count as valid. E.g. "you must say which clause the answer came from" |
| `src/covenant_evals/items.py` | Reads your question files off disk and checks them all |
| `src/covenant_evals/budget.py` | Tracks what you're spending on API calls, so month 4 has no nasty surprise |
| `src/covenant_evals/cli.py` | Two commands: check my questions, show my spending |
| `tests/` | 28 small tests proving the above actually works. Run `python -m pytest -q` |
| `docs/LIMITATIONS.md` | An honest list of what this project *can't* tell you. Written now, before any results exist, because it's much harder to be honest once you've got a number you're proud of |
| `docs/METHODOLOGY.md` | The rules you're promising to follow. Mostly blanks to fill in as you go |
| `docs/TAXONOMY.md` | Empty. This becomes the catalogue of *ways the AI fails* — the most valuable thing you'll produce |
| `data/items/` | Empty until week 4. Your questions go here, one file each |

## 8. Try it right now

```bash
cd covenant-evals
pip install -e ".[dev]"
python -m pytest -q                          # the test suite
python -m covenant_evals.cli items check     # "0 items — nothing to check yet"
python -m covenant_evals.cli budget          # "$0.0"
```

On Windows use `py` instead of `python`. The `python -m` form is deliberate: pip also
installs a `covenant-evals` command, but Windows does not put its folder on PATH by
default, and `-m` never depends on PATH.

On Mac or Linux there is a `make` shortcut for each of these. On Windows there is no `make`
— use the `covenant-evals` command, which does exactly the same thing.

If those work, the project is running. That's genuinely the whole goal for this week: a project
that runs, tests that pass, and somewhere for everything else to go.

## 9. Week 2 is done — here's what it added, plainly

Code that goes and gets the contracts for you.

| Command | What it does |
|---|---|
| `covenant-evals corpus search --query '"Majority Lenders"'` | Searches every SEC filing for that phrase. Downloads nothing — just shows you what exists |
| `covenant-evals corpus add ... --cik ... --governing-law English` | "Yes, I want that one." Writes it into the manifest |
| `covenant-evals corpus fetch` | Downloads them, strips the HTML down to plain text, and fingerprints the result |
| `covenant-evals corpus status` | How many you have, how many still to get |

Three ideas in there are worth understanding, because they come up again and again:

**The fingerprint (hash).** When you fetch a document, the code takes the plain text and
produces a 64-character fingerprint of it. Change one comma and the fingerprint changes
completely. Every question you write later stores the fingerprint of the document it was
written against. So if a contract on EDGAR ever gets replaced, the code notices immediately
and tells you *"the questions written against this document may now be wrong"* — instead of
you quietly scoring against text that no longer says what you thought.

**Never download twice.** Run `corpus fetch` ten times and it makes one network request per
document, ever. Partly manners — the SEC asks people not to hammer their servers — and
partly that a script you're afraid to re-run is a script you'll avoid using.

**Refusing to run.** If you haven't set your name and email in `.env`, the code stops with
an explanation instead of calling EDGAR. The SEC requires that header, and sending a bad one
gets your home IP blocked for ten minutes. A loud failure on your laptop beats a mysterious
one halfway through fetching 25 documents.

## 10. "Should this be US-only, or can we do the UK too?"

You asked this, and it's a better question than it looks.

**Short answer: the documents come from the US system, but not all of them are US-law
documents — and that distinction is now built into the project.**

Here's the thing. US law requires a company to publicly file its important contracts,
including loan agreements. **UK law does not.** Companies House gets your accounts and a
short note that a lender has security over your assets — it does not get the 150-page
facility agreement. So there is no British EDGAR to point this at. That's not a preference;
it's the reason the corpus is where it is.

But — and this is the useful part — plenty of documents *on* EDGAR are governed by **English
law**, not New York law. UK companies with US listings file there. US companies borrowing in
London file there. And English-law loan documents are drafted in a noticeably different
house style (the LMA style): different vocabulary — *Majority Lenders* rather than *Required
Lenders* — different covenant structure, definitions laid out differently.

So the corpus now records **which law governs each document** as a separate field from where
it was filed, and targets at least five English-law agreements among the twenty-five.

Why that's worth doing, for you specifically: you're in the UK, applying to UK institutions.
"I built an eval for AI reading loan contracts" is good. **"...and I measured whether it
holds up on English-law LMA-style documents, where the score drops eleven points"** is a much
better thing to say in a London interview — and as far as I can find, nobody has measured it.

One honest caveat: I could not reach Companies House from here to double-check what it does
and doesn't publish. That paragraph is from knowledge, not verified today. Spend ten minutes
confirming it yourself before you repeat it to anyone.

## 11. Week 3 is done — the code can now find its way around a contract

Every question you write has to say *which clause* the answer came from. So the code needs
to understand that a contract has a structure — Article VII contains Section 7.02, which
contains paragraph (b), which contains sub-paragraph (ii) — and be able to jump to any of
them.

Two commands, and the second is the one you'll live in from week 4:

```bash
covenant-evals corpus section 0000950170-24-012345 '7.02(b)'
covenant-evals corpus locate 0000950170-24-012345 'not to exceed the greater of $35,000,000'
```

`section` shows you a clause. `locate` takes a sentence you want to quote and tells you
**exactly where it sits in the document** — printing a `gold_span: [445, 795]` line you
paste straight into your question file. You never count characters by hand.

`locate` also does something more useful than it sounds: **if your quote appears more than
once, it fails and tells you.** A citation that matches two places in a contract is
ambiguous, and the offsets you record might not be the passage you meant. Better to find
that out now than to discover in week 22 that eleven of your questions cite the wrong thing.

### The genuinely hard bits, in case you're curious why this took a week

**The table of contents.** Nearly every credit agreement opens with a contents list that
repeats every heading in the document with a page number after it. Left alone, the code
finds a phantom copy of the entire structure at the front, and "7.02" resolves to a line in
the contents list rather than the actual covenant.

**"(i)" means two different things.** It's roman numeral one — and it's also the letter
after (h). The rule the code uses: treat it as a letter only if the previous paragraph was
(h). Otherwise it's roman one.

**US and English contracts don't number themselves the same way.** US: `ARTICLE VII` then
`SECTION 7.02. Liens.` English/LMA: `23. NEGATIVE COVENANTS` then `23.1 Financial
Indebtedness`. Because you decided to include both, the code handles both.

### The part worth actually remembering

The unit tests all passed. Then I ran it on a realistic document and it was **wrong in two
places**:

- A financial ratio that wrapped onto its own line — `4.00 to 1.00;` — was read as
  "Section 4.00", and it swallowed the rest of the covenant as its contents.
- A cross-reference that wrapped onto its own line — `Section 7.03(b) and subject to...` —
  was read as the *heading* of section 7.03. So every question citing 7.03 would have
  pointed at a sentence in 7.01 instead.

Neither would have thrown an error. Neither would have failed a test. They'd have quietly
corrupted a chunk of your labels months later.

**That is the entire thesis of this project, happening to you on week 3.** A system can be
confidently, silently wrong, and the only thing that catches it is someone deliberately
checking against reality. Both are now regression tests, and `covenant-evals corpus sections --check` runs the
segmenter over every document at once so the next one gets found on 25 documents rather
than in one broken label.

## 12. Week 4 — the part I can't do for you, and everything around it that I can

Week 4's deliverable is **25 hand-labelled questions**. I have built everything except the
25 questions, and that gap is deliberate, not laziness.

### Why I didn't write the questions

If a model writes the answers, you are testing a model against a model's opinion. Every
number you compute from that is circular. That one is obvious.

The less obvious one: **even letting a model write the *questions* poisons the set.** Models
ask the questions models find natural — clean provisions, answer in one place, well
signposted. The entire value of your dataset is the opposite: the questions where a
confident-looking system quietly gets it wrong. Generate the questions and you
systematically filter out the ones worth having, and the corpus still looks fine from the
outside.

So the questions are yours. What I built is everything that makes writing them fast and
hard to get wrong.

### What's new this week

**The schema is frozen.** Three fields added first, each because the old schema couldn't
express something real: `unit` (35000000 of *what* — dollars, percent, a ratio?),
`enum_options` (an enum with no options is just free text), and `dispute_note` (a question
that turns out to be arguable is a finding, so it's kept and excluded from scores rather
than deleted). A test now fails if anyone changes the field list without following the
protocol.

**One command writes an item:**

```bash
covenant-evals items new --ref 0000950170-24-012345 --section '7.01(b)'   --question 'May the Borrower incur $50,000,000 of incremental term loans without lender consent?'   --type boolean --gold false   --quote 'not to exceed the greater of $35,000,000'   --rationale 'The basket caps incremental facilities below the requested figure.'   --traps basket_cap --difficulty hard
```

You paste a quote. It finds the offsets, pins the document's fingerprint, and writes the
file. **You never count characters.**

**And it argues with you.** All five of these are refusals, tested:

| It says | What you actually did |
|---|---|
| *the quote is in section 7.02, not 7.01(b)* | Right sentence, wrong section |
| *that quote appears 2 times* | Ambiguous citation — the offsets might be the wrong copy |
| *that quote does not appear* | A smart quote, an en dash, or a word you retyped |
| *section '9.99' does not resolve* | Typo, or you're in the wrong document |
| *numeric answers need a unit* | 35 million what? |

**`covenant-evals items check` re-checks everything, later.** For every item: is the document still
the one you labelled, does the section still exist, is the quote still at those offsets, and
**is the quote inside the section you cited**. That last one catches the item that looks
perfect and teaches the wrong lesson.

**`docs/LABELLING.md`** is the actual protocol — how to run an hour-long session, what
separates a good item from a bad one with worked examples of both, and a bank of question
shapes for each trap so you're not staring at section 7.02 wondering what to ask.

### What to do now

Open `docs/LABELLING.md`. Pick one section of one agreement. Read it once without writing
anything. Then write three questions and answer them.

Time yourself honestly. Multiply by 25. That number is your week 4, and knowing it now is
worth more than any tool I could have built you.

## 13. Week 5 — the three piles, and a lock on the third

Week 5 does two things: you get to 60 items, and the corpus gets cut into dev, test and
heldout. The cutting is built; the items are still yours.

**Split by document, not by question.** Two questions about the same clause — one in dev,
one in test — are not independent. Tune against the first and you have tuned against the
second without noticing. So every question about one agreement lives in one pile, always.

**Balanced by governing law.** If dev were all US-law and heldout all English-law, a drop
between them would be indistinguishable from "the English pile is just harder". Since
comparing the two is one of your headline results, the split spreads them deliberately.

**Frozen means frozen.** `splits freeze` refuses to run twice. Adding a document later is
allowed; moving one between piles is not — every past result was measured against the old
arrangement, so redrawing it silently rewrites history.

### The interesting bit: making heldout genuinely hard to open

You are meant not to look at the heldout pile until week 22. That's seventeen weeks. Nobody
holds that on willpower.

So it's mechanical. Any command that would read heldout **refuses** unless you give a
written reason of at least ten characters — a one-word reason is exactly how a lock gets
defeated by accident — and every single opening is appended to `runs/heldout-access.log`,
which is committed to git.

```
$ covenant-evals items export --split heldout

the heldout split is closed until week 22.
Opening it early is the single easiest way to invalidate this whole project: any
decision informed by heldout turns it into a second test split.
If you genuinely mean to open it, pass a reason of at least ten characters. It is
written to runs/heldout-access.log, which is committed.
```

**That log is the point.** When you publish, it is proof that you opened the heldout set
once, in week 22, deliberately. Almost nobody can show that, and to a careful reader it is
worth more than a high score — because it means the number is real.

One more guard, small but important: **exporting questions never includes the answers.**
The export path emits the question, the document and the section, and is structurally
incapable of emitting the gold answer or the citation. Handing the answer to the thing you
are testing is the dumbest available failure, so the code cannot do it.

### Also: read YOUR-TURN.md

You asked what's on you. It's now a file in the repo — `YOUR-TURN.md` — listing everything
blocked on you, in order, with time estimates. Short version: set your EDGAR email, confirm
the fetch pipeline against the live SEC (it has never run there), build 25 documents, then
start labelling.

## 14. What happens next

- **Weeks 6–7:** keep labelling to ~110 items.
- **Week 8+:** finally point an AI at your questions and see how badly it does.

## 15. Things you don't need to understand yet

Genuinely fine to not know these in week 1. They arrive when you need them:

- How prompt caching works internally
- What "bootstrap confidence intervals" are (week 10 — it's a way of saying "84%, give or
  take 8%" instead of pretending you know it's exactly 84%)
- Anything about the AI judge (week 15)
- What prompt injection is (week 19)

**One thing to hold on to if the rest is a blur:** you are writing an exam that an AI has to
pass before anyone would trust it with money, and the exam is worth more than the AI.
