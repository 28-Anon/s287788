"""Command line entry points.

    py -m control_evals.cli run --split dev        # run an agent against a split
    py -m control_evals.cli run --dry-run          # exercise it all, spending nothing
    py -m control_evals.cli budget                 # what this project has cost so far
    py -m control_evals.cli scenarios              # what is in the suite
    py -m control_evals.cli splits freeze          # cut dev/test/heldout, once
    py -m control_evals.cli splits status          # the assignment, and the heldout log
    py -m control_evals.cli splits check           # is the frozen split still sound
    py -m control_evals.cli splits assign-new      # place families added since the freeze
    py -m control_evals.cli splits show dev        # the scenarios in a split
    py -m control_evals.cli splits refingerprint   # accept edits to existing scenarios

`pyproject.toml` also installs this as `control-evals`, but `py -m` always works and does
not depend on pip's Scripts folder being on PATH, which on Windows it usually is not.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import budget as budget_module
from .agent import DEFAULT_MAX_TURNS, DEFAULT_MODEL, PaymentsAgent
from .fixture import DecliningClient
from .metrics import by_category, format_frontier, summarise
from .runner import run_split
from .scenario import validate_all
from .scenarios import SUITE
from .splits import (
    DEFAULT_SEED,
    LOCK_MESSAGE,
    SPLITS,
    HeldoutLocked,
    Splits,
    access_history,
    assign_new,
    families,
    freeze,
    is_open,
    refresh_fingerprints,
    select,
    shares,
)
from .splits import (
    check as check_splits,
)


def _require_splits() -> Splits:
    splits = Splits.load()
    if splits is None:
        raise SystemExit("splits have not been frozen yet — run `splits freeze`")
    return splits


def _print_shares(splits: Splits) -> None:
    for split, data in shares(splits, SUITE).items():
        categories = ", ".join(f"{k}:{v}" for k, v in sorted(data["categories"].items()))
        print(
            f"  {split:<8} {data['families']:>3} families  {data['scenarios']:>3} scenarios  "
            f"{data['share']:>5.0%} (target {data['target']:.0%})  {categories}"
        )


# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------


def cmd_scenarios() -> int:
    problems = validate_all(list(SUITE))
    splits = Splits.load()

    for name, members in families(SUITE).items():
        assigned = splits.of(name) if splits else "-"
        print(f"{name}  [{assigned}]")
        for scenario in members:
            flag = " INVALID" if scenario.id in problems else ""
            print(f"    {scenario.id:<16} {scenario.category:<20} {scenario.pressure}{flag}")

    print(f"\n{len(SUITE)} scenarios in {len(families(SUITE))} families")
    if problems:
        for scenario_id in sorted(problems):
            for message in problems[scenario_id]:
                print(f"{scenario_id}: {message}", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------------------
# splits
# ---------------------------------------------------------------------------


def cmd_splits_freeze(args: argparse.Namespace) -> int:
    existing = Splits.load()
    if existing is not None and existing.is_frozen and not args.force:
        raise SystemExit(
            f"splits were frozen at {existing.frozen_at} and will not be re-cut.\n"
            "A split you can silently redraw is not a split: every past result was "
            "measured against this one.\n"
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
        print("no new families to assign")
        return 0

    splits.save()
    for name in added:
        print(f"{splits.of(name):<8} {name}")
    print(f"\n{len(added)} family/families assigned. Nothing already assigned was moved.")
    return 0


def cmd_splits_status() -> int:
    splits = Splits.load()
    if splits is None:
        print("splits not frozen yet")
        return 0

    print(f"frozen at {splits.frozen_at}")
    print(f"seed {splits.seed}, assignment {splits.assignment_sha256[:12]}…\n")
    _print_shares(splits)

    history = access_history()
    print()
    if history:
        print(f"HELDOUT HAS BEEN OPENED {len(history)} time(s):")
        for entry in history:
            print(f"  {entry['at']}  {entry['reason']}")
    else:
        print("heldout: never opened")
    return 0


def cmd_splits_check() -> int:
    splits = _require_splits()
    problems = check_splits(splits, SUITE)

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} problem(s)", file=sys.stderr)
        return 1

    print(f"splits are sound: {len(SUITE)} scenarios, {len(splits.assignment)} families")
    return 0


def cmd_splits_show(args: argparse.Namespace) -> int:
    splits = _require_splits()
    try:
        chosen = select(SUITE, splits, args.split, reason=args.reason)
    except HeldoutLocked as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for scenario in chosen:
        print(f"{scenario.id:<16} {scenario.family:<14} {scenario.category}")
    print(f"\n{len(chosen)} scenario(s) in {args.split}")
    if args.split == "heldout":
        print("This access was written to runs/heldout-access.log. Commit it.")
    return 0


def cmd_splits_refingerprint(args: argparse.Namespace) -> int:
    splits = _require_splits()
    moved = refresh_fingerprints(splits, SUITE)

    if not moved:
        print("no scenario content has changed")
        splits.save()
        return 0

    if not args.yes:
        print("these scenarios have changed since the freeze:", file=sys.stderr)
        for scenario_id in moved:
            print(f"  {scenario_id}", file=sys.stderr)
        print(
            "\nAccepting them means results measured before and after are not comparable. "
            "The cheaper fix is usually a new id for the new version. Pass --yes if you "
            "mean it.",
            file=sys.stderr,
        )
        return 1

    splits.save()
    for scenario_id in moved:
        print(f"refingerprinted {scenario_id}")
    return 0


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """Read KEY=value lines from .env into the environment.

    Deliberately tiny and dependency-free. Existing environment variables always win, so
    `$env:ANTHROPIC_API_KEY="..."` on the command line overrides the file.
    """
    target = path or REPO_ROOT / ".env"
    if not target.exists():
        return
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def cmd_run(args: argparse.Namespace) -> int:
    splits = _require_splits()

    problems = check_splits(splits, SUITE)
    if problems and not args.force:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(
            "\nRefusing to run against a suite that does not match the freeze — the numbers "
            "would not mean what they say. Fix it, or pass --force and say so in the write-up.",
            file=sys.stderr,
        )
        return 1

    # Before anything else, including credentials: a locked split should say so rather than
    # complain about an API key. is_open does not log, so the real opening below is the only
    # line that reaches the access log.
    if not is_open(args.split, args.reason):
        print(LOCK_MESSAGE, file=sys.stderr)
        return 1

    if args.dry_run:
        client: object = DecliningClient()
    else:
        load_dotenv()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "no ANTHROPIC_API_KEY. Put it in control-evals/.env or set it in the "
                "environment. Nothing has been spent.\n"
                "To check the pipeline works without spending anything: --dry-run",
                file=sys.stderr,
            )
            return 1

        try:
            import anthropic
        except ImportError:
            print(
                "the anthropic package is not installed: py -m pip install -e .",
                file=sys.stderr,
            )
            return 1
        client = anthropic.Anthropic()

    agent = PaymentsAgent(
        client,
        model=args.model,
        effort=args.effort,
        max_turns=args.max_turns,
    )

    def report(result) -> None:
        mark = "VIOLATED" if result.violated else "ok      "
        note = result.violation or result.error or ""
        print(f"  {mark} {result.scenario_id:<16} {result.turns:>2} turns  {note}")

    print(f"{args.model}{' effort=' + args.effort if args.effort else ''} on split {args.split}\n")

    try:
        run = run_split(
            agent,
            SUITE,
            splits,
            args.split,
            reason=args.reason,
            limit=args.limit,
            on_result=report,
        )
    except HeldoutLocked as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not args.dry_run:
        for result in run.results:
            budget_module.record(
                result.model, result.usage, note=f"{args.split}/{result.scenario_id}"
            )

    print()
    print(format_frontier(summarise(run.results)))

    print("\nby category:")
    for category, frontier in by_category(run.results).items():
        print(f"  {category:<20} violation {frontier.violation}  completion {frontier.completion}")

    if args.dry_run:
        print(
            "\nDRY RUN — the agent declined everything without calling a tool. These are not "
            "results, they are proof the pipeline runs. Note where a refuse-everything agent "
            "sits on the frontier: no violations, and useless."
        )
        return 0

    path = run.save()
    print(f"\nwritten to {path.relative_to(REPO_ROOT)}")
    print(
        "The traces are in there. Read them before believing the rates — the failure "
        "taxonomy is the deliverable, the numbers are the index to it."
    )
    return 0


def cmd_budget() -> int:
    totals = budget_module.summary()
    print(f"{totals['calls']} calls, ${totals['total_usd']:.4f}")
    for model, bucket in sorted(totals["by_model"].items()):
        print(f"  {model:<22} {bucket['calls']:>5} calls  ${bucket['usd']:.4f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="control-evals", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("scenarios", help="list the suite")
    sub.add_parser("budget", help="what this project has cost so far")

    run_parser = sub.add_parser("run", help="run an agent against a split")
    run_parser.add_argument("--split", choices=SPLITS, default="dev")
    run_parser.add_argument("--model", default=DEFAULT_MODEL)
    run_parser.add_argument(
        "--effort",
        default="",
        choices=["", "low", "medium", "high", "xhigh", "max"],
        help="how much thinking. Sweeping this is one of the experiments.",
    )
    run_parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    run_parser.add_argument("--limit", type=int, default=0, help="run only the first N")
    run_parser.add_argument("--reason", default="", help="required for heldout, and logged")
    run_parser.add_argument(
        "--force", action="store_true", help="run even if the suite has drifted from the freeze"
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="exercise the whole pipeline with a canned declining agent. No API key, no cost.",
    )

    splits_parser = sub.add_parser("splits", help="dev/test/heldout assignment")
    splits_sub = splits_parser.add_subparsers(dest="splits_command")

    freeze_parser = splits_sub.add_parser("freeze", help="cut the splits, once")
    freeze_parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    freeze_parser.add_argument("--force", action="store_true", help="re-cut an existing freeze")

    splits_sub.add_parser("assign-new", help="place families added since the freeze")
    splits_sub.add_parser("status", help="the assignment and the heldout access log")
    splits_sub.add_parser("check", help="verify the frozen split against the suite")

    show_parser = splits_sub.add_parser("show", help="the scenarios in one split")
    show_parser.add_argument("split", choices=SPLITS)
    show_parser.add_argument("--reason", default="", help="required for heldout, and logged")

    refingerprint_parser = splits_sub.add_parser(
        "refingerprint", help="accept edits to existing scenarios"
    )
    refingerprint_parser.add_argument("--yes", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scenarios":
        return cmd_scenarios()

    if args.command == "budget":
        return cmd_budget()

    if args.command == "run":
        return cmd_run(args)

    if args.command == "splits":
        if args.splits_command == "freeze":
            return cmd_splits_freeze(args)
        if args.splits_command == "assign-new":
            return cmd_splits_assign_new()
        if args.splits_command == "status":
            return cmd_splits_status()
        if args.splits_command == "check":
            return cmd_splits_check()
        if args.splits_command == "show":
            return cmd_splits_show(args)
        if args.splits_command == "refingerprint":
            return cmd_splits_refingerprint(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
