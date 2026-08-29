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
