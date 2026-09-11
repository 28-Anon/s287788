"""A synthetic agreement and four items, for demonstrating the loop end to end.

**This is not data.** It is not in the manifest, not in any split, and no result from it
means anything. It exists so the whole path — document in, model answers, answer scored —
can be run and watched before there is a corpus or a single real label.

The four items are chosen to show the four things the scorer distinguishes: a
straightforward lookup, a cap that has to be compared against a number, a definition that
points at another definition, and a question the agreement simply does not answer.
"""

from __future__ import annotations

from datetime import date

from ..corpus.normalise import sha256_text
from ..corpus.sections import find_spans
from ..schema import Item

DOCUMENT = """ARTICLE I

DEFINITIONS

SECTION 1.01. Defined Terms.

"Consolidated EBITDA" means, for any period, Consolidated Net Income for such period plus,
without duplication, interest expense, taxes, depreciation and amortisation for such
period, in each case determined in accordance with GAAP.

"Free and Clear Amount" means the greater of $35,000,000 and 25% of Consolidated EBITDA
for the most recently ended Test Period.

"Restricted Subsidiary" means any Subsidiary other than an Unrestricted Subsidiary.

"Test Period" means the four consecutive fiscal quarters most recently ended for which
financial statements have been delivered.

ARTICLE VII

NEGATIVE COVENANTS

SECTION 7.01. Indebtedness.

The Borrower shall not, and shall not permit any Restricted Subsidiary to, create, incur,
assume or suffer to exist any Indebtedness, except:

(a) Indebtedness existing on the Closing Date and set forth on Schedule 7.01;

(b) Indebtedness in respect of Incremental Term Loans in an aggregate principal amount not
to exceed the Free and Clear Amount, provided that no Default has occurred and is
continuing;

(c) Indebtedness of any Restricted Subsidiary owing to the Borrower.

SECTION 7.02. Liens.

The Borrower shall not create, incur, assume or suffer to exist any Lien upon any of its
property, whether now owned or hereafter acquired, except Permitted Liens.

SECTION 7.03. Restricted Payments.

The Borrower shall not declare or make any Restricted Payment, except that the Borrower may
make Restricted Payments in an aggregate amount not to exceed $10,000,000 in any fiscal
year so long as the Consolidated Leverage Ratio does not exceed 3.50 to 1.00.
"""

DOC_SHA = sha256_text(DOCUMENT)


def _cite(quote: str) -> tuple[str, list[int]]:
    """Locate a quote and return the document's own text for it, plus the span.

    The searched-for string and the stored citation are not always the same: a quote that
    crosses a line break matches whitespace-tolerantly but the document holds a newline
    where the search had a space. The citation must be what the document actually says,
    which is exactly what `items new` stores.
    """
    spans = find_spans(DOCUMENT, quote)
    if len(spans) != 1:
        raise AssertionError(f"fixture quote is not unique in the document: {quote!r}")
    start, end = spans[0]
    return DOCUMENT[start:end], [start, end]


def items() -> list[Item]:
    """Four hand-written items against the synthetic agreement above."""
    common = dict(
        doc="FIXTURE-00-000000",
        doc_sha256=DOC_SHA,
        labelled_by="fixture",
        labelled_at=date(2026, 9, 3),
        review_status="double_checked",
    )

    incremental_text, incremental_span = _cite("not to exceed the Free and Clear Amount")
    basket_text, basket_span = _cite("the greater of $35,000,000 and 25% of Consolidated EBITDA")
    leverage_text, leverage_span = _cite(
        "the Consolidated Leverage Ratio does not exceed 3.50 to 1.00"
    )

    return [
        Item(
            id="fixture-001",
            section="7.01(b)",
            question=(
                "May the Borrower incur $50,000,000 of Incremental Term Loans without "
                "lender consent, assuming Consolidated EBITDA of $100,000,000?"
            ),
            answer_type="boolean",
            gold=False,
            gold_citation=incremental_text,
            gold_span=incremental_span,
            rationale=(
                "The cap is the Free and Clear Amount, defined as the greater of $35m and "
                "25% of Consolidated EBITDA. On $100m of EBITDA that is $35m, below the "
                "$50m requested."
            ),
            difficulty="hard",
            traps=["defined_term_chain", "basket_cap"],
            **common,
        ),
        Item(
            id="fixture-002",
            section="1.01",
            question="What is the fixed dollar component of the Free and Clear Amount?",
            answer_type="numeric",
            gold=35_000_000,
            unit="USD",
            gold_citation=basket_text,
            gold_span=basket_span,
            rationale="The definition states the greater of $35,000,000 and a percentage.",
            difficulty="easy",
            traps=["basket_cap"],
            **common,
        ),
        Item(
            id="fixture-003",
            section="7.03",
            question=(
                "What is the maximum Consolidated Leverage Ratio permitted while making "
                "Restricted Payments?"
            ),
            answer_type="numeric",
            gold=3.5,
            unit="ratio",
            gold_citation=leverage_text,
            gold_span=leverage_span,
            rationale="Section 7.03 conditions Restricted Payments on that ratio.",
            difficulty="medium",
            traps=["numeric_unit_confusion"],
            **common,
        ),
        Item(
            id="fixture-004",
            section="7.01",
            question="What default interest rate applies after an Event of Default?",
            answer_type="abstain",
            gold=None,
            gold_citation=None,
            gold_span=None,
            rationale=(
                "The agreement contains no default interest provision. A realistic question "
                "a credit analyst would ask, which this document simply does not answer."
            ),
            difficulty="hard",
            traps=["not_in_document"],
            **common,
        ),
    ]
