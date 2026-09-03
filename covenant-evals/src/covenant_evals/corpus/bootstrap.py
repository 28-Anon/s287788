"""Assemble a candidate corpus in one command.

Building 25 documents by hand is a search, then twenty-five `corpus add` calls each needing
an accession and a CIK copied across correctly, then a fetch. That is roughly thirty
commands and the copying is exactly the kind of work people get wrong at item nineteen.

This runs several searches, discards the amendments and waivers, ranks what is left, takes a
balanced slice and writes them all to the manifest. Two commands total: bootstrap, then
fetch.

**It does not decide what your corpus is.** Selection is the largest single source of bias
in the results — `docs/LIMITATIONS.md` says so — and a candidate list assembled by keyword
is a starting point, not a decision. Review what it added, delete what does not belong, and
write a real note on each one you keep.
"""

from __future__ import annotations

from dataclasses import dataclass

from .edgar import EdgarClient, EdgarError, Hit, is_derivative, looks_like_agreement
from .fetch import agreement_from_hit
from .manifest import Agreement, Manifest

#: Phrases that appear in the *body* of a credit agreement, paired with the drafting
#: tradition they point at. A phrase from the body beats one from the title: every
#: amendment has "Credit Agreement" in its name, but only an agreement defines its own
#: majority-lender mechanics.
DEFAULT_QUERIES: tuple[tuple[str, str], ...] = (
    ('"Required Lenders"', "NY"),
    ('"Consolidated EBITDA"', ""),
    ('"Majority Lenders"', "English"),
    ('"Finance Parties"', "English"),
    ('"Permitted Liens"', ""),
)


@dataclass
class Candidate:
    hit: Hit
    query: str
    law_hint: str

    @property
    def note(self) -> str:
        hint = f", probably {self.law_hint} law" if self.law_hint else ""
        return (
            f"candidate found by {self.query}{hint} — PROVISIONAL, "
            "confirm by reading and replace this note"
        )


def gather(
    client: EdgarClient,
    *,
    queries: tuple[tuple[str, str], ...] = DEFAULT_QUERIES,
    forms: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    per_query: int = 40,
) -> list[Candidate]:
    """Run every query, drop derivatives and duplicates, keep the best of each query.

    Results are interleaved round-robin rather than ranked globally, so every query is
    represented. A global ranking would let one phrase dominate, and the point of using
    several is to get both drafting traditions.
    """
    by_query: list[list[Candidate]] = []
    seen: set[str] = set()

    for query, law_hint in queries:
        try:
            hits = client.search(
                query, forms=forms, start_date=start_date, end_date=end_date, limit=per_query
            )
        except EdgarError:
            # One failed query must not lose the four that worked.
            by_query.append([])
            continue

        kept = [hit for hit in hits if not is_derivative(hit) and looks_like_agreement(hit) > 0]
        kept.sort(key=lambda hit: hit.filed, reverse=True)
        kept.sort(key=looks_like_agreement, reverse=True)

        unique: list[Candidate] = []
        for hit in kept:
            if hit.ref in seen:
                continue
            seen.add(hit.ref)
            unique.append(Candidate(hit=hit, query=query, law_hint=law_hint))
        by_query.append(unique)

    interleaved: list[Candidate] = []
    for index in range(max((len(group) for group in by_query), default=0)):
        for group in by_query:
            if index < len(group):
                interleaved.append(group[index])

    return interleaved


def to_agreements(candidates: list[Candidate]) -> list[Agreement]:
    """Turn candidates into manifest entries.

    `governing_law` is left **empty**, deliberately, even though the query that found a
    document hints at it. A guess recorded in the same field as a checked fact is
    indistinguishable from one later, and the English-law comparison is a headline result.
    The hint goes in the note, where it reads as what it is.
    """
    return [agreement_from_hit(c.hit, note=c.note) for c in candidates]


def bootstrap(
    client: EdgarClient,
    manifest: Manifest,
    *,
    count: int = 25,
    queries: tuple[tuple[str, str], ...] = DEFAULT_QUERIES,
    forms: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[Agreement], int]:
    """Add up to `count` new candidates to the manifest. Returns (added, already_present)."""
    candidates = gather(
        client, queries=queries, forms=forms, start_date=start_date, end_date=end_date
    )

    added: list[Agreement] = []
    already = 0

    for agreement in to_agreements(candidates):
        if len(added) >= count:
            break
        if manifest.get(agreement.ref) is not None:
            already += 1
            continue
        manifest.add(agreement)
        added.append(agreement)

    return added, already
