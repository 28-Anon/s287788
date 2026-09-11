"""Tests for the split assignment and the heldout lock.

The lock is the part worth testing hardest. A heldout split you can open by accident is
not a heldout split, and the failure is silent: nothing breaks, the numbers just quietly
stop meaning what you will claim they mean in week 22.
"""

from datetime import date

import pytest

from covenant_evals.corpus.manifest import Agreement, Manifest
from covenant_evals.items import by_split, export, split_of
from covenant_evals.schema import Item
from covenant_evals.splits import (
    DEFAULT_TARGETS,
    HeldoutLocked,
    Splits,
    access_history,
    assign_new,
    check,
    freeze,
    manifest_fingerprint,
    require_open,
    shares,
    sync_manifest,
)


def make_manifest(count: int = 20, english_every: int = 4) -> Manifest:
    manifest = Manifest()
    for index in range(count):
        agreement = Agreement(
            accession=f"0000950170-24-{index:06d}",
            filename="ex101.htm",
            cik="320123",
            company=f"Company {index}",
            form="EX-10.1",
            filed="2024-03-04",
            governing_law="English" if index % english_every == 0 else "NY",
        )
        agreement.text_sha256 = "a" * 64
        agreement.char_count = 100_000 + index * 1_000
        manifest.add(agreement)
    return manifest


# -- assignment ------------------------------------------------------------------


def test_every_fetched_document_gets_exactly_one_split():
    manifest = make_manifest()
    splits = freeze(manifest)

    assert len(splits.assignment) == len(manifest.agreements)
    assert set(splits.assignment.values()) <= {"dev", "test", "heldout"}


def test_assignment_is_deterministic_for_a_given_seed():
    manifest = make_manifest()
    assert freeze(manifest, seed=7).assignment == freeze(manifest, seed=7).assignment


def test_a_different_seed_gives_a_different_assignment():
    manifest = make_manifest()
    assert freeze(manifest, seed=7).assignment != freeze(manifest, seed=8).assignment


def test_shares_land_near_the_targets():
    manifest = make_manifest(count=25)
    splits = freeze(manifest)
    actual = shares(splits, manifest)

    for split, target in DEFAULT_TARGETS.items():
        assert abs(actual[split]["share"] - target) < 0.12, f"{split} is badly off target"


def test_english_law_documents_are_spread_across_splits():
    # If dev were all NY-law and heldout all English-law, a drop between them would be
    # indistinguishable from the split simply being harder.
    manifest = make_manifest(count=24, english_every=3)
    splits = freeze(manifest)
    by_law = {
        s: data["governing_law"].get("English", 0) for s, data in shares(splits, manifest).items()
    }
    assert all(count > 0 for count in by_law.values()), by_law


def test_unfetched_documents_are_not_assigned():
    manifest = make_manifest(count=5)
    manifest.agreements[0].text_sha256 = ""  # never fetched
    splits = freeze(manifest)
    assert manifest.agreements[0].ref not in splits.assignment


def test_freeze_records_what_it_was_cut_from():
    manifest = make_manifest()
    splits = freeze(manifest)
    assert splits.manifest_sha256 == manifest_fingerprint(manifest)
    assert len(splits.assignment_sha256) == 64
    assert splits.is_frozen


def test_nothing_to_split_is_an_error_not_an_empty_result():
    with pytest.raises(ValueError):
        freeze(Manifest())


# -- adding documents after the freeze -------------------------------------------


def test_assign_new_places_later_documents_without_moving_anything():
    manifest = make_manifest(count=12)
    splits = freeze(manifest)
    before = dict(splits.assignment)

    extra = Agreement(
        accession="0000950170-25-000099",
        filename="ex101.htm",
        cik="320123",
        company="Latecomer",
        form="EX-10.1",
        filed="2025-01-01",
        governing_law="NY",
    )
    extra.text_sha256 = "b" * 64
    extra.char_count = 90_000
    manifest.add(extra)

    splits, added = assign_new(splits, manifest)

    assert added == [extra.ref]
    for ref, split in before.items():
        assert splits.assignment[ref] == split, "a frozen assignment must never move"


def test_assign_new_with_nothing_new_changes_nothing():
    manifest = make_manifest(count=8)
    splits = freeze(manifest)
    before = dict(splits.assignment)
    splits, added = assign_new(splits, manifest)
    assert added == []
    assert splits.assignment == before


# -- integrity checks ------------------------------------------------------------


def test_check_passes_on_a_sound_split():
    manifest = make_manifest()
    splits = freeze(manifest)
    sync_manifest(splits, manifest)
    assert check(splits, manifest) == []


def test_check_catches_an_unassigned_document():
    manifest = make_manifest(count=10)
    splits = freeze(manifest)
    splits.assignment.pop(manifest.agreements[0].ref)
    assert any("no split" in p for p in check(splits, manifest))


def test_check_catches_a_document_that_left_the_corpus():
    manifest = make_manifest(count=10)
    splits = freeze(manifest)
    manifest.agreements = manifest.agreements[1:]
    assert any("no longer fetched" in p for p in check(splits, manifest))


def test_check_catches_the_manifest_disagreeing_with_splits_json():
    manifest = make_manifest(count=10)
    splits = freeze(manifest)
    sync_manifest(splits, manifest)
    manifest.agreements[0].split = (
        "heldout" if splits.of(manifest.agreements[0].ref) != "heldout" else "dev"
    )
    assert any("splits.json is authoritative" in p for p in check(splits, manifest))


