"""Tests for the item schema.

These are as much documentation as verification: each test names one rule the schema
enforces, so reading the test file tells you what a valid item is.
"""

from datetime import date

import pytest

from covenant_evals.schema import Item, validate

SHA = "a" * 64


def make_item(**overrides) -> Item:
    """A valid item, with fields overridable one at a time."""
    defaults = dict(
        id="cov-0001",
        doc="0000950170-24-012345",
        doc_sha256=SHA,
        section="7.02(b)",
        question="May the Borrower incur $50,000,000 of incremental term loans?",
        answer_type="boolean",
        gold=False,
        gold_citation="in an aggregate principal amount not to exceed $35,000,000",
        gold_span=[148223, 148344],
        rationale="The Free and Clear amount caps incremental facilities below the request.",
        difficulty="hard",
        labelled_by="SM",
        labelled_at=date(2026, 10, 4),
        review_status="double_checked",
        traps=["defined_term_chain", "basket_cap"],
    )
    defaults.update(overrides)
    return Item(**defaults)


def test_a_well_formed_item_has_no_errors():
    assert validate(make_item()) == []


def test_section_is_required():
    errors = validate(make_item(section="  "))
    assert any("section" in e for e in errors)


def test_hash_must_be_a_full_sha256():
    errors = validate(make_item(doc_sha256="abc123"))
    assert any("sha256" in e.lower() for e in errors)


def test_unknown_trap_is_rejected():
    errors = validate(make_item(traps=["vibes"]))
    assert any("unknown traps" in e for e in errors)


def test_boolean_answer_must_be_a_boolean():
    errors = validate(make_item(answer_type="boolean", gold="no"))
    assert any("true/false" in e for e in errors)


def test_numeric_answer_rejects_a_boolean():
    # True == 1 in Python, so a bool would silently pass a naive isinstance check.
    errors = validate(make_item(answer_type="numeric", gold=True))
    assert any("number" in e for e in errors)


def test_answerable_item_requires_a_citation():
    errors = validate(make_item(gold_citation=None))
    assert any("verbatim text" in e for e in errors)


def test_answerable_item_requires_a_span():
    errors = validate(make_item(gold_span=None))
    assert any("gold_span" in e for e in errors)


def test_span_must_run_forwards():
    errors = validate(make_item(gold_span=[500, 100]))
    assert any("greater than start" in e for e in errors)


def test_abstain_item_has_no_answer_and_no_citation():
    item = make_item(
        answer_type="abstain",
        gold=None,
        gold_citation=None,
        gold_span=None,
        traps=["not_in_document"],
    )
    assert validate(item) == []


def test_abstain_item_must_carry_the_not_in_document_trap():
    item = make_item(answer_type="abstain", gold=None, gold_citation=None, gold_span=None, traps=[])
    errors = validate(item)
    assert any("not_in_document" in e for e in errors)


def test_abstain_item_must_not_have_an_answer():
    item = make_item(
        answer_type="abstain",
        gold=True,
        gold_citation=None,
        gold_span=None,
        traps=["not_in_document"],
    )
    errors = validate(item)
    assert any("gold must be null" in e for e in errors)


@pytest.mark.parametrize("field,value", [("difficulty", "spicy"), ("review_status", "ok")])
def test_controlled_vocabularies_are_enforced(field, value):
    errors = validate(make_item(**{field: value}))
    assert any(field in e for e in errors)
