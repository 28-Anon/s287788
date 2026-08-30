# Items

One labelled question per file, named `cov-NNNN.yaml`.

**Empty until week 4.** The schema is not frozen until then, and labelling against a schema
you are still changing wastes the labelling.

The format is in `docs/example-item.yaml`, and the rules that file must satisfy are in
`src/covenant_evals/schema.py`. Run `make validate` after adding any item.

## The two rules that matter more than the schema

1. **Label before you look.** Write the gold answer before you have seen any model output on
   that question. A label written after seeing an answer is contaminated and quietly
   invalidates every number computed from it.
2. **No section, no item.** If you cannot say which clause the answer comes from, the item
   is not ready.

## How to fill in gold_span

Do not count characters by hand. Copy the sentence you want to cite and ask the code:

```bash
make corpus-locate REF=0000950170-24-012345 Q='not to exceed the greater of $35,000,000'
```

It prints a `gold_span: [start, end]` line to paste in, and tells you which section the
quote sits in. If it reports more than one match, your citation is **ambiguous** — quote
more context until there is exactly one, or the span you record may not be the passage you
meant.

To read a whole section before writing questions about it:

```bash
make corpus-section REF=0000950170-24-012345 ADDR='7.02(b)'
```
