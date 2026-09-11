"""Tests for loading item files off disk."""

from pathlib import Path

import pytest

from covenant_evals.items import load_all, load_item, validate_all

VALID_YAML = """
id: cov-0001
doc: "0000950170-24-012345"
doc_sha256: "{sha}"
section: "7.02(b)"
question: May the Borrower incur $50,000,000 of incremental term loans?
answer_type: boolean
gold: false
gold_citation: in an aggregate principal amount not to exceed $35,000,000
gold_span: [148223, 148344]
rationale: The Free and Clear amount caps incremental facilities below the request.
difficulty: hard
traps: [defined_term_chain]
labelled_by: SM
labelled_at: 2026-10-04
review_status: single
""".format(sha="a" * 64)


def write(directory: Path, name: str, body: str) -> None:
    (directory / name).write_text(body, encoding="utf-8")


def test_loads_a_valid_item(tmp_path):
    write(tmp_path, "cov-0001.yaml", VALID_YAML)
    items = load_all(tmp_path)
    assert len(items) == 1
    assert items[0].id == "cov-0001"
    assert items[0].gold is False
    assert validate_all(items) == {}


def test_labelled_at_parses_from_a_string(tmp_path):
    write(tmp_path, "cov-0001.yaml", VALID_YAML.replace("2026-10-04", '"2026-10-04"'))
    assert load_all(tmp_path)[0].labelled_at.year == 2026


def test_missing_directory_of_items_is_simply_empty(tmp_path):
    assert load_all(tmp_path) == []


def test_unknown_field_is_an_error_not_a_silent_drop(tmp_path):
    write(tmp_path, "bad.yaml", VALID_YAML + "\nseverity: high\n")
    with pytest.raises(ValueError):
        load_all(tmp_path)


def test_duplicate_ids_are_caught_across_files(tmp_path):
    write(tmp_path, "a.yaml", VALID_YAML)
    write(tmp_path, "b.yaml", VALID_YAML)
    problems = validate_all(load_all(tmp_path))
    assert any("duplicate id" in m for m in problems["cov-0001"])


def test_top_level_must_be_a_mapping(tmp_path):
    write(tmp_path, "bad.yaml", "- just\n- a\n- list\n")
    with pytest.raises(ValueError):
        load_item(tmp_path / "bad.yaml")
