"""The item schema.

An *item* is one labelled question about one credit agreement, with the answer and the
exact text in the document that justifies it.

This schema is PROVISIONAL until week 4. Once it is frozen, changing it means re-checking
every item already labelled against it, so change it freely now and reluctantly later.

Deliberately no third-party validation library. The rules below are the whole contract and
you should be able to read them in one sitting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

ANSWER_TYPES = frozenset({"boolean", "numeric", "enum", "date", "abstain"})

DIFFICULTIES = frozenset({"easy", "medium", "hard"})

REVIEW_STATUSES = frozenset({"single", "double_checked", "disputed"})

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
    """One labelled question.

    Attributes mirror the YAML files in data/items/ one-for-one.
    """

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


def validate(item: Item) -> list[str]:
    """Return a list of human-readable problems. An empty list means the item is valid.

    Returning errors rather than raising is deliberate: CI should be able to report every
    broken item in one pass instead of stopping at the first one.
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

    # --- the answer must match its declared type --------------------------------
    if item.answer_type == "boolean":
        require(isinstance(item.gold, bool), "answer_type 'boolean' requires gold to be true/false")
    elif item.answer_type == "numeric":
        require(
            isinstance(item.gold, (int, float)) and not isinstance(item.gold, bool),
            "answer_type 'numeric' requires gold to be a number",
        )
    elif item.answer_type in {"enum", "date"}:
        require(
            isinstance(item.gold, str) and bool(item.gold.strip()),
            f"answer_type '{item.answer_type}' requires gold to be a non-empty string",
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
