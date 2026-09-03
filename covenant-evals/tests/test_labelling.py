"""Tests for writing items and checking them against the documents they cite.

Cross-validation is the safety net for the errors that actually happen while labelling:
a quote pasted from the wrong section, a span copied from the previous item, a document
re-fetched after the label was written. Each of those is tested here.
"""

from datetime import date

import pytest

from covenant_evals.corpus.manifest import Agreement, Manifest
from covenant_evals.corpus.normalise import sha256_text
from covenant_evals.corpus.sections import find_spans
from covenant_evals.items import (
    cross_validate,
    item_to_yaml,
    load_item,
    next_item_id,
    stats,
    write_item,
)
from covenant_evals.schema import Item, validate

DOC = """ARTICLE VII

NEGATIVE COVENANTS

SECTION 7.01. Indebtedness.

The Borrower shall not incur Indebtedness, except:

(a) Indebtedness existing on the Closing Date;

(b) Indebtedness in an aggregate principal amount not to exceed the greater of
$35,000,000 and 25% of Consolidated EBITDA.

SECTION 7.02. Liens.

The Borrower shall not create any Lien upon any of its property.
"""

QUOTE = "not to exceed the greater of\n$35,000,000"


@pytest.fixture
def corpus(tmp_path):
    """A one-document corpus on disk, with a manifest that matches it."""
    agreement = Agreement(
        accession="0000950170-24-012345",
        filename="ex101.htm",
        cik="320123",
        company="Acme Corp",
        form="EX-10.1",
        filed="2024-03-04",
        governing_law="NY",
    )
    agreement.text_sha256 = sha256_text(DOC)
    agreement.char_count = len(DOC)

    path = agreement.text_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DOC, encoding="utf-8")

    manifest = Manifest()
    manifest.add(agreement)
    return manifest, tmp_path, agreement


def make_item(agreement, **overrides) -> Item:
    span = find_spans(DOC, QUOTE)[0]
    defaults = dict(
        id="cov-0001",
        doc=agreement.accession,
        doc_sha256=agreement.text_sha256,
        section="7.01(b)",
        question="May the Borrower incur $50,000,000 of incremental term loans?",
        answer_type="boolean",
        gold=False,
        gold_citation=DOC[span[0] : span[1]],
        gold_span=[span[0], span[1]],
        rationale="The basket caps incremental facilities below the requested figure.",
        difficulty="hard",
        labelled_by="SM",
        labelled_at=date(2026, 10, 4),
        traps=["basket_cap"],
    )
    defaults.update(overrides)
    return Item(**defaults)


# -- cross-validation: the checks that catch real labelling mistakes --------------


def test_a_correctly_labelled_item_passes(corpus):
    manifest, cache, agreement = corpus
    item = make_item(agreement)
    assert validate(item) == []
    assert cross_validate([item], manifest, cache_dir=cache) == {}


def test_a_changed_document_is_caught(corpus):
    manifest, cache, agreement = corpus
    item = make_item(agreement, doc_sha256="b" * 64)
    problems = cross_validate([item], manifest, cache_dir=cache)
    assert any("has changed since this item was labelled" in m for m in problems["cov-0001"])


def test_a_section_that_does_not_exist_is_caught(corpus):
    manifest, cache, agreement = corpus
    item = make_item(agreement, section="9.99")
    problems = cross_validate([item], manifest, cache_dir=cache)
    assert any("does not resolve" in m for m in problems["cov-0001"])


def test_offsets_that_do_not_hold_the_quote_are_caught(corpus):
    manifest, cache, agreement = corpus
    item = make_item(agreement, gold_span=[0, 40])
    problems = cross_validate([item], manifest, cache_dir=cache)
    assert any("not at gold_span" in m for m in problems["cov-0001"])


def test_a_quote_from_the_wrong_section_is_caught(corpus):
    # The quote is real, the offsets are right, the section is wrong. This item looks
    # perfect and teaches the wrong lesson, which is why the check exists.
    manifest, cache, agreement = corpus
    span = find_spans(DOC, "shall not create any Lien")[0]
    item = make_item(
        agreement,
        section="7.01(b)",
        gold_citation=DOC[span[0] : span[1]],
        gold_span=[span[0], span[1]],
    )
    problems = cross_validate([item], manifest, cache_dir=cache)
    assert any("sits outside section 7.01(b)" in m for m in problems["cov-0001"])


def test_an_item_citing_a_document_not_in_the_manifest_is_caught(corpus):
    manifest, cache, agreement = corpus
    item = make_item(agreement, doc="0000000000-00-000000")
    problems = cross_validate([item], manifest, cache_dir=cache)
    assert any("not in the manifest" in m for m in problems["cov-0001"])


def test_an_unfetched_document_is_caught(corpus, tmp_path):
    manifest, _cache, agreement = corpus
    empty = tmp_path / "empty-cache"
    problems = cross_validate([make_item(agreement)], manifest, cache_dir=empty)
    assert any("not in the cache" in m for m in problems["cov-0001"])


def test_abstain_items_skip_the_citation_checks(corpus):
    manifest, cache, agreement = corpus
    item = make_item(
        agreement,
        answer_type="abstain",
        gold=None,
        gold_citation=None,
        gold_span=None,
        traps=["not_in_document"],
        section="7.01",
    )
    assert validate(item) == []
    assert cross_validate([item], manifest, cache_dir=cache) == {}


# -- writing ---------------------------------------------------------------------