def test_check_catches_an_empty_split():
    manifest = make_manifest(count=10)
    splits = freeze(manifest)
    for ref in list(splits.assignment):
        splits.assignment[ref] = "dev"
    problems = check(splits, manifest)
    assert any("has no documents" in p for p in problems)


# -- persistence -----------------------------------------------------------------


def test_splits_round_trip(tmp_path):
    manifest = make_manifest()
    splits = freeze(manifest)
    path = tmp_path / "splits.json"
    splits.save(path)

    reloaded = Splits.load(path)
    assert reloaded.assignment == splits.assignment
    assert reloaded.seed == splits.seed
    assert reloaded.assignment_sha256 == splits.assignment_sha256


def test_loading_a_missing_file_returns_none_rather_than_an_empty_split(tmp_path):
    # An empty Splits would silently behave as "nothing is heldout", which is the worst
    # possible default.
    assert Splits.load(tmp_path / "absent.json") is None


def test_a_quiet_edit_to_the_assignment_changes_its_fingerprint(tmp_path):
    manifest = make_manifest()
    splits = freeze(manifest)
    original = splits.assignment_sha256

    ref = next(r for r, s in splits.assignment.items() if s == "test")
    splits.assignment[ref] = "dev"
    assert splits.assignment_sha256 != original


# -- the heldout lock ------------------------------------------------------------


def test_dev_and_test_open_freely(tmp_path):
    log = tmp_path / "access.log"
    require_open("dev", log_path=log)
    require_open("test", log_path=log)
    assert not log.exists(), "only heldout access is recorded"


def test_heldout_refuses_without_a_reason(tmp_path):
    with pytest.raises(HeldoutLocked, match="closed until week 22"):
        require_open("heldout", log_path=tmp_path / "access.log")


def test_heldout_refuses_a_token_reason(tmp_path):
    # "ok" or "test" is how a lock gets defeated by accident.
    with pytest.raises(HeldoutLocked):
        require_open("heldout", reason="ok", log_path=tmp_path / "access.log")


def test_opening_heldout_leaves_a_permanent_record(tmp_path):
    log = tmp_path / "access.log"
    require_open("heldout", reason="week 22 final graded run, all three systems", log_path=log)

    history = access_history(log)
    assert len(history) == 1
    assert "week 22" in history[0]["reason"]
    assert history[0]["at"]


def test_every_opening_is_appended_not_overwritten(tmp_path):
    log = tmp_path / "access.log"
    require_open("heldout", reason="first graded run of the heldout split", log_path=log)
    require_open("heldout", reason="second run after fixing the scorer", log_path=log)
    assert len(access_history(log)) == 2


def test_no_history_when_heldout_was_never_opened(tmp_path):
    assert access_history(tmp_path / "absent.log") == []


# -- export ----------------------------------------------------------------------


def make_item(accession: str, item_id: str = "cov-0001") -> Item:
    return Item(
        id=item_id,
        doc=accession,
        doc_sha256="a" * 64,
        section="7.01(b)",
        question="May the Borrower incur $50,000,000 of incremental term loans?",
        answer_type="boolean",
        gold=False,
        gold_citation="not to exceed the greater of $35,000,000",
        gold_span=[100, 140],
        rationale="The basket caps incremental facilities below the requested figure.",
        difficulty="hard",
        labelled_by="SM",
        labelled_at=date(2026, 10, 4),
        traps=["basket_cap"],
    )


def test_items_inherit_the_split_of_their_document():
    manifest = make_manifest(count=10)
    splits = freeze(manifest)
    accession = manifest.agreements[0].accession
    assert split_of(make_item(accession), manifest, splits) == splits.of(manifest.agreements[0].ref)


def test_by_split_groups_items_and_flags_orphans():
    manifest = make_manifest(count=10)
    splits = freeze(manifest)
    items = [
        make_item(manifest.agreements[0].accession, "cov-0001"),
        make_item("0000000000-00-000000", "cov-0002"),
    ]
    grouped = by_split(items, manifest, splits)
    assert "unassigned" in grouped
    assert len(grouped["unassigned"]) == 1


def test_export_never_emits_the_answer(tmp_path):
    manifest = make_manifest(count=10)
    splits = freeze(manifest)
    accession = next(a.accession for a in manifest.agreements if splits.of(a.ref) == "dev")
    rows = export([make_item(accession)], "dev", manifest, splits, log_path=tmp_path / "l.log")

    assert len(rows) == 1
    serialised = str(rows)
    assert "gold" not in serialised
    assert "35,000,000" not in serialised
    assert "basket caps" not in serialised
    assert rows[0]["question"].startswith("May the Borrower")


def test_exporting_heldout_goes_through_the_lock(tmp_path):
    manifest = make_manifest(count=10)
    splits = freeze(manifest)
    with pytest.raises(HeldoutLocked):
        export([], "heldout", manifest, splits, log_path=tmp_path / "l.log")


def test_exporting_heldout_with_a_reason_is_recorded(tmp_path):
    log = tmp_path / "l.log"
    manifest = make_manifest(count=10)
    splits = freeze(manifest)
    export([], "heldout", manifest, splits, reason="week 22 graded run", log_path=log)
    assert len(access_history(log)) == 1
