"""Command line entry points.

python -m covenant_evals.cli validate          # check every item against the schema
python -m covenant_evals.cli budget            # what this project has cost so far
python -m covenant_evals.cli corpus search     # find candidate agreements on EDGAR
python -m covenant_evals.cli corpus add        # put one into the manifest
python -m covenant_evals.cli corpus fetch      # download, normalise, hash, cache
python -m covenant_evals.cli corpus status     # what state the corpus is in
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import budget as budget_module
from .corpus import NORMALISER_VERSION, EdgarClient, EdgarError, Manifest
from .corpus.fetch import agreement_from_hit, fetch_all
from .items import load_all, validate_all

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """Read KEY=value lines from .env into the environment.

    Deliberately tiny and dependency-free. Existing environment variables always win, so
    `EDGAR_USER_AGENT=... python -m covenant_evals.cli ...` overrides the file.
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


def make_client() -> EdgarClient:
    load_dotenv()
    return EdgarClient(user_agent=os.environ.get("EDGAR_USER_AGENT", ""))


# ---------------------------------------------------------------------------
# items and budget
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------


def cmd_corpus_search(args: argparse.Namespace) -> int:
    client = make_client()
    hits = client.search(
        args.query,
        forms=args.forms.split(",") if args.forms else None,
        start_date=args.start,
        end_date=args.end,
        limit=args.limit,
    )

    if not hits:
        print("no hits. Try quoting the phrase: --query '\"credit agreement\"'")
        return 0

    for hit in hits:
        print(f"{hit.ref}\n    {hit.company}  {hit.form}  {hit.filed}\n    {hit.url}")
    print(f"\n{len(hits)} hits. Add one with:  corpus add <accession:filename>")
    return 0


def cmd_corpus_add(args: argparse.Namespace) -> int:
    if ":" not in args.ref:
        print("ref must be accession:filename, as printed by `corpus search`", file=sys.stderr)
        return 1

    accession, filename = args.ref.split(":", 1)
    manifest = Manifest.load()

    if manifest.get(args.ref) is not None:
        print(f"{args.ref} is already in the manifest")
        return 0

    client = make_client()
    try:
        # Confirm the document exists and pick up its exhibit type before committing to it.
        index = client.filing_index(args.cik, accession)
    except EdgarError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    entry = next((i for i in index if i.get("name") == filename), None)
    if entry is None:
        available = ", ".join(str(i.get("name")) for i in index[:10])
        print(f"{filename} is not in that filing. First few files: {available}", file=sys.stderr)
        return 1

    from .corpus.edgar import Hit

    hit = Hit(
        accession=accession,
        filename=filename,
        cik=args.cik,
        company=args.company or "",
        form=str(entry.get("type", "")),
        filed=args.filed or "",
    )
    manifest.add(
        agreement_from_hit(hit, note=args.note or "", governing_law=args.governing_law or "")
    )
    manifest.save()
    print(f"added {args.ref} ({entry.get('type')}). Run `corpus fetch` to download it.")
    return 0


def cmd_corpus_fetch(args: argparse.Namespace) -> int:
    manifest = Manifest.load()
    if not manifest.agreements:
        print("manifest is empty — nothing to fetch. Use `corpus search` then `corpus add`.")
        return 0

    try:
        client = make_client()
    except EdgarError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    results = fetch_all(client, manifest, force=args.force)
    manifest.save()

    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
        if result.status in {"conflict", "failed"}:
            print(f"{result.status.upper()}  {result.ref}\n    {result.detail}", file=sys.stderr)
        else:
            print(f"{result.status:8} {result.ref}  {result.char_count:,} chars")

    print("\n" + "  ".join(f"{status}: {n}" for status, n in sorted(counts.items())))
    return 1 if counts.get("failed") or counts.get("conflict") else 0


def cmd_corpus_status() -> int:
    manifest = Manifest.load()
    total = len(manifest.agreements)
    fetched = [a for a in manifest.agreements if a.is_fetched]
    stale = manifest.stale(NORMALISER_VERSION)

    print(f"agreements in manifest: {total}")
    print(f"fetched and hashed:     {len(fetched)}")
    print(f"pending:                {len(manifest.pending())}")
    if fetched:
        chars = sum(a.char_count for a in fetched)
        print(f"total text:             {chars:,} chars (~{chars // 4:,} tokens, rough)")
    if stale:
        print(f"\nSTALE (normaliser has changed since these were hashed): {len(stale)}")
        for agreement in stale:
            print(f"  {agreement.ref}  v{agreement.normaliser_version} -> v{NORMALISER_VERSION}")
        print("  Items labelled against these have offsets that may no longer be correct.")

    by_law: dict[str, int] = {}
    for agreement in manifest.agreements:
        by_law[agreement.governing_law or "unchecked"] = (
            by_law.get(agreement.governing_law or "unchecked", 0) + 1
        )
    if manifest.agreements:
        print("\ngoverning law:")
        for law, count in sorted(by_law.items()):
            print(f"  {law:<10} {count}")
        english = by_law.get("English", 0)
        if english < 5:
            print(f"  target is at least 5 English-law agreements; {5 - english} to go")

    if total < 25:
        print(f"\ntarget for week 3 is 25 agreements; {25 - total} to go")
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="covenant-evals")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="check every item against the schema")
    sub.add_parser("budget", help="report API spend so far")

    corpus = sub.add_parser("corpus", help="build and inspect the document corpus")
    corpus_sub = corpus.add_subparsers(dest="corpus_command", required=True)

    search = corpus_sub.add_parser("search", help="EDGAR full-text search")
    search.add_argument("--query", required=True, help="quote phrases: '\"credit agreement\"'")
    search.add_argument("--forms", default="8-K", help="comma-separated, e.g. 8-K,10-Q")
    search.add_argument("--start", help="YYYY-MM-DD (requires --end)")
    search.add_argument("--end", help="YYYY-MM-DD (requires --start)")
    search.add_argument("--limit", type=int, default=20)

    add = corpus_sub.add_parser("add", help="add one document to the manifest")
    add.add_argument("ref", help="accession:filename, as printed by `corpus search`")
    add.add_argument("--cik", required=True)
    add.add_argument("--company", help="for readability in the manifest")
    add.add_argument("--filed", help="YYYY-MM-DD")
    add.add_argument("--note", help="why this document is in the corpus")
    add.add_argument(
        "--governing-law",
        choices=["NY", "English", "Delaware", "other"],
        help="which law governs the agreement — not where it was filed",
    )

    fetch = corpus_sub.add_parser("fetch", help="download, normalise, hash, cache")
    fetch.add_argument("--force", action="store_true", help="re-download and re-hash")

    corpus_sub.add_parser("status", help="what state the corpus is in")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "validate":
            return cmd_validate()
        if args.command == "budget":
            return cmd_budget()
        if args.command == "corpus":
            if args.corpus_command == "search":
                return cmd_corpus_search(args)
            if args.corpus_command == "add":
                return cmd_corpus_add(args)
            if args.corpus_command == "fetch":
                return cmd_corpus_fetch(args)
            if args.corpus_command == "status":
                return cmd_corpus_status()
    except EdgarError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
