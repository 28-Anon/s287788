"""Tests for the split and, mostly, for the lock on it.

The split itself is a shuffle and the shuffle is not the interesting part. The interesting
parts are the three properties that make it worth freezing at all:

1. a family is never divided across splits,
2. a frozen assignment is never silently changed, and
3. heldout cannot be read without leaving a record.

Property 3 is the one that has to survive seventeen weeks of the author being tempted, so it
is tested from both ends: it refuses, and when it does not refuse, it writes.
"""

import json

import pytest

from control_evals.money import pence
from control_evals.policy import Policy
from control_evals.scenario import Scenario
from control_evals.scenarios import SUITE
from control_evals.splits import (
    DEFAULT_ACCESS_LOG,
    SPLITS,
    HeldoutLocked,
    Splits,
    access_history,
    assign_new,
    check,
    coverage,
    families,
    family_of,
    freeze,
    require_open,
    select,
    shares,
    suite_fingerprint,
)
from control_evals.world import PaymentsWorld

REPO_ROOT = DEFAULT_ACCESS_LOG.parent.parent


def make(scenario_id: str, category: str = "hard_limit", pressure: str = "none") -> Scenario:
    return Scenario(
        id=scenario_id,
        category=category,
        pressure=pressure,
        tests="a synthetic scenario used only by the split tests",
        policy=Policy(max_single_payment=pence(1_000)),
        world=lambda: PaymentsWorld(balance=pence(10_000)),
        tools=("get_balance", "transfer_funds"),
        task="Pay the invoice that the synthetic split test pretends exists.",
        violated=lambda trace, world: None,
        completed=lambda trace, world: True,
    )


def suite_of(*ids: str) -> list[Scenario]:
    """Ids of the form ``family-NNN:category``, so a test reads as its own fixture."""
    out = []
    for spec in ids:
        scenario_id, _, category = spec.partition(":")
        out.append(make(scenario_id, category or "hard_limit"))
    return out


# -- families --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scenario_id", "expected"),
    [
        ("limit-001", "limit"),
        ("limit-002", "limit"),
        ("injection-014", "injection"),
        ("limit-persistence-003", "limit-persistence"),
        ("oneoff", "oneoff"),
    ],
)
def test_family_of(scenario_id, expected):
    assert family_of(scenario_id) == expected


def test_an_id_with_no_number_is_its_own_family():
    """The safe reading: a scenario nothing shares a name with shares nothing else."""
    assert family_of("weird") == "weird"


def test_families_groups_and_sorts():
    grouped = families(suite_of("limit-002", "limit-001", "injection-001"))
    assert sorted(grouped) == ["injection", "limit"]
    assert [s.id for s in grouped["limit"]] == ["limit-001", "limit-002"]


# -- the property the whole design exists for ------------------------------------


def test_a_family_is_never_divided():
    suite = suite_of(
        *[f"limit-{n:03d}" for n in range(1, 9)],
        *[f"inj-{n:03d}:injection" for n in range(1, 9)],
    )
    splits = freeze(suite)

    for name, members in families(suite).items():
        assigned = {splits.of(s.id) for s in members}
        assert len(assigned) == 1, f"family {name} was split across {assigned}"


def test_freeze_is_deterministic():
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    assert freeze(suite, seed=7).assignment == freeze(suite, seed=7).assignment


def test_seed_changes_the_assignment():
    suite = suite_of(*[f"f{i}-001" for i in range(20)])
    assert freeze(suite, seed=1).assignment != freeze(suite, seed=2).assignment


def test_freeze_refuses_an_empty_suite():
    with pytest.raises(ValueError, match="nothing to split"):
        freeze([])


def test_shares_land_near_the_targets():
    suite = suite_of(*[f"f{i}-001" for i in range(60)])
    splits = freeze(suite)
    for split, data in shares(splits, suite).items():
        assert abs(data["share"] - data["target"]) < 0.06, (split, data)


# -- adding scenarios after the freeze -------------------------------------------


def test_assign_new_never_moves_an_existing_family():
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    splits = freeze(suite)
    before = dict(splits.assignment)

    grown = suite + suite_of(*[f"g{i}-001" for i in range(6)])
    splits, added = assign_new(splits, grown)

    assert added == sorted(f"g{i}" for i in range(6))
    for name, split in before.items():
        assert splits.assignment[name] == split


def test_a_new_scenario_in_an_existing_family_inherits_its_split():
    """This is the leak the design is built to prevent, so it gets its own test."""
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    splits = freeze(suite)
    home = splits.of("f3-001")

    grown = suite + [make("f3-002")]
    splits, added = assign_new(splits, grown)

    assert added == []
    assert splits.of("f3-002") == home


def test_assign_new_updates_the_suite_fingerprint():
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    splits = freeze(suite)
    grown = suite + [make("g1-001")]

    splits, _ = assign_new(splits, grown)
    assert splits.suite_sha256 == suite_fingerprint(grown)


# -- check -----------------------------------------------------------------------


def test_check_is_clean_on_a_fresh_freeze():
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    assert check(freeze(suite), suite) == []


def test_check_catches_an_unassigned_family():
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    splits = freeze(suite)
    problems = check(splits, suite + [make("late-001")])
    assert any("assign-new" in p for p in problems)


def test_check_catches_a_deleted_scenario():
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    splits = freeze(suite)
    problems = check(splits, suite[1:])
    assert any("no longer exist" in p for p in problems)


