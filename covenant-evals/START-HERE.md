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

## 7. What's in the repo right now (week 1)

Nothing that does any AI yet. Deliberately. This week is just the foundations:

| File | What it does, plainly |
|---|---|
| `src/covenant_evals/schema.py` | The rules a question must follow to count as valid. E.g. "you must say which clause the answer came from" |
| `src/covenant_evals/items.py` | Reads your question files off disk and checks them all |
| `src/covenant_evals/budget.py` | Tracks what you're spending on API calls, so month 4 has no nasty surprise |
| `src/covenant_evals/cli.py` | Two commands: check my questions, show my spending |
| `tests/` | 28 small tests proving the above actually works. Run `make test` |
| `docs/LIMITATIONS.md` | An honest list of what this project *can't* tell you. Written now, before any results exist, because it's much harder to be honest once you've got a number you're proud of |
| `docs/METHODOLOGY.md` | The rules you're promising to follow. Mostly blanks to fill in as you go |
| `docs/TAXONOMY.md` | Empty. This becomes the catalogue of *ways the AI fails* — the most valuable thing you'll produce |
| `data/items/` | Empty until week 4. Your questions go here, one file each |

## 8. Try it right now

```bash
cd covenant-evals
make test         # 28 tests should pass in under a second
make validate     # "0 items — nothing to validate yet"
make budget       # "$0.0"
```

If those three work, week 1 is done. That's genuinely the whole goal for this week: a project
that runs, tests that pass, and somewhere for everything else to go.

## 9. What happens next

- **Week 2–3:** write the code that downloads contracts from the SEC website.
- **Week 4–7:** the real work — read contracts and hand-write ~110 questions with answers.
  This is slow, unglamorous, and it's where all the value is. Nobody else does it.
- **Week 8+:** finally point an AI at your questions and see how badly it does.

## 10. Things you don't need to understand yet

Genuinely fine to not know these in week 1. They arrive when you need them:

- How prompt caching works internally
- What "bootstrap confidence intervals" are (week 10 — it's a way of saying "84%, give or
  take 8%" instead of pretending you know it's exactly 84%)
- Anything about the AI judge (week 15)
- What prompt injection is (week 19)

**One thing to hold on to if the rest is a blur:** you are writing an exam that an AI has to
pass before anyone would trust it with money, and the exam is worth more than the AI.
