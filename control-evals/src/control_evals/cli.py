"""The command line. Everything you can do to this project without writing Python.

Two rules it follows, both learned the hard way in covenant-evals:

* **No `make`.** Every command in the docs is `py -m control_evals.cli ...`, which works on
  Windows PowerShell, macOS and Linux with no extra tooling and no PATH surprises.
* **Nothing here reaches the network.** Week 9 adds a runner that does; until then every
  command is offline and instant.
"""

from __future__ import annotations

import argparse
import json
import sys

from .scenario import CATEGORIES, validate_all
from .scenarios import SUITE, by_id
from .splits import (
    DEFAULT_SEED,
    MIN_FAMILIES_PER_CATEGORY,
    SPLITS,
    HeldoutLocked,
    Splits,
    access_history,
    assign_new,
    coverage,
    families,
    family_of,
    grouped_for_category,
    select,
    shares,
)
from .splits import check as check_splits

# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------


def cmd_scenarios_list(args: argparse.Namespace) -> int:
    splits = Splits.load()
    rows = sorted(SUITE, key=lambda s: s.id)
    if args.category:
        rows = [s for s in rows if s.category == args.category]

    print(f"{'id':<16} {'family':<12} {'category':<19} {'pressure':<12} split")
    print("-" * 74)
    for scenario in rows:
        split = splits.of(scenario.id) if splits else "-"
        print(
            f"{scenario.id:<16} {family_of(scenario.id):<12} {scenario.category:<19} "
            f"{scenario.pressure:<12} {split or 'unassigned'}"
        )

    grouped = families(rows)
    print(f"\n{len(rows)} scenario(s) in {len(grouped)} family/families")

    uncovered = sorted(set(CATEGORIES) - {s.category for s in SUITE})
    if uncovered:
        print(f"categories with no scenario yet: {', '.join(uncovered)}")
    return 0


def cmd_scenarios_show(args: argparse.Namespace) -> int:
    """One scenario in full: the policy as the agent will see it, and the task."""
    scenario = by_id(args.id)
    if scenario is None:
        raise SystemExit(f"no scenario {args.id!r} — try `scenarios list`")

    splits = Splits.load()
    print(f"{scenario.id}  [{scenario.category} / pressure: {scenario.pressure}]")
    if splits:
        print(f"split: {splits.of(scenario.id) or 'unassigned'}")
    print(f"\ntests: {scenario.tests}\n")
    print("-- policy, as the agent sees it " + "-" * 47)
    print(scenario.policy.render(scenario.tools))
    print("\n-- task " + "-" * 70)
    print(scenario.task)
    print("\n-- tools " + "-" * 69)
    print(", ".join(scenario.tools))
    if scenario.inaction_is_a_violation:
        print("\nNote: doing nothing is a violation here — a payment is already queued.")
    return 0


def cmd_scenarios_categories() -> int:
    """The taxonomy and how many families sit in each. The suite's own health check."""
    splits = Splits.load()
    grouped = families(SUITE)

    print(f"{'category':<20} {'families':>8} {'scenarios':>10}  splits")
    print("-" * 62)
    for category in CATEGORIES:
        members = [s for s in SUITE if s.category == category]
        names = grouped_for_category(grouped, category)
        where = sorted({splits.of(s.id) for s in members}) if splits else []
        flag = "" if len(names) >= MIN_FAMILIES_PER_CATEGORY else "  (thin)"
        print(
            f"{category:<20} {len(names):>8} {len(members):>10}  "
            f"{', '.join(w for w in where if w)}{flag}"
        )
    print(f"\n{len(SUITE)} scenarios in {len(grouped)} families")
    return 0


def cmd_scenarios_check() -> int:
    problems = validate_all(list(SUITE))
    if not problems:
        print(f"{len(SUITE)} scenarios, all well formed")
        return 0
    for scenario_id, errors in sorted(problems.items()):
        print(f"{scenario_id}:")
        for error in errors:
            print(f"  - {error}")
    return 1


# ---------------------------------------------------------------------------
# splits
# ---------------------------------------------------------------------------


def _require_splits() -> Splits:
    splits = Splits.load()
    if splits is None:
        raise SystemExit("no splits yet — run `py -m control_evals.cli splits freeze` first")
    return splits


def _print_shares(splits: Splits) -> None:
    print(f"{'split':<10} {'families':>8} {'scenarios':>10} {'share':>7} {'target':>7}")
    for split, data in shares(splits, SUITE).items():
        print(
            f"{split:<10} {data['families']:>8} {data['scenarios']:>10} "
            f"{data['share']:>6.0%} {data['target']:>7.0%}"
        )


def cmd_splits_freeze(args: argparse.Namespace) -> int:
    from .splits import freeze

    existing = Splits.load()
    if existing is not None and existing.is_frozen and not args.force:
        raise SystemExit(
            f"splits were frozen at {existing.frozen_at} and will not be re-cut.\n"
            "Re-cutting after any result exists makes every past number incomparable.\n"
            "To place families added since the freeze, use `splits assign-new`."
        )

    splits = freeze(SUITE, seed=args.seed)
    splits.save()

    print(f"frozen at {splits.frozen_at}")
    print(f"seed {splits.seed}, assignment {splits.assignment_sha256[:12]}…\n")
    _print_shares(splits)
    print("\nCommit data/splits.json now. The heldout split is closed until week 22.")
    return 0


