# What the corpus is, and what has to be in it

The corpus is not a pile of documents. **It is the design of your experiment**, and it is
fixed before you have any results. Every claim the project ever makes is a claim about
*these documents*. Nothing you do later — no scorer, no confidence interval, no clever
analysis — can recover something the corpus was not built to show.

So it is worth an hour of thinking now.

---

## 1. The principle everything else follows from

> **You are not collecting documents. You are collecting contrasts.**

Twenty-five near-identical US leveraged loans give you one number: how well a system reads
US leveraged loans. That is a fact, and a thin one.

Eight documents chosen to differ along axes you care about give you something better: **the
shape of where performance falls off.** "Grounded accuracy is 81% on New York-law
agreements and 63% on English-law ones" is a finding. "78% overall" is a scoreboard.

Which leads directly to the rule that governs corpus size:

> **At least two documents of anything you want to make a claim about.**

With one English-law document you cannot distinguish *"English-law drafting is harder"* from
*"that particular document is harder."* One is a finding about the field; the other is a
fact about one contract. With one document you can never tell which you have.

This is the single most common way an eval corpus is quietly wasted.

---

## 2. The axes that actually matter

Each of these is a plausible reason a system's performance would differ. Each needs at least
two documents to be claimable.

### Legal tradition — the highest-value axis

New York-law US style versus English LMA style. They differ in vocabulary (*Required
Lenders* / *Majority Lenders*), in covenant architecture, in how definitions are laid out,
and in where the exceptions live. A system trained mostly on US filings may well be worse at
English drafting, and **nobody has measured it.**

This is also the axis that makes the work interesting to a London employer, which is not a
scientific reason but is a real one.

### Covenant density

A leveraged loan carries a full covenant package: baskets, carve-outs, ratio tests,
builder amounts. An investment-grade revolver is close to covenant-lite. The question is
whether a system does *better* on sparse documents (less to get lost in) or *worse* (less
signposting, answers by absence). Genuinely not obvious in advance, which makes it worth
testing.

### Length and cross-reference depth

Twenty pages against three hundred. Tests whether accuracy degrades with context length and
with how far a definition chain reaches. A 1M-token window means the document *fits* — it
does not mean the model *tracks* a term defined on page 14 and used on page 210.

### Deal type

Corporate, asset-based (borrowing-base machinery), REIT, BDC fund-level, reserve-based
lending. Different vocabulary, different covenant kinds. Mostly a robustness check: does
performance hold when the words change but the structure does not?

### Vintage — the one most people miss

A credit agreement filed in 2019 has been public for years and may well be in a model's
training data. One filed in 2025 is much less likely to be. **A vintage spread lets you test
for memorisation:** if performance on 2018–2020 documents is markedly better than on
2024–2025 ones, that gap is not comprehension, and reporting it would be one of the more
interesting things this project could produce.

Aim for roughly half the corpus filed in the last two years.

### Original versus amended

For the `amendment_supersession` trap in week 20 you need **pairs**: an agreement *and* a
later amendment to that same agreement. Three or four pairs. Collect them together or you
will not find the match later.

---

## 3. The eight-document opening corpus

Enough for the first 25–40 items, and every slot earns its place.

| # | Slot | What it gives you |
|---|---|---|
| 1 | US leveraged loan, 2022+, full covenant package | The core case. Most items come from here |
| 2 | US leveraged loan, different industry and sponsor | Replication: is a result about the document or the type? |
| 3 | English LMA senior facilities, 2020+ | The tradition contrast |
| 4 | English LMA, second one | So the contrast is not one document's quirk |
| 5 | Investment-grade revolver, light covenants | Density contrast, and the easy end of the range |
| 6 | ABL / Loan and Security Agreement | Borrowing-base vocabulary, different covenant kinds |
| 7 | Short bilateral loan agreement, real covenants | Length contrast |
| 8 | An amendment to one of 1–6 | Opens the week 20 trap. Pair it deliberately |

Note what is deliberately **paired**: 1 with 2, and 3 with 4. Those two pairs are what make
the headline comparison possible. Everything else is a single because it is context, not a
claim.

## 4. Growing to twenty-five

Roughly: **6 US leveraged · 5 English LMA · 3 investment-grade · 3 ABL or specialty · 2 short
bilateral · 3 amendment pairs (6 documents, 3 of which are the agreements above) · 2 wildcards
you found genuinely confusing.**

Constraints throughout:

- **At most one document per filing.** Two exhibits in one filing are usually the agreement
  and something attached to it.
- **At most two per company.** One borrower's drafting habits are not a finding.
- **Vary the law firm** if you can tell. Three agreements from the same firm's template are
  close to one document.
- **8–12 items per document.** More than that and one document dominates your results.

---

## 5. What disqualifies a document

- **No negative covenants section.** Nothing to ask about.
- **You cannot confidently answer questions about it.** If you do not understand the
  document, your gold answers are guesses with a confident label on them.
- **It is a near-duplicate** of one you already have — same sponsor, same firm, same year.
- It is one of the derivative types in [DOCUMENT-TYPES.md](DOCUMENT-TYPES.md).

---

## 6. The statistical point that changes how you report results

Items from one document are **not independent**. They share a text, a drafting style, a
definitions section, one author's habits. If a system is good at document 4, it is good at
all twelve items from document 4.

So 250 items across 25 documents is **not** an effective sample of 250. For any claim about
credit agreements in general, the effective sample size is much closer to **25**.

Two consequences, and both are worth stating out loud in the write-up:

1. **Bootstrap by resampling documents, not items.** Resampling items gives confidence
   intervals that are far too narrow and a false sense of precision. Clustering on document
   is the honest version.
2. **More documents beats more items per document.** Twenty-five documents at 10 items each
   supports stronger claims than 10 documents at 25 items each, even though both give 250
   items.

Almost no published eval does this. Doing it, and saying why, is the kind of detail that
tells a careful reader you know what a measurement is.

---

## 7. What this corpus lets you claim

| With | You can say | You cannot say |
|---|---|---|
| 8 documents | "On these eight agreements, grounded accuracy was X" | Anything about credit agreements as a class |
| 25 across types | "In this sample, accuracy was X on NY-law and Y on English-law documents, a gap of Z (95% CI …, clustered by document)" | That the gap holds generally |
| Any number | What the failure modes *are*, with reproducible examples | How common they are in the wild |

**The taxonomy is where the transferable value lives.** A failure mode demonstrated on three
documents is a real finding about how these systems break. A percentage from 25 documents is
a fact about 25 documents. Write the paper around the former.
