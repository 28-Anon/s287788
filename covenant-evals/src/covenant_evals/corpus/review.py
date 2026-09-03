"""Walking through candidate documents one at a time, deciding what stays.

`corpus bootstrap` produces a list; a list is not a corpus. Somebody has to open each
document, decide whether it is really a credit agreement, work out which law governs it and
write down why it is in the corpus. That is a judgement task, and the honest interface for a
judgement task is one thing at a time with the source in front of you.

So this opens each candidate in your browser — where a filing is actually readable, with its
tables and formatting intact — and asks four questions in the terminal. It writes the
manifest as it goes, so quitting halfway keeps the decisions already made.

Input and browser-opening are injected, so the whole flow is testable without a terminal or
a browser.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .manifest import Agreement, Manifest

PROVISIONAL = "PROVISIONAL"

#: Printed once, before the first document. The decision is quick and reversible, and
#: people agonise over quick reversible decisions when nobody tells them not to.
ORIENTATION = (
    "",
    "This is a SKIM, not a read. About a minute each. You are answering one question:",
    "is this the actual loan contract, or something attached to one?",
    "",
    "  KEEP   long (100+ pages), has ARTICLE I..X, a definitions section, and a",
    "         'Negative Covenants' section. Titles: Credit Agreement, Facility",
    "         Agreement, Loan Agreement, Credit and Guaranty Agreement.",
    "",
    "  DROP   short; or an amendment, waiver, supplement, guarantee, security or",
    "         pledge agreement. Related to a loan, but not the contract itself.",
    "",
    "  SKIP   you cannot tell in a minute. It comes back next time.",
    "",
    "  QUIT   stop for now. Everything decided so far is saved.",
    "",
    "In the browser, Ctrl+F is the whole technique:",
    "  'Negative Covenants'  -> if it is missing, there is nothing to ask questions about",
    "  'governed by'         -> gives you the governing law in one hit",
    "",
    "Nothing here is final. You can drop a document later; the corpus is not fixed",
    "until you freeze the splits.",
    "",
)

LAW_CHOICES = {
    "1": "NY",
    "2": "English",
    "3": "Delaware",
    "4": "other",
    "": "",
}


@dataclass
class ReviewOutcome:
    kept: int = 0
    dropped: int = 0
    skipped: int = 0
    quit_early: bool = False


def needs_review(manifest: Manifest) -> list[Agreement]:
    """Candidates still carrying the note bootstrap gave them."""
    return [a for a in manifest.agreements if PROVISIONAL in a.note]


def review(
    manifest: Manifest,
    *,
    agreements: list[Agreement] | None = None,
    ask: Callable[[str], str] = input,
    say: Callable[[str], None] = print,
    open_url: Callable[[str], None] | None = None,
    save: Callable[[], None] | None = None,
) -> ReviewOutcome:
    """Walk the candidates. Returns what happened."""
    queue = agreements if agreements is not None else needs_review(manifest)
    outcome = ReviewOutcome()

    if not queue:
        say("nothing to review — every document has been through this already")
        return outcome

    for line in ORIENTATION:
        say(line)

    for index, agreement in enumerate(queue, start=1):
        say("")
        say("=" * 72)
        say(f"{index} of {len(queue)}   {agreement.ref}")
        say(f"  {agreement.company}   {agreement.form}   filed {agreement.filed}")
        say(f"  {agreement.note}")
        say(f"  {agreement.url()}")
        say("=" * 72)

        if open_url is not None:
            open_url(agreement.url())
            say("  (opened in your browser)")

        answer = ask("keep / drop / skip / quit  [k/d/s/q] ").strip().lower()[:1]

        if answer == "q":
            outcome.quit_early = True
            break

        if answer == "d":
            manifest.agreements.remove(agreement)
            outcome.dropped += 1
            say("  dropped")
            if save:
                save()
            continue

        if answer != "k":
            outcome.skipped += 1
            say("  skipped — it keeps its provisional note and will come up again")
            continue

        say(
            "  governing law:  1) NY   2) English   3) Delaware   4) other   (enter to leave blank)"
        )
        law = LAW_CHOICES.get(ask("  > ").strip(), "")
        agreement.governing_law = law

        note = ask("  why is this document in the corpus? ").strip()
        # Never leave the provisional note in place on something marked as reviewed: it
        # would read six weeks later as though the law had been checked when it had not.
        agreement.note = note or f"kept in review; governing law {law or 'not recorded'}"

        outcome.kept += 1
        say(f"  kept  [{law or 'law not recorded'}]")
        if save:
            save()

    return outcome


def summarise(outcome: ReviewOutcome, manifest: Manifest) -> str:
    lines = [
        "",
        f"kept {outcome.kept}, dropped {outcome.dropped}, skipped {outcome.skipped}",
    ]
    if outcome.quit_early:
        lines.append("stopped early — decisions already made are saved")

    remaining = len(needs_review(manifest))
    if remaining:
        lines.append(f"{remaining} still to review")

    english = sum(1 for a in manifest.agreements if a.governing_law == "English")
    if english < 5:
        lines.append(
            f"{english} English-law document(s) so far; the target is 5, and they are what "
            "make the London comparison possible"
        )

    return "\n".join(lines)