def cmd_splits_assign_new() -> int:
    splits = _require_splits()
    splits, added = assign_new(splits, SUITE)
    if not added:
        print("no new families since the freeze")
        return 0
    splits.save()
    print(f"placed {len(added)} new family/families:\n")
    for name in added:
        print(f"  {splits.family_split(name):<9} {name}")
    print("\nCommit data/splits.json.")
    return 0


def cmd_splits_status() -> int:
    splits = Splits.load()
    if splits is None:
        print("splits not frozen yet")
        return 0

    print(f"frozen at {splits.frozen_at}")
    print(f"seed {splits.seed}, assignment {splits.assignment_sha256[:12]}…\n")
    _print_shares(splits)

    opened = access_history()
    print(f"\nheldout opened {len(opened)} time(s)")
    for entry in opened:
        print(f"  {entry['at']}  {entry['reason']}")
    return 0


def cmd_splits_check() -> int:
    splits = _require_splits()
    problems = check_splits(splits, SUITE)
    report = coverage(splits, SUITE)

    for problem in problems:
        print(f"PROBLEM  {problem}")

    thin = report["thin"]
    if thin:
        print(
            f"\nWARN     {len(thin)} categor(y/ies) have fewer than three families, so a "
            "per-category\n         result cannot be reported on test alone yet:"
        )
        for category in thin:
            placement = report["by_category"].get(category, {})
            where = ", ".join(f"{split}: {len(names)}" for split, names in placement.items())
            print(f"           {category:<19} {where or 'no scenarios yet'}")
        print("         This clears when weeks 6-8 give each category several families.")

    if not problems:
        print(f"\n{len(splits.assignment)} families assigned, no problems")
    return 1 if problems else 0


def cmd_splits_show(args: argparse.Namespace) -> int:
    splits = _require_splits()
    try:
        chosen = select(args.split, SUITE, splits, reason=args.reason)
    except HeldoutLocked as exc:
        print(str(exc), file=sys.stderr)
        return 2

    for scenario in chosen:
        print(f"{scenario.id:<16} {scenario.category:<19} {scenario.tests}")
    print(f"\n{len(chosen)} scenario(s) in {args.split}")
    if args.split == "heldout":
        print("This access has been written to runs/heldout-access.log. Commit it.")
    return 0


def cmd_splits_log() -> int:
    opened = access_history()
    if not opened:
        print("heldout has never been opened")
        return 0
    for entry in opened:
        print(f"{entry['at']}  {entry['reason']}")
    print(f"\n{len(opened)} access(es)")
    return 0


def cmd_splits_coverage() -> int:
    splits = _require_splits()
    print(json.dumps(coverage(splits, SUITE), indent=2))
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="control-evals",
        description="Does an AI agent stay inside the limits you set when it can move money?",
    )
    sub = parser.add_subparsers(dest="group", required=True)

    scenarios = sub.add_parser("scenarios", help="the scenario suite").add_subparsers(
        dest="command", required=True
    )
    listing = scenarios.add_parser("list", help="every scenario and its split")
    listing.add_argument("--category", choices=CATEGORIES)
    listing.set_defaults(func=lambda args: cmd_scenarios_list(args))
    scenarios.add_parser("check", help="validate every scenario").set_defaults(
        func=lambda args: cmd_scenarios_check()
    )
    show_one = scenarios.add_parser("show", help="one scenario in full")
    show_one.add_argument("id")
    show_one.set_defaults(func=lambda args: cmd_scenarios_show(args))
    scenarios.add_parser(
        "categories", help="the taxonomy, and how well each is covered"
    ).set_defaults(func=lambda args: cmd_scenarios_categories())

    splits = sub.add_parser("splits", help="dev / test / heldout").add_subparsers(
        dest="command", required=True
    )
    frz = splits.add_parser("freeze", help="cut the split, once")
    frz.add_argument("--seed", type=int, default=DEFAULT_SEED)
    frz.add_argument("--force", action="store_true", help="re-cut anyway (almost never right)")
    frz.set_defaults(func=lambda args: cmd_splits_freeze(args))

    splits.add_parser("assign-new", help="place families added since the freeze").set_defaults(
        func=lambda args: cmd_splits_assign_new()
    )
    splits.add_parser("status", help="shares, and the heldout access log").set_defaults(
        func=lambda args: cmd_splits_status()
    )
    splits.add_parser("check", help="what is wrong with the split").set_defaults(
        func=lambda args: cmd_splits_check()
    )
    splits.add_parser("coverage", help="category coverage as JSON").set_defaults(
        func=lambda args: cmd_splits_coverage()
    )
    show = splits.add_parser("show", help="the scenarios in one split")
    show.add_argument("split", choices=SPLITS)
    show.add_argument("--reason", default="", help="required for heldout; it is logged")
    show.set_defaults(func=lambda args: cmd_splits_show(args))

    splits.add_parser("log", help="every time heldout has been opened").set_defaults(
        func=lambda args: cmd_splits_log()
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
