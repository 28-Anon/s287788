"""Scoring one answer against one item.

The headline metric is **grounded accuracy**, and it is deliberately strict:

    the answer is right
    AND the quote appears verbatim in the document
    AND the quote sits inside the section the item cites

A right answer with an invented citation scores zero. That is the whole opinion of this
project: nobody can act on an answer they cannot check, so an unverifiable answer has not
earned partial credit for being lucky.

The three components are also reported separately, because *how* something failed is the
useful part. A system that is right but cites badly needs different work from one that
cites well and reasons wrongly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..corpus.sections import find_spans, segment
from ..schema import Item

ABSTAIN = "INSUFFICIENT_INFORMATION"


@dataclass
class Grade:
    """How one answer scored, and why."""

    item_id: str
    answer_correct: bool
    citation_verbatim: bool
    citation_in_section: bool
    abstained: bool
    should_abstain: bool

    detail: str = ""

    @property
    def grounded(self) -> bool:
        """The headline. Correct and checkable, or it does not count."""
        if self.should_abstain:
            # Nothing to cite, so abstaining correctly is the whole test.
            return self.abstained
        return self.answer_correct and self.citation_verbatim and self.citation_in_section

    @property
    def wrong_when_should_abstain(self) -> bool:
        """The failure that matters most in a regulated setting: confident invention."""
        return self.should_abstain and not self.abstained


def _normalise_number(value: str) -> float | None:
    cleaned = re.sub(r"[,$£€\s]", "", value.strip())
    try:
        return float(cleaned)
    except ValueError:
        return None


def answers_match(given: str, item: Item) -> bool:
    """Is this the right answer, allowing for how a person would write it?

    Kept deliberately forgiving about *format* and strict about *content*: "false", "no"
    and "False" are the same answer, but "$35,000,000" and "$50,000,000" are not.
    """
    given = given.strip()

    if item.answer_type == "abstain":
        return given.upper() == ABSTAIN

    if item.answer_type == "boolean":
        lowered = given.lower().rstrip(".")
        if lowered in {"true", "yes", "y"}:
            return item.gold is True
        if lowered in {"false", "no", "n"}:
            return item.gold is False
        return False

    if item.answer_type == "numeric":
        number = _normalise_number(given)
        if number is None or not isinstance(item.gold, (int, float)):
            return False
        # Relative tolerance, so 35000000.0 and 35,000,000 agree and 35m and 50m do not.
        return abs(number - float(item.gold)) <= max(1e-9, abs(float(item.gold)) * 1e-9)

    if isinstance(item.gold, str):
        return given.casefold() == item.gold.strip().casefold()

    return False


def grade(item: Item, answer: str, quote: str, document: str) -> Grade:
    """Score one answer. Pure — no network, no model, reproducible from stored results."""
    should_abstain = item.answer_type == "abstain"
    abstained = answer.strip().upper() == ABSTAIN
    correct = answers_match(answer, item)

    if should_abstain:
        return Grade(
            item_id=item.id,
            answer_correct=abstained,
            citation_verbatim=True,
            citation_in_section=True,
            abstained=abstained,
            should_abstain=True,
            detail="" if abstained else f"answered {answer!r} where the document does not say",
        )

    spans = find_spans(document, quote) if quote.strip() else []
    verbatim = bool(spans)

    in_section = False
    detail = ""

    if not verbatim:
        detail = "quote does not appear in the document" if quote.strip() else "no quote given"
    else:
        section = segment(document).find(item.section)
        if section is None:
            # The item's own section could not be resolved; do not punish the system for it.
            in_section = True
            detail = f"section {item.section} did not resolve — citation position unchecked"
        else:
            in_section = any(section.start <= start < section.end for start, _ in spans)
            if not in_section:
                detail = f"quote is real but outside section {item.section}"

    if correct and not verbatim:
        # Two different failure modes, and the taxonomy will want to tell them apart: a
        # system that fabricates support is not the same as one that offers none.
        label = "NO CITATION" if not quote.strip() else "INVENTED CITATION"
        detail = f"RIGHT ANSWER, {label} — scores zero. " + detail

    return Grade(
        item_id=item.id,
        answer_correct=correct,
        citation_verbatim=verbatim,
        citation_in_section=in_section,
        abstained=abstained,
        should_abstain=False,
        detail=detail,
    )


def summarise(grades: list[Grade]) -> dict[str, object]:
    """Aggregate a run. Rates only — confidence intervals arrive in week 10."""
    if not grades:
        return {"items": 0}

    total = len(grades)
    answerable = [g for g in grades if not g.should_abstain]
    abstainable = [g for g in grades if g.should_abstain]

    return {
        "items": total,
        "grounded_accuracy": sum(g.grounded for g in grades) / total,
        "answer_accuracy": sum(g.answer_correct for g in grades) / total,
        "citation_verbatim": (
            sum(g.citation_verbatim for g in answerable) / len(answerable) if answerable else None
        ),
        "citation_in_section": (
            sum(g.citation_in_section for g in answerable) / len(answerable) if answerable else None
        ),
        "wrong_when_should_abstain": (
            sum(g.wrong_when_should_abstain for g in abstainable) / len(abstainable)
            if abstainable
            else None
        ),
    }
