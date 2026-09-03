# Limitations

Written in week 1, before any results exist, and updated as more become apparent. Writing
this first is deliberate: it is much harder to be honest about limitations once you have a
number you are proud of.

## 1. A single labeller, so there is no inter-annotator agreement

Every item is labelled by one person. The project reports that person's *self*-agreement —
a sample of items relabelled weeks later, blind — which bounds how high any system could
credibly score. But self-agreement does not catch a **systematic** misreading: if the
labeller consistently misunderstands how incremental facility baskets work, every item
touching them is wrong in the same direction and no internal check will reveal it.

Anyone reading a result from this repository should treat the labels as one careful
non-lawyer's reading, not as settled fact.

## 2. The corpus is selected, not sampled

Twenty-five agreements chosen by hand. They over-represent what was findable on EDGAR
full-text search and what the labeller found interesting, and they are exclusively
English-language, **filed with the SEC**, and public. That excludes private credit
agreements that are never filed anywhere — which is precisely the segment the downstream
use case cares most about.

Note what this does *not* exclude. Where a document was filed and which law governs it are
different facts. EDGAR carries English-law, LMA-style facility agreements as well as
New York-law ones, because UK groups with US listings and US groups borrowing in London
both file there. The corpus deliberately includes at least five English-law agreements and
records `governing_law` for every document, so results can be reported by legal tradition
rather than pooled into a single misleading number.

What is genuinely unavailable: UK-only borrowers with no US listing. The UK has no
equivalent of the US requirement to file material contracts as exhibits, so their facility
agreements are simply not public anywhere. Any claim this project makes about English-law
drafting rests on the subset that reached EDGAR, which is larger and more listed-company-
heavy than the English-law market as a whole.

## 3. Ground truth is a reading, not a legal opinion

For genuinely contested provisions, competent credit lawyers disagree. The intent is that
arguable questions never become items — but the labeller will not always recognise that a
question is arguable, which means some portion of the gold set encodes a confident answer to
a question that does not have one. Items found to be arguable are marked `disputed` and
excluded from headline scores rather than silently corrected.

## 4. Section addresses come from heuristics, not from the document

There is no schema for a credit agreement. Section boundaries are found by pattern-matching
headings, and the patterns were tuned on a handful of documents. Two failure modes are known
and neither is fully solved:

- **Lettered lists that reach (h).** "(i)" is treated as roman one unless the previous
  paragraph was "(h)". A document that ends a lettered list at (h) and opens a roman
  sub-list immediately after will be read wrongly.
- **Documents whose markup produced no blank lines.** Heading detection leans on a heading
  being set off from surrounding text. Where that signal is absent the segmenter falls back
  to relaxed rules, which admit false positives — cross-references and wrapped lines can
  appear as sections. The fallback is reported in the warnings, never applied silently.

Two false positives that reached a realistic document before being caught: a financial
ratio wrapped onto its own line ("4.00 to 1.00;") parsed as a section, and a wrapped
cross-reference ("Section 7.03(b) and subject to...") parsed as the heading of 7.03. Both
are now regression-tested. Assume others remain. `corpus sections --check` exists so they
are found across the corpus rather than in one item at a time.

## 5. This measures document comprehension, not deployment safety

A system scoring well here has demonstrated that it can read a contract and cite it
accurately. It has *not* demonstrated that it is safe to deploy: nothing here tests
authorisation limits, escalation, monitoring over time, behaviour under data drift, or what
happens when the system is wrong and nobody notices. Those are separate controls and this
harness does not stand in for them.

<!-- Add to this list as you find things. A limitations page that stops growing has stopped
     being honest. -->
