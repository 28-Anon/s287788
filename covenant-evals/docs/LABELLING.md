# How to label

The protocol for writing items. Read once before your first session, then keep it open.

Target for week 4: **25 items.** That is roughly five hours of careful reading, in sessions
of about an hour. It is the slowest, least technical, least impressive part of this project
and it is the only part nobody else will do.

---

## Why these cannot be generated

The obvious shortcut is to have a language model draft the questions and answers. Do not.
Two separate reasons, and the second is the one people miss.

**Answers are contamination, plainly.** A gold answer produced by a model, used to test a
model, measures agreement rather than correctness. Every number computed from it is
circular. This is not a close call.

**Questions are contamination too, more subtly.** Model-drafted questions cluster on what
models find natural to ask — clean, well-signposted provisions with the answer in one place.
The whole value of this dataset is the opposite: the questions where a competent-looking
system quietly gets it wrong. Generate the questions and you systematically select against
the items worth having, while the corpus still *looks* fine.

The one safe use of a model here is **question shapes** — the templates in §5 below, which
are about credit agreements in general and not about any document in your corpus. Filling
one in requires reading the actual clause, which is the part that has to be yours.

---

## 1. The two rules that outrank everything else

**Label before you look.** Write the gold answer before you have run any system on that
question. One contaminated item is a footnote; the habit invalidates the whole set.

**No section, no item.** If you cannot say which clause the answer comes from, the item is
not ready. Not "roughly section 7" — the clause.

---

## 2. A one-hour session

1. **Pick one section**, not a document. "Section 7.02, Liens" is a session. "This
   agreement" is not.
2. **Read it once without writing anything.** Including every defined term it leans on.
   You cannot write a question about a provision you have not understood, and the attempt
   produces items whose answers are not actually in the document.
3. **Write down what a lender would care about here**, in your own words, three or four
   things. These become questions.
4. **Write the questions, then find the answers.** In that order. Reversing it produces
   questions shaped to the answer you already spotted, which are easy questions.
5. **Create each item with the tool** (§4). It fills in the hash, the offsets and the
   section check, and refuses several mistakes you would otherwise make silently.
6. **Stop when you stop being careful.** Twenty-five good items beat forty rushed ones, and
   a rushed item is worse than no item because it looks the same as a good one.

Log the session in one line: date, section, items written, anything that confused you. The
confusions become taxonomy entries in week 12.

---

## 3. What makes an item good

A good item has **one fact in it**, an answer that is **checkable in the document**, and a
quote that **would convince someone who disagreed with you**.

### Bad, and why

> **Q:** Is the leverage covenant reasonable?

Not answerable from the document. There is no fact here.

> **Q:** What are the restrictions on indebtedness?

Not one fact. Nothing to mark against — any summary is arguably correct.

> **Q:** Can the Borrower incur more debt?
> **A:** No.

Under-specified. More than what? Under which basket? A system that answers "it depends on
the amount" is right, and you have marked it wrong.

### Good

> **Q:** May the Borrower incur $50,000,000 of incremental term loans without obtaining
> lender consent?
> **A:** false
> **Quote:** "in an aggregate principal amount not to exceed the greater of $35,000,000 and
> 25% of Consolidated EBITDA"
> **Why:** the Free and Clear amount caps incremental facilities below the requested figure.

One fact. A specific number that sits on the far side of a specific cap. The quote settles
it. Someone who disagreed would have to argue with the contract, not with you.

**The test:** could a competent stranger, given only the document, arrive at your answer and
your citation? If the answer depends on something you know and did not write down, the item
is not ready.

---

## 4. Creating an item

```bash
covenant-evals items new \
  --ref 0000950170-24-012345 \
  --section '7.01(b)' \
  --question 'May the Borrower incur $50,000,000 of incremental term loans without lender consent?' \
  --type boolean --gold false \
  --quote 'not to exceed the greater of $35,000,000' \
  --rationale 'The Free and Clear amount caps incremental facilities below the requested figure.' \
  --difficulty hard --traps basket_cap,defined_term_chain --by SM
```

You paste a quote; it finds the offsets. You never count characters.

It refuses to write an item when:

