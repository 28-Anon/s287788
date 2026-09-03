"""The item schema. **Frozen as of week 4.**

An *item* is one labelled question about one credit agreement, with the answer and the
exact text in the document that justifies it.

Frozen means: changing anything below invalidates every item already labelled against it.
The change protocol, which exists so that a five-minute edit cannot quietly cost you
weeks of labelling:

1. Bump SCHEMA_VERSION.
2. Update the field list in tests/test_schema.py::test_the_schema_is_frozen, which fails
   on any silent addition or removal.
3. Re-run `covenant-evals items check` and fix every item the change breaks.
4. Write down in docs/METHODOLOGY.md what changed and why.

Deliberately no third-party validation library. The rules below are the whole contract and
you should be able to read them in one sitting.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

ANSWER_TYPES = frozenset({"boolean", "numeric", "enum", "date", "abstain"})

DIFFICULTIES = frozenset({"easy", "medium", "hard"})

REVIEW_STATUSES = frozenset({"single", "double_checked", "disputed"})

#: Units for numeric answers. A bare number is ambiguous — "35" could be millions, a
#: percentage, or a ratio — and an eval that cannot tell those apart cannot mark them.
UNITS = frozenset(
    {
        "USD",
        "GBP",
        "EUR",
        "percent",
        "ratio",
        "days",
        "months",
        "years",
        "count",
    }
)

#: Why an item is hard. The failure taxonomy in docs/TAXONOMY.md grows out of these, so
#: add a trap here before you use it, and give each one at least three items.
TRAPS = frozenset(
    {
        "defined_term_chain",  # the answer depends on a definition that cites another definition
        "amendment_supersession",  # a later filing changes the answer
        "basket_cap",  # a permitted amount is capped by a formula
        "carve_out",  # the prohibition has an exception that reverses the answer
        "cross_reference",  # the clause points elsewhere in the document
        "negative_covenant_inversion",  # the covenant forbids, so "may X" flips
        "numeric_unit_confusion",  # millions vs thousands, or a percentage of what
        "not_in_document",  # the honest answer is "this document does not say"
        "injected_instruction",  # the document text contains something aimed at a reader/model
    }
)


@dataclass
class Item:
    """One labelled question. Fields mirror the YAML files in data/items/ one-for-one."""

    id: str
    doc: str  # EDGAR accession number, e.g. "0000950170-24-012345"
    doc_sha256: str  # pins the exact normalised text this label was made against
    section: str  # human-locatable provenance, e.g. "7.02(b)"
    question: str
    answer_type: str
    gold: bool | float | str | None
    gold_citation: str | None
    gold_span: list[int] | None  # [start, end] character offsets into the normalised text
    rationale: str
    difficulty: str
    labelled_by: str
    labelled_at: date
    review_status: str = "single"
    traps: list[str] = field(default_factory=list)

    #: Required for numeric answers. "35000000" means nothing without knowing whether it is
    #: dollars, pounds or a percentage of EBITDA.
    unit: str = ""

    #: Required for enum answers: the closed set the answer is drawn from. Without it,
    #: "enum" is just an unscoreable free-text field.
    enum_options: list[str] = field(default_factory=list)

    #: Why this item is marked disputed. Disputed items are excluded from headline scores
    #: rather than deleted — a question that turned out to be arguable is itself a finding.
    dispute_note: str = ""


FIELD_NAMES = tuple(f.name for f in fields(Item))


def validate(item: Item) -> list[str]:
    """Return a list of human-readable problems. An empty list means the item is valid.

    Returning errors rather than raising is deliberate: CI should be able to report every
    broken item in one pass instead of stopping at the first one.

    This checks the item against *itself*. Checking it against the document it cites is a
    separate pass — see items.cross_validate — because that one needs the corpus on disk.
    """
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    # --- identity and provenance ------------------------------------------------
    require(bool(item.id.strip()), "id must not be empty")
    require(bool(item.doc.strip()), "doc (EDGAR accession) must not be empty")
    require(len(item.doc_sha256) == 64, "doc_sha256 must be a 64-character SHA-256 hex digest")
    require(
        bool(item.section.strip()),
        "section must not be empty — every item cites a section, no section no item",
    )

    # --- the question and the reasoning ----------------------------------------
    require(len(item.question.strip()) >= 10, "question is too short to be a real question")
    require(
        len(item.rationale.strip()) >= 20,
        "rationale must explain why the gold answer follows from the citation",
    )

    # --- controlled vocabularies ------------------------------------------------
    require(item.answer_type in ANSWER_TYPES, f"answer_type must be one of {sorted(ANSWER_TYPES)}")
    require(item.difficulty in DIFFICULTIES, f"difficulty must be one of {sorted(DIFFICULTIES)}")
    require(
        item.review_status in REVIEW_STATUSES,
        f"review_status must be one of {sorted(REVIEW_STATUSES)}",
    )
    unknown_traps = sorted(set(item.traps) - TRAPS)
    require(not unknown_traps, f"unknown traps {unknown_traps} — add them to TRAPS first")

    if item.review_status == "disputed":
        require(
            bool(item.dispute_note.strip()),
            "a disputed item must record why it is disputed — that note is the finding",
        )

    # --- the answer must match its declared type --------------------------------
    if item.answer_type == "boolean":
        require(isinstance(item.gold, bool), "answer_type 'boolean' requires gold to be true/false")
    elif item.answer_type == "numeric":
        require(
            isinstance(item.gold, (int, float)) and not isinstance(item.gold, bool),
            "answer_type 'numeric' requires gold to be a number",
        )
        require(
            item.unit in UNITS,
            f"numeric answers need a unit, one of {sorted(UNITS)} — a bare number is ambiguous",
        )
    elif item.answer_type == "enum":
        require(
            isinstance(item.gold, str) and bool(item.gold.strip()),
            "answer_type 'enum' requires gold to be a non-empty string",
        )
        require(len(item.enum_options) >= 2, "an enum needs at least two options to choose between")
        if item.enum_options and isinstance(item.gold, str):
            require(
                item.gold in item.enum_options,
                f"gold {item.gold!r} is not one of enum_options {item.enum_options}",
            )
    elif item.answer_type == "date":
        require(
            isinstance(item.gold, str) and bool(item.gold.strip()),
            "answer_type 'date' requires gold to be a non-empty string",
        )
    elif item.answer_type == "abstain":
        require(
            item.gold is None,
            "answer_type 'abstain' means the document does not answer it — gold must be null",
        )
        require(
            "not_in_document" in item.traps,
            "abstain items must carry the 'not_in_document' trap",
        )

    if item.answer_type != "numeric":
        require(not item.unit, "unit only applies to numeric answers")
    if item.answer_type != "enum":
        require(not item.enum_options, "enum_options only applies to enum answers")

    # --- citations: the whole point of the project ------------------------------
    if item.answer_type == "abstain":
        require(
            item.gold_citation is None and item.gold_span is None,
            "abstain items have nothing to cite — leave gold_citation and gold_span null",
        )
    else:
        require(
            bool(item.gold_citation and item.gold_citation.strip()),
            "every answerable item needs the verbatim text that justifies it",
        )
        if item.gold_span is None:
            errors.append("every answerable item needs gold_span character offsets")
        else:
            require(len(item.gold_span) == 2, "gold_span must be exactly [start, end]")
            if len(item.gold_span) == 2:
                start, end = item.gold_span
                require(start >= 0, "gold_span start must not be negative")
                require(end > start, "gold_span end must be greater than start")

    return errors
