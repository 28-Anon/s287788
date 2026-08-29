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
full-text search and what the labeller found interesting, and they are exclusively:
US-law-governed, English-language, filed by SEC registrants, and public. That excludes
private credit agreements that are never filed — which is precisely the segment the
downstream use case cares most about.

Results here should not be assumed to transfer to European facility agreements, to unfiled
private credit documents, or to non-English instruments.

## 3. Ground truth is a reading, not a legal opinion

For genuinely contested provisions, competent credit lawyers disagree. The intent is that
arguable questions never become items — but the labeller will not always recognise that a
question is arguable, which means some portion of the gold set encodes a confident answer to
a question that does not have one. Items found to be arguable are marked `disputed` and
excluded from headline scores rather than silently corrected.

## 4. This measures document comprehension, not deployment safety

A system scoring well here has demonstrated that it can read a contract and cite it
accurately. It has *not* demonstrated that it is safe to deploy: nothing here tests
authorisation limits, escalation, monitoring over time, behaviour under data drift, or what
happens when the system is wrong and nobody notices. Those are separate controls and this
harness does not stand in for them.

<!-- Add to this list as you find things. A limitations page that stops growing has stopped
     being honest. -->