def test_next_item_id_starts_at_one(tmp_path):
    assert next_item_id(tmp_path) == "cov-0001"


def test_next_item_id_skips_files_already_present(tmp_path):
    (tmp_path / "cov-0001.yaml").write_text("id: cov-0001\n")
    (tmp_path / "cov-0007.yaml").write_text("id: cov-0007\n")
    assert next_item_id(tmp_path) == "cov-0008"


def test_deleting_an_item_does_not_free_its_id(corpus, tmp_path):
    # Stored run results refer to items by id. Handing cov-0002 to a different question
    # later would silently corrupt every comparison against those runs.
    _manifest, _cache, agreement = corpus
    items_dir = tmp_path / "items"

    first = write_item(make_item(agreement, id="cov-0001"), items_dir)
    write_item(make_item(agreement, id="cov-0002"), items_dir)
    assert next_item_id(items_dir) == "cov-0003"

    first.unlink()
    (items_dir / "cov-0002.yaml").unlink()
    assert next_item_id(items_dir) == "cov-0003", "ids are permanent even when items are not"


def test_an_item_round_trips_through_yaml(corpus, tmp_path):
    _manifest, _cache, agreement = corpus
    item = make_item(agreement)
    path = write_item(item, tmp_path / "items")
    reloaded = load_item(path)

    assert reloaded.id == item.id
    assert reloaded.gold is False
    assert reloaded.gold_span == item.gold_span
    assert reloaded.labelled_at == item.labelled_at
    assert " ".join(reloaded.gold_citation.split()) == " ".join(item.gold_citation.split())


def test_writing_never_silently_replaces_a_label(corpus, tmp_path):
    _manifest, _cache, agreement = corpus
    item = make_item(agreement)
    write_item(item, tmp_path / "items")
    with pytest.raises(FileExistsError):
        write_item(item, tmp_path / "items")


def test_empty_optional_fields_are_left_out_of_the_file(corpus):
    _manifest, _cache, agreement = corpus
    text = item_to_yaml(make_item(agreement))
    assert "unit:" not in text
    assert "enum_options:" not in text
    assert "dispute_note:" not in text


def test_a_reloaded_item_still_cross_validates(corpus, tmp_path):
    manifest, cache, agreement = corpus
    path = write_item(make_item(agreement), tmp_path / "items")
    assert cross_validate([load_item(path)], manifest, cache_dir=cache) == {}


# -- the new schema fields -------------------------------------------------------


def test_numeric_answers_need_a_unit(corpus):
    _manifest, _cache, agreement = corpus
    without = make_item(agreement, answer_type="numeric", gold=35_000_000)
    assert any("need a unit" in e for e in validate(without))

    with_unit = make_item(agreement, answer_type="numeric", gold=35_000_000, unit="USD")
    assert validate(with_unit) == []


def test_enum_answers_need_options_the_answer_is_in(corpus):
    _manifest, _cache, agreement = corpus
    item = make_item(agreement, answer_type="enum", gold="NY", enum_options=["NY", "English"])
    assert validate(item) == []

    wrong = make_item(agreement, answer_type="enum", gold="Delaware", enum_options=["NY", "Eng"])
    assert any("not one of enum_options" in e for e in validate(wrong))


def test_a_disputed_item_must_say_why(corpus):
    _manifest, _cache, agreement = corpus
    item = make_item(agreement, review_status="disputed")
    assert any("why it is disputed" in e for e in validate(item))

    resolved = make_item(
        agreement, review_status="disputed", dispute_note="Counsel reads the basket differently."
    )
    assert validate(resolved) == []


def test_unit_and_enum_options_are_rejected_where_they_do_not_apply(corpus):
    _manifest, _cache, agreement = corpus
    assert any("only applies to numeric" in e for e in validate(make_item(agreement, unit="USD")))
    assert any(
        "only applies to enum" in e for e in validate(make_item(agreement, enum_options=["a", "b"]))
    )


def test_the_schema_is_frozen():
    """Fails on any silent change to the field set.

    If you are here because this test failed: that is the point. Follow the change
    protocol at the top of schema.py before updating this list.
    """
    from covenant_evals.schema import FIELD_NAMES, SCHEMA_VERSION

    assert SCHEMA_VERSION == 1
    assert FIELD_NAMES == (
        "id",
        "doc",
        "doc_sha256",
        "section",
        "question",
        "answer_type",
        "gold",
        "gold_citation",
        "gold_span",
        "rationale",
        "difficulty",
        "labelled_by",
        "labelled_at",
        "review_status",
        "traps",
        "unit",
        "enum_options",
        "dispute_note",
    )


# -- stats -----------------------------------------------------------------------


def test_stats_counts_the_dimensions_the_corpus_must_stay_balanced_on(corpus):
    _manifest, _cache, agreement = corpus
    items = [
        make_item(agreement, id="cov-0001"),
        make_item(agreement, id="cov-0002", difficulty="easy", traps=["carve_out"]),
        make_item(
            agreement,
            id="cov-0003",
            answer_type="abstain",
            gold=None,
            gold_citation=None,
            gold_span=None,
            traps=["not_in_document"],
        ),
    ]
    counts = stats(items)
    assert counts["answer_type"] == {"boolean": 2, "abstain": 1}
    assert counts["difficulty"]["hard"] == 2
    assert counts["trap"]["basket_cap"] == 1
    assert counts["document"][agreement.accession] == 3
