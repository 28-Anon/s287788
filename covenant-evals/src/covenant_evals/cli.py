"""Command line entry points.

python -m covenant_evals.cli validate   # check every item against the schema
python -m covenant_evals.cli budget     # what this project has cost so far
"""

from __future__ import annotations

import argparse
import sys

from . import budget as budget_module
from .items import load_all, validate_all


def cmd_validate() -> int:
    try:
        items = load_all()
    except (ValueError, TypeError) as exc:
        print(f"could not load items: {exc}", file=sys.stderr)
        return 1

    if not items:
        print("0 items — nothing to validate yet. That is expected until week 4.")
        return 0

    problems = validate_all(items)
    for item_id in sorted(problems):
        for message in problems[item_id]:
            print(f"{item_id}: {message}", file=sys.stderr)

    if problems:
        print(f"\n{len(problems)} of {len(items)} items have problems", file=sys.stderr)
        return 1

    print(f"{len(items)} items, all valid")
    return 0


def cmd_budget() -> int:
    totals = budget_module.summary()
    print(f"calls: {totals['calls']}")
    print(f"total: ${totals['total_usd']}")
    for model, bucket in sorted(totals["by_model"].items()):  # type: ignore[union-attr]
        print(f"  {model}: {bucket['calls']} calls, ${bucket['usd']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="covenant-evals")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="check every item against the schema")
    sub.add_parser("budget", help="report API spend so far")

    args = parser.parse_args(argv)
    if args.command == "validate":
        return cmd_validate()
    if args.command == "budget":
        return cmd_budget()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
