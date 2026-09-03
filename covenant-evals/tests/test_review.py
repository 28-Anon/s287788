"""Tests for the review flow and the HTML corpus report.

Input, output and browser-opening are all injected, so the interactive flow is tested
without a terminal.
"""

from covenant_evals.corpus.manifest import Agreement, Manifest
from covenant_evals.corpus.normalise import sha256_text
from covenant_evals.corpus.report import build
from covenant_evals.corpus.review import needs_review, review, summarise

DOC = """ARTICLE VII

NEGATIVE COVENANTS

SECTION 7.01. Indebtedness.

The Borrower shall not incur Indebtedness.

SECTION 7.02. Liens.

The Borrower shall not create any Lien.
"""


def candidate(
    index: int = 1, note: str = "candidate found by X — PROVISIONAL, confirm"
) -> Agreement:
    return Agreement(
        accession=f"0000950170-24-{index:06d}",
        filename="ex101.htm",
        cik="320123",
        company=f"Company {index}",
        form="8-K",
        filed="2024-03-04",
        note=note,
    )


def scripted(answers):
    """An `ask` that plays a list of replies, and records the prompts it was given."""
    replies = list(answers)
    asked = []

    def ask(prompt):
        asked.append(prompt)
        return replies.pop(0) if replies else "q"

    return ask, asked


def run(manifest, answers, **kwargs):
    ask, asked = scripted(answers)
    said = []
    outcome = review(manifest, ask=ask, say=said.append, **kwargs)
    return outcome, said, asked


# -- the queue -------------------------------------------------------------------


def test_only_provisional_entries_need_review():
    manifest = Manifest()
    manifest.add(candidate(1))
    manifest.add(candidate(2, note="checked: US leveraged loan, NY law"))
    assert [a.accession for a in needs_review(manifest)] == ["0000950170-24-000001"]


def test_nothing_to_review_says_so():
    outcome, said, _ = run(Manifest(), [])
    assert outcome.kept == 0
    assert any("nothing to review" in line for line in said)


# -- decisions -------------------------------------------------------------------


def test_keeping_records_the_law_and_replaces_the_provisional_note():
    manifest = Manifest()
    manifest.add(candidate(1))
    outcome, _, _ = run(manifest, ["k", "2", "LMA-style, sponsor-backed, English law"])

    kept = manifest.agreements[0]
    assert outcome.kept == 1
    assert kept.governing_law == "English"
    assert kept.note == "LMA-style, sponsor-backed, English law"
    assert "PROVISIONAL" not in kept.note


def test_a_kept_document_never_keeps_its_provisional_note_even_with_no_note_given():
    # Otherwise it reads six weeks later as though the law had been checked when it had not.
    manifest = Manifest()
    manifest.add(candidate(1))
    run(manifest, ["k", "1", ""])
    assert "PROVISIONAL" not in manifest.agreements[0].note
    assert "NY" in manifest.agreements[0].note


def test_dropping_removes_it_from_the_manifest():
    manifest = Manifest()
    manifest.add(candidate(1))
    manifest.add(candidate(2))
    outcome, _, _ = run(manifest, ["d", "q"])

    assert outcome.dropped == 1
    assert len(manifest.agreements) == 1


def test_skipping_leaves_it_to_come_up_again():
    manifest = Manifest()
    manifest.add(candidate(1))
    outcome, _, _ = run(manifest, ["s"])

    assert outcome.skipped == 1
    assert len(needs_review(manifest)) == 1


def test_quitting_stops_but_keeps_what_was_already_decided():
    manifest = Manifest()
    for index in (1, 2, 3):
        manifest.add(candidate(index))

    outcome, _, _ = run(manifest, ["k", "1", "first one, checked", "q"])

    assert outcome.quit_early
    assert outcome.kept == 1
    assert len(needs_review(manifest)) == 2


def test_each_decision_is_saved_immediately():
    # Quitting halfway must not lose the decisions already made.
    manifest = Manifest()
    manifest.add(candidate(1))
    manifest.add(candidate(2))
    saves = []
    run(manifest, ["k", "1", "kept", "d"], save=lambda: saves.append(1))
    assert len(saves) == 2


def test_the_filing_is_opened_in_the_browser():
    manifest = Manifest()
    manifest.add(candidate(1))
    opened = []
    run(manifest, ["s"], open_url=opened.append)
    assert opened == ["https://www.sec.gov/Archives/edgar/data/320123/000095017024000001/ex101.htm"]


def test_the_summary_nags_about_english_law_documents():
    manifest = Manifest()
    manifest.add(candidate(1))
    outcome, _, _ = run(manifest, ["k", "1", "US deal"])
    assert "English-law" in summarise(outcome, manifest)


# -- the HTML report -------------------------------------------------------------


def fetched(manifest, tmp_path, text=DOC, **kwargs):
    agreement = candidate(**kwargs) if kwargs else candidate(1)
    agreement.text_sha256 = sha256_text(text)
    agreement.char_count = len(text)
    path = agreement.text_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    manifest.add(agreement)
    return agreement


def test_report_lists_documents_and_their_sections(tmp_path):
    manifest = Manifest()
    fetched(manifest, tmp_path)
    page = build(manifest, cache_dir=tmp_path)

    assert "Company 1" in page
    assert "3 sections" in page
    assert "7.01" in page and "7.02" in page


def test_report_flags_a_document_with_no_sections_and_says_why(tmp_path):
    manifest = Manifest()
    fetched(manifest, tmp_path, text="Plain prose with no headings whatsoever.\n" * 40)
    page = build(manifest, cache_dir=tmp_path)

    assert "no sections" in page
    assert "nothing matched any heading pattern" in page


def test_report_flags_unchecked_law_and_unreviewed_documents(tmp_path):
    manifest = Manifest()
    fetched(manifest, tmp_path)
    page = build(manifest, cache_dir=tmp_path)

    assert "law unchecked" in page
    assert "not reviewed" in page


def test_report_escapes_document_text(tmp_path):
    # Filing text is not ours and must never be trusted into the page unescaped.
    manifest = Manifest()
    agreement = fetched(manifest, tmp_path)
    agreement.company = "<script>alert('xss')</script>"
    page = build(manifest, cache_dir=tmp_path)

    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_report_handles_an_empty_manifest():
    assert "Nothing in the manifest yet" in build(Manifest())


def test_report_handles_a_document_that_was_never_fetched():
    manifest = Manifest()
    manifest.add(candidate(1))
    assert "not fetched" in build(manifest)


def test_the_rules_are_printed_before_the_first_document():
    # The command has to be usable without going back to the docs to remember what
    # "keep" means.
    manifest = Manifest()
    manifest.add(candidate(1))
    _outcome, said, _ = run(manifest, ["s"])
    joined = "\n".join(said)

    assert "SKIM, not a read" in joined
    assert "Negative Covenants" in joined
    assert "governed by" in joined


def test_the_rules_are_not_printed_when_there_is_nothing_to_do():
    _outcome, said, _ = run(Manifest(), [])
    assert "SKIM" not in "\n".join(said)