| It says | What you did |
|---|---|
| the quote is in section 7.02, not 7.01(b) | Right sentence, wrong section — decide which is wrong |
| that quote appears 2 times | Ambiguous citation. Quote more context until there is one match |
| that quote does not appear | A smart quote, an en dash, or a word you retyped |
| section '9.99' does not resolve | Check the tree with `corpus sections` |
| numeric answers need a unit | "35000000" of what — dollars, percent, a ratio? |

Then `covenant-evals items check` re-verifies every item against its document: hash still
matching, section still resolving, quote still at those offsets, quote inside the cited
section. Run it before every commit.

---

## 5. Question shapes, by trap

Use these as prompts for your own reading, not as templates to fill blindly. Each needs a
real clause behind it.

### `basket_cap` — a permitted amount is capped by a formula
- May the Borrower incur $N of [debt type] without consent? *(pick N above and below the cap — two items, one true, one false)*
- Is the cap a fixed amount, a formula, or the greater of the two?
- Does the cap reset annually or apply to the life of the facility?

### `defined_term_chain` — the answer needs a definition that cites another definition
- Is [specific thing] included in the definition of [defined term]?
- Does [Term A] as used in this clause include amounts owed by [entity type]?
- Which definition determines whether [event] has occurred?

### `carve_out` — an exception reverses the plain reading
- The clause prohibits X. Does it prohibit X in [specific circumstance]?
- Is [permitted transaction] caught by the prohibition in [section]?
- Does the exception require consent, notice, or neither?

### `negative_covenant_inversion` — "shall not" read as "may"
- Is the Borrower permitted to [do the thing the covenant forbids]?
- Must the Borrower obtain consent before [action], or merely give notice?

### `cross_reference` — the clause points elsewhere
- Which section governs [topic] for the purposes of this clause?
- Does the definition in [section] or the one in [other section] apply here?

### `numeric_unit_confusion` — millions, percentages, ratios
- What is the maximum permitted [amount], in dollars? *(answer_type: numeric, unit: USD)*
- What is the maximum permitted Leverage Ratio? *(unit: ratio)*
- Is the threshold a percentage of EBITDA or of total assets?

### `not_in_document` — the honest answer is that it does not say
**Target about one item in five.** These are the hardest to collect and the most valuable:
they are where a confident invention shows up.
- What is the governing law of the intercreditor agreement? *(when this document does not say)*
- What interest rate applies after an Event of Default? *(when the clause is silent)*
- How many lenders are party to this facility? *(when only "the Lenders" is used)*

Write these deliberately, from things you *expected* to find and did not. Do not invent
absurd questions — the abstention has to be a realistic one a person would actually ask.

### `amendment_supersession` — week 20
Needs a second filing that amends the first. Note candidates as you go; do not chase them
in week 4.

### `injected_instruction` — week 19
Constructed deliberately, not found. Leave it.

---

## 6. The mix to aim for

Across the whole set, not each session:

| Dimension | Target |
|---|---|
| `abstain` items | ~20% |
| `hard` | at least a third |
| Items per trap | at least 5 |
| Items per document | 8–12, so no single agreement dominates |
| English-law documents | at least 5 documents' worth |

`covenant-evals items stats` reports all of this and tells you what is thin.

---

## 7. When you are not sure

Three options, in order of preference:

1. **Read more of the document.** Most uncertainty is missing context.
2. **Skip the question.** A question you cannot answer confidently is a question a
   competent lawyer might answer differently, and it does not belong in a gold set.
3. **Write it and mark it `disputed`,** with a `dispute_note` saying what the disagreement
   is. Disputed items are excluded from headline scores but kept — a question that turned
   out to be arguable is itself a finding, and one worth writing up.

Never resolve uncertainty by picking the answer that seems more likely. That is exactly the
behaviour you are building this to detect.

---

## 8. Self-agreement, every four weeks

Relabel 30 random items blind — do not look at your originals until you are done. The rate
at which you agree with yourself is the **ceiling on every number this project reports**. If
you agree with yourself 85% of the time, no system can credibly be said to score above 85%.

Publish that number in the README. Almost nobody does, and it is the fastest way to show a
reader that you know what you are doing.