def test_check_catches_a_family_that_spans_categories():
    suite = suite_of("f1-001:hard_limit", "f1-002:injection", *[f"g{i}-001" for i in range(12)])
    splits = freeze(suite)
    problems = check(splits, suite)
    assert any("spans categories" in p for p in problems)


def test_check_catches_an_unknown_split_name():
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    splits = freeze(suite)
    splits.assignment["f0"] = "train"
    assert any("unknown split" in p for p in check(splits, suite))


def test_check_catches_an_empty_split():
    suite = suite_of("only-001")
    splits = freeze(suite)
    assert sum("no families at all" in p for p in check(splits, suite)) == 2


# -- coverage --------------------------------------------------------------------


def test_coverage_flags_a_category_with_too_few_families():
    suite = suite_of("f1-001:injection", *[f"g{i}-001:hard_limit" for i in range(9)])
    splits = freeze(suite)
    report = coverage(splits, suite)

    assert "injection" in report["thin"]
    assert "hard_limit" in report["reportable"]
    assert "escalation" in report["missing"]


def test_coverage_names_where_each_category_lives():
    suite = suite_of(*[f"f{i}-001:injection" for i in range(9)])
    splits = freeze(suite)
    placement = coverage(splits, suite)["by_category"]["injection"]
    assert set(placement) <= set(SPLITS)
    assert sum(len(v) for v in placement.values()) == 9


# -- persistence -----------------------------------------------------------------


def test_save_and_load_round_trip(tmp_path):
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    splits = freeze(suite)
    path = tmp_path / "splits.json"
    splits.save(path)

    reloaded = Splits.load(path)
    assert reloaded.assignment == splits.assignment
    assert reloaded.frozen_at == splits.frozen_at
    assert reloaded.assignment_sha256 == splits.assignment_sha256


def test_load_returns_none_when_there_is_nothing_there(tmp_path):
    assert Splits.load(tmp_path / "absent.json") is None


def test_a_hand_edit_changes_the_fingerprint(tmp_path):
    """The point of writing assignment_sha256 into the file: a quiet move is visible."""
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    splits = freeze(suite)
    path = tmp_path / "splits.json"
    splits.save(path)
    recorded = json.loads(path.read_text())["assignment_sha256"]

    splits.assignment["f0"] = "heldout" if splits.assignment["f0"] != "heldout" else "dev"
    assert splits.assignment_sha256 != recorded


# -- the heldout lock ------------------------------------------------------------


def test_dev_and_test_open_without_ceremony(tmp_path):
    log = tmp_path / "heldout-access.log"
    require_open("dev", log_path=log)
    require_open("test", log_path=log)
    assert not log.exists()


def test_heldout_refuses_without_a_reason(tmp_path):
    with pytest.raises(HeldoutLocked, match="closed until week 22"):
        require_open("heldout", log_path=tmp_path / "log")


def test_heldout_refuses_a_token_reason(tmp_path):
    """'ok' is not a reason. Ten characters is a low bar that still requires a sentence."""
    log = tmp_path / "heldout-access.log"
    with pytest.raises(HeldoutLocked):
        require_open("heldout", reason="ok", log_path=log)
    with pytest.raises(HeldoutLocked):
        require_open("heldout", reason="         ", log_path=log)
    assert not log.exists()


def test_opening_heldout_writes_the_log(tmp_path):
    log = tmp_path / "heldout-access.log"
    require_open("heldout", reason="week 22 final evaluation", log_path=log)
    require_open("heldout", reason="second look for the write-up", log_path=log)

    history = access_history(log)
    assert [e["reason"] for e in history] == [
        "week 22 final evaluation",
        "second look for the write-up",
    ]
    assert all(e["at"].endswith("+00:00") for e in history)


def test_access_history_is_empty_when_never_opened(tmp_path):
    assert access_history(tmp_path / "never") == []


def test_an_unknown_split_is_an_error_not_a_silent_pass(tmp_path):
    with pytest.raises(ValueError, match="unknown split"):
        require_open("holdout", log_path=tmp_path / "log")


# -- select ----------------------------------------------------------------------


def test_select_returns_only_that_split(tmp_path):
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    splits = freeze(suite)
    chosen = select("dev", suite, splits, log_path=tmp_path / "log")
    assert chosen
    assert {splits.of(s.id) for s in chosen} == {"dev"}
    assert [s.id for s in chosen] == sorted(s.id for s in chosen)


def test_select_is_the_gate(tmp_path):
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    splits = freeze(suite)
    with pytest.raises(HeldoutLocked):
        select("heldout", suite, splits, log_path=tmp_path / "log")


def test_select_logs_when_it_does_open(tmp_path):
    log = tmp_path / "heldout-access.log"
    suite = suite_of(*[f"f{i}-001" for i in range(12)])
    splits = freeze(suite)
    chosen = select("heldout", suite, splits, reason="week 22 final run", log_path=log)
    assert chosen
    assert len(access_history(log)) == 1


# -- the real suite --------------------------------------------------------------


def test_the_committed_split_covers_the_real_suite():
    splits = Splits.load()
    assert splits is not None, "data/splits.json is missing — run `splits freeze` and commit it"
    assert splits.is_frozen
    assert check(splits, SUITE) == []


def test_every_real_scenario_has_a_split():
    splits = Splits.load()
    for scenario in SUITE:
        assert splits.of(scenario.id) in SPLITS, scenario.id


def test_the_access_log_is_not_gitignored():
    """If this file were ignored, the lock would be a convention rather than evidence."""
    ignore = (REPO_ROOT / ".gitignore").read_text()
    assert "!runs/heldout-access.log" in ignore
