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
from .corpus import (
    NORMALISER_VERSION,
    SEGMENTER_VERSION,
    EdgarClient,
    EdgarError,
    Manifest,
    find_spans,
    segment,
)
from .corpus.fetch import agreement_from_hit, fetch_all, load_text
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
    stale_sections = manifest.stale_sections(SEGMENTER_VERSION)

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
    if stale_sections:
        print(f"\nSEGMENTED BY AN OLDER SEGMENTER: {len(stale_sections)}")
        print("  Offsets are fine; section addresses may resolve elsewhere.")

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


def _load(ref: str) -> tuple[str, str]:
    """Return (ref, normalised text) for a manifest entry, or raise SystemExit with help."""
    manifest = Manifest.load()
    agreement = manifest.get(ref)

    if agreement is None:
        matches = [a for a in manifest.agreements if ref in a.ref]
        if len(matches) == 1:
            agreement = matches[0]
        elif matches:
            raise SystemExit(
                f"{ref!r} matches {len(matches)} documents. Be more specific:\n  "
                + "\n  ".join(a.ref for a in matches[:10])
            )
        else:
            raise SystemExit(f"{ref!r} is not in the manifest. Try `corpus status`.")

    try:
        return agreement.ref, load_text(agreement)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc


def cmd_corpus_sections(args: argparse.Namespace) -> int:
    """Print the section tree, or check every document at once."""
    if args.check:
        return _check_all_segmentation()

    ref, text = _load(args.ref)
    result = segment(text)

    for section in result:
        indent = "  " * section.level
        title = f"  {section.title}" if section.title else ""
        print(f"{indent}{section.label:<10}{title}")
        if args.offsets:
            print(f"{indent}          [{section.start}, {section.end}]  {section.char_count:,} ch")

    print(f"\n{ref}: {result.count} sections, {len(text):,} characters")
    if result.toc_entries_dropped:
        print(f"contents entries dropped: {result.toc_entries_dropped}")
    for warning in result.warnings:
        print(f"WARNING: {warning}")

    return 0


def _check_all_segmentation() -> int:
    """Segment every fetched document and report anything suspicious.

    Run this after any change to the segmenter. A rule that fixes one document and breaks
    three others is the normal outcome of tuning heuristics, and this is how you see it.
    """
    manifest = Manifest.load()
    fetched = [a for a in manifest.agreements if a.is_fetched]

    if not fetched:
        print("nothing fetched yet — run `make corpus-fetch` first")
        return 0

    problems = 0
    for agreement in fetched:
        result = segment(load_text(agreement))
        flag = "  <-- CHECK" if result.warnings else ""
        drift = (
            f"  (was {agreement.section_count})"
            if agreement.section_count and agreement.section_count != result.count
            else ""
        )
        print(f"{result.count:>4} sections  {agreement.ref}{drift}{flag}")
        for warning in result.warnings:
            print(f"             {warning}")
            problems += 1

    print(f"\n{len(fetched)} documents, {problems} warning(s)")
    return 1 if problems else 0


def cmd_corpus_section(args: argparse.Namespace) -> int:
    """Print one section, its offsets, and a gold_span line ready to paste into an item."""
    ref, text = _load(args.ref)
    result = segment(text)
    section = result.find(args.address)

    if section is None:
        available = [s.label for s in result if s.level <= 1][:20]
        print(
            f"{args.address!r} not found in {ref}.\nSections available: "
            f"{', '.join(available)}{'...' if len(available) == 20 else ''}",
            file=sys.stderr,
        )
        return 1

    body = section.body(text) if args.body else section.text(text)
    start = section.body_start if args.body else section.start

    print(f"# {ref}  §{args.address}")
    print(f"# chars [{start}, {section.end}]  ({section.end - start:,})")
    print(f"gold_span: [{start}, {section.end}]")
    print()
    print(body if not args.quiet else body[:2000])
    return 0


def cmd_corpus_locate(args: argparse.Namespace) -> int:
    """Find the character offsets of a quote — what you need to fill in gold_span.

    Reports every match, because a quote appearing more than once is a labelling hazard:
    the span you record may not be the passage you meant.
    """
    ref, text = _load(args.ref)
    spans = find_spans(text, args.quote)

    if not spans:
        print(
            "not found. The quote must appear verbatim (whitespace aside) — check for a "
            "smart quote, an en dash, or a word you retyped.",
            file=sys.stderr,
        )
        return 1

    result = segment(text)
    for start, end in spans:
        owner = next(
            (s.label for s in sorted(result, key=lambda s: -s.level) if s.start <= start < s.end),
            "?",
        )
        print(f"gold_span: [{start}, {end}]   section {owner}")
        print(
            f"  ...{text[max(0, start - 60) : start]}[{text[start:end]}]{text[end : end + 60]}..."
        )
        print()

    if len(spans) > 1:
        print(
            f"{len(spans)} matches — this citation is AMBIGUOUS. Quote more context until "
            "there is exactly one, or the span you record may not be the one you meant.",
            file=sys.stderr,
        )
        return 1

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

    sections = corpus_sub.add_parser("sections", help="print the section tree")
    sections.add_argument("ref", nargs="?", default="", help="accession:filename, or part of it")
    sections.add_argument("--offsets", action="store_true", help="show character ranges")
    sections.add_argument(
        "--check", action="store_true", help="segment every fetched document and report problems"
    )

    section = corpus_sub.add_parser("section", help="print one section and its offsets")
    section.add_argument("ref")
    section.add_argument("address", help="e.g. 7.02, 7.02(b), 23.1(a)(ii)")
    section.add_argument("--body", action="store_true", help="omit the heading line")
    section.add_argument("--quiet", action="store_true", help="first 2000 characters only")

    locate = corpus_sub.add_parser("locate", help="find the offsets of a quote")
    locate.add_argument("ref")
    locate.add_argument("quote", help="the text you want to cite, in quotes")

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
            if args.corpus_command == "sections":
                return cmd_corpus_sections(args)
            if args.corpus_command == "section":
                return cmd_corpus_section(args)
            if args.corpus_command == "locate":
                return cmd_corpus_locate(args)
            if args.corpus_command == "status":
                return cmd_corpus_status()
    except EdgarError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
