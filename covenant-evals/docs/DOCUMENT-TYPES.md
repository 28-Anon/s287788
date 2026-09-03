# What to keep and what to drop

A reference for `corpus review`. EDGAR's EX-10 exhibits are "material contracts", which is a
very wide net — you will meet all of these.

**The one test everything else approximates:** does the document *restrict what the borrower
may do*? Ctrl+F `Negative Covenants`, `shall not incur`, `Restricted Payments`. If none of
them appear, there is nothing to write questions about.

---

## Keep — the loan contract itself

| Title you will see | Why |
|---|---|
| **Credit Agreement** | The standard US syndicated form. What this corpus is made of |
| **Amended and Restated Credit Agreement** | **Keep.** See the trap below — this is a complete agreement, not an amendment |
| **Second / Third Amended and Restated Credit Agreement** | Same. The count just says how many times it has been restated |
| **Facility Agreement**, **Senior Facilities Agreement** | The English/LMA equivalent. These are your English-law documents |
| **Term and Revolving Facilities Agreement** | English/LMA, same thing |
| **Term Loan Agreement**, **Revolving Credit Agreement** | A single facility rather than a package. Thinner, still real |
| **Credit and Guaranty Agreement** | Credit agreement with the guarantee bolted in. Keep |
| **Loan and Security Agreement** | Usually asset-based (ABL). Covenants live in it, plus borrowing-base machinery. Keep and note the type |
| **Loan Agreement** | Often bilateral and short. Keep **if** it has a covenants section |
| **Note Purchase Agreement** | US private placement. Covenant-rich. Keep, and note that it is not a bank loan |

## Drop — attached to a loan, but not the loan

| Title | What it actually is |
|---|---|
| **Amendment No. 2 to Credit Agreement**, **First Amendment** | Changes a few clauses in an agreement you do not have. Meaningless alone |
| **Waiver**, **Consent**, **Forbearance Agreement** | The lenders agreeing not to enforce something. No covenants of its own |
| **Supplement**, **Joinder**, **Accession Deed** | Adds a party or a facility to an existing agreement |
| **Guarantee**, **Guaranty Agreement** | Somebody else promising to pay. Obligations, but not borrower covenants |
| **Security Agreement**, **Pledge Agreement**, **Debenture**, **Deed of Charge** | What the lender can seize. Different subject entirely |
| **Intercreditor Agreement**, **Subordination Agreement** | Who gets paid first among lenders. Nothing about the borrower |
| **Mortgage**, **Deed of Trust** | Security over property |
| **Assignment and Assumption** | One lender selling its position to another. Two pages |
| **Fee Letter** | What the arranger gets paid |
| **Commitment Letter**, **Term Sheet** | Pre-contractual. Not binding in the way an agreement is |
| **Payoff Letter**, **Termination Agreement** | The loan ending |
| **Promissory Note** | The IOU. Almost never carries covenants |
| **Escrow Agreement**, **Registration Rights Agreement** | Not lending at all — EX-10 just catches every material contract |

## Borderline — decide once, then be consistent

| Title | Call |
|---|---|
| **Indenture** | A bond, not a loan. Genuinely covenant-rich, but the covenant architecture differs enough that mixing them in muddies your results. **Drop by default.** Including one or two deliberately is defensible if you say so in the note and in LIMITATIONS.md |
| **Receivables / Securitisation Facility** | Very different machinery. Drop unless you want one deliberately as an outlier |
| **DIP Credit Agreement** | Debtor-in-possession lending in bankruptcy. A real agreement with real covenants, but unusual ones. At most one, noted |

---

## The trap that catches everyone

> **"Amended and Restated Credit Agreement" is a KEEP.**
> **"Amendment No. 3 to Credit Agreement" is a DROP.**

They look nearly identical in a filing list and they are opposites. *Amended and restated*
means the parties rewrote the whole contract and this document replaces everything before it
— it is complete and current, which makes it one of the **best** things you can have. *An
amendment* is a few pages changing clauses in a document you do not have.

The tell is the word **amendment**. If it says "Amendment", it is one. If it says "Amended
and Restated", it is not.

This filter got it wrong until 3 September 2026 and was silently discarding every
restatement before it ever reached you.

---

## The amendments you keep on purpose

Three or four, deliberately, tagged in the note. Week 20 builds the
`amendment_supersession` trap: items where a later filing changes the answer, and a system
reading only the original gets it confidently wrong.

For those you need **both** documents — the agreement and the amendment to it. Search hides
amendments by default, so collect them explicitly:

```
covenant-evals corpus search --query '"Majority Lenders"' --all
```

Note them as `amendment to <the agreement's accession>, kept for the week 20 trap`.

---

## When you cannot tell

Press `s` to skip. It comes back next time.

And nothing is final: you can drop a document later, the corpus is not fixed until the
splits are frozen, and dropping a good one costs nothing because `corpus bootstrap` will
find more.
