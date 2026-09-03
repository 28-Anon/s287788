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
import json
import os
import sys
from datetime import date
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
from .items import (
    cross_validate,
    export,
    item_to_yaml,
    load_all,
    next_item_id,
    stats,
    validate_all,
    write_item,
)
from .schema import ANSWER_TYPES, DIFFICULTIES, TRAPS, UNITS, Item, validate
from .splits import (
    SPLITS,
    HeldoutLocked,
    Splits,
    access_history,
    assign_new,
    freeze,
    shares,
    sync_manifest,
)
from .splits import (
    check as check_splits,
)

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


def _load(ref: str):
    """Return (agreement, normalised text) for a manifest entry, or exit with help."""
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
        return agreement, load_text(agreement)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc


def cmd_corpus_sections(args: argparse.Namespace) -> int:
    """Print the section tree, or check every document at once."""
    if args.check:
        return _check_all_segmentation()

    agreement, text = _load(args.ref)
    result = segment(text)

    for section in result:
        indent = "  " * section.level
        title = f"  {section.title}" if section.title else ""
        print(f"{indent}{section.label:<10}{title}")
        if args.offsets:
            print(f"{indent}          [{section.start}, {section.end}]  {section.char_count:,} ch")

    print(f"\n{agreement.ref}: {result.count} sections, {len(text):,} characters")
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
    agreement, text = _load(args.ref)
    result = segment(text)
    section = result.find(args.address)

    if section is None:
        available = [s.label for s in result if s.level <= 1][:20]
        print(
            f"{args.address!r} not found in {agreement.ref}.\nSections available: "
            f"{', '.join(available)}{'...' if len(available) == 20 else ''}",
            file=sys.stderr,
        )
        return 1

    body = section.body(text) if args.body else section.text(text)
    start = section.body_start if args.body else section.start

    print(f"# {agreement.ref}  §{args.address}")
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
    agreement, text = _load(args.ref)
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
# items
# ---------------------------------------------------------------------------


def _parse_gold(answer_type: str, raw: str | None):
    """Turn the --gold string into the right Python type, or exit explaining why not."""
    if answer_type == "abstain":
        return None
    if raw is None:
        raise SystemExit("--gold is required unless --type abstain")

    if answer_type == "boolean":
        lowered = raw.strip().lower()
        if lowered in {"true", "yes", "y"}:
            return True
        if lowered in {"false", "no", "n"}:
            return False
        raise SystemExit(f"--gold {raw!r} is not a boolean. Use true or false.")

    if answer_type == "numeric":
        cleaned = raw.replace(",", "").replace("$", "").replace("£", "").strip()
        try:
            return float(cleaned) if "." in cleaned else int(cleaned)
        except ValueError as exc:
            raise SystemExit(f"--gold {raw!r} is not a number") from exc

    return raw


def cmd_items_new(args: argparse.Namespace) -> int:
    """Scaffold one item, filling in the hash, offsets and section from the document.

    Everything this fills in automatically is something you would otherwise get wrong by
    hand: the document hash, the character offsets, and whether your quote is actually in
    the section you think it is.
    """
    agreement, text = _load(args.ref)
    segmentation = segment(text)

    section = segmentation.find(args.section)
    if section is None:
        available = [s.label for s in segmentation if s.level <= 1][:25]
        raise SystemExit(
            f"section {args.section!r} does not resolve in {agreement.ref}.\n"
            f"Available: {', '.join(available)}"
        )

    gold_citation = None
    gold_span = None

    if args.type != "abstain":
        if not args.quote:
            raise SystemExit("--quote is required unless --type abstain")

        spans = find_spans(text, args.quote)
        if not spans:
            raise SystemExit(
                "that quote does not appear in the document. It must match verbatim "
                "(whitespace aside) — check for a smart quote, an en dash, or a retyped word."
            )
        if len(spans) > 1:
            raise SystemExit(
                f"that quote appears {len(spans)} times, so the span would be ambiguous. "
                "Quote more context until there is exactly one match."
            )

        start, end = spans[0]
        if not (section.start <= start < section.end):
            owner = next(
                (
                    s.label
                    for s in sorted(segmentation, key=lambda s: -s.level)
                    if s.start <= start < s.end
                ),
                "?",
            )
            raise SystemExit(
                f"the quote is in section {owner}, not {args.section}. "
                "Either the citation or the section is wrong — decide which before writing it."
            )

        gold_citation = text[start:end]
        gold_span = [start, end]

    item = Item(
        id=next_item_id(),
        doc=agreement.accession,
        doc_sha256=agreement.text_sha256 or "",
        section=args.section,
        question=args.question,
        answer_type=args.type,
        gold=_parse_gold(args.type, args.gold),
        gold_citation=gold_citation,
        gold_span=gold_span,
        rationale=args.rationale,
        difficulty=args.difficulty,
        labelled_by=args.by or os.environ.get("LABELLER", ""),
        labelled_at=date.today(),
        traps=[t.strip() for t in (args.traps or "").split(",") if t.strip()],
        unit=args.unit or "",
        enum_options=[o.strip() for o in (args.enum_options or "").split(",") if o.strip()],
    )

    errors = validate(item)
    if errors:
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        raise SystemExit("item is not valid — nothing written")

    if args.dry_run:
        print(item_to_yaml(item))
        return 0

    path = write_item(item)
    print(f"wrote {path.relative_to(REPO_ROOT)}")
    print(
        f"  section {args.section}, span [{gold_span[0]}, {gold_span[1]}]"
        if gold_span
        else f"  section {args.section}, abstain"
    )
    return 0


def cmd_items_check(args: argparse.Namespace) -> int:
    """Schema check, then check every item against the document it cites."""
    items = load_all()
    if not items:
        print("0 items — nothing to check yet. That is expected until you start labelling.")
        return 0

    problems = validate_all(items)

    if not args.schema_only:
        for item_id, errors in cross_validate(items).items():
            problems.setdefault(item_id, []).extend(errors)

    for item_id in sorted(problems):
        print(f"{item_id}:", file=sys.stderr)
        for message in problems[item_id]:
            print(f"  {message}", file=sys.stderr)

    if problems:
        print(f"\n{len(problems)} of {len(items)} items have problems", file=sys.stderr)
        return 1

    scope = "schema" if args.schema_only else "schema and documents"
    print(f"{len(items)} items, all valid against {scope}")
    return 0


def cmd_items_stats() -> int:
    items = load_all()
    if not items:
        print("0 items")
        return 0

    counts = stats(items)
    print(f"{len(items)} items across {len(counts['document'])} documents\n")

    for dimension in ("answer_type", "difficulty", "review_status", "trap"):
        print(dimension)
        for key, count in sorted(counts[dimension].items(), key=lambda kv: -kv[1]):
            share = count / len(items)
            print(f"  {key:<28} {count:>4}  {share:>5.0%}")
        print()

    abstain = counts["answer_type"].get("abstain", 0)
    share = abstain / len(items)
    print(f"abstain items: {abstain} ({share:.0%}) — target is about 20%")
    if share < 0.15:
        print("  under target. Questions the document does not answer are the ones that")
        print("  catch confident invention, and they are the easiest to under-collect.")

    thin = [t for t in sorted(TRAPS) if counts["trap"].get(t, 0) < 3]
    if thin:
        print(f"\ntraps with fewer than 3 items: {', '.join(thin)}")
    return 0


# ---------------------------------------------------------------------------
# splits
# ---------------------------------------------------------------------------


def _require_splits() -> Splits:
    splits = Splits.load()
    if splits is None:
        raise SystemExit("no splits yet — run `covenant-evals splits freeze` first")
    return splits


def cmd_splits_freeze(args: argparse.Namespace) -> int:
    existing = Splits.load()
    if existing is not None and existing.is_frozen and not args.force:
        raise SystemExit(
            f"splits were frozen at {existing.frozen_at} and will not be re-cut.\n"
            "A split you can silently redraw is not a split: every past result was "
            "measured against this one.\n"
            "To add documents fetched since the freeze, use `splits assign-new`."
        )

    manifest = Manifest.load()
    splits = freeze(manifest, seed=args.seed)
    sync_manifest(splits, manifest)
    splits.save()
    manifest.save()

    print(f"frozen at {splits.frozen_at}")
    print(f"seed {splits.seed}, assignment {splits.assignment_sha256[:12]}…\n")
    _print_shares(splits, manifest)
    print("\nCommit data/splits.json now. The heldout split is closed until week 22.")
    return 0


def cmd_splits_assign_new() -> int:
    splits = _require_splits()
    manifest = Manifest.load()
    splits, added = assign_new(splits, manifest)

    if not added:
        print("no new documents to assign")
        return 0

    sync_manifest(splits, manifest)
    splits.save()
    manifest.save()

    for ref in added:
        print(f"{splits.of(ref):<8} {ref}")
    print(f"\n{len(added)} document(s) assigned. Nothing already assigned was moved.")
    return 0


def _print_shares(splits: Splits, manifest: Manifest) -> None:
    for split, data in shares(splits, manifest).items():
        laws = ", ".join(f"{k}:{v}" for k, v in sorted(data["governing_law"].items()))
        print(
            f"  {split:<8} {data['documents']:>3} docs  {data['chars']:>9,} chars  "
            f"{data['share']:>5.0%} (target {data['target']:.0%})  {laws}"
        )


def cmd_splits_status() -> int:
    splits = Splits.load()
    if splits is None:
        print("splits not frozen yet")
        return 0

    manifest = Manifest.load()
    print(f"frozen at {splits.frozen_at}")
    print(f"seed {splits.seed}, assignment {splits.assignment_sha256[:12]}…\n")
    _print_shares(splits, manifest)

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
    manifest = Manifest.load()
    problems = check_splits(splits, manifest)

    for problem in problems:
        print(problem, file=sys.stderr)

    if problems:
        print(f"\n{len(problems)} problem(s)", file=sys.stderr)
        return 1

    print(f"{len(splits.assignment)} documents assigned, no problems")
    return 0


def cmd_splits_sync() -> int:
    splits = _require_splits()
    manifest = Manifest.load()
    changed = sync_manifest(splits, manifest)
    manifest.save()
    print(f"{changed} manifest entries updated from splits.json")
    return 0


def cmd_items_export(args: argparse.Namespace) -> int:
    """Emit the questions in a split, for handing to a system under test."""
    splits = _require_splits()
    manifest = Manifest.load()

    try:
        rows = export(load_all(), args.split, manifest, splits, reason=args.reason or "")
    except HeldoutLocked as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1

    print(json.dumps(rows, indent=2))
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="covenant-evals")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="check every item against the schema (alias of items check)")

    items = sub.add_parser("items", help="create and check labelled items")
    items_sub = items.add_subparsers(dest="items_command", required=True)

    new = items_sub.add_parser("new", help="scaffold one item from a document and a quote")
    new.add_argument("--ref", required=True, help="document: accession:filename, or part of it")
    new.add_argument("--section", required=True, help="e.g. 7.02(b)")
    new.add_argument("--question", required=True)
    new.add_argument("--type", required=True, choices=sorted(ANSWER_TYPES))
    new.add_argument("--gold", help="the answer; omit only for --type abstain")
    new.add_argument("--quote", help="verbatim text that proves the answer")
    new.add_argument("--rationale", required=True, help="why the answer follows from the quote")
    new.add_argument("--difficulty", default="medium", choices=sorted(DIFFICULTIES))
    new.add_argument("--traps", help="comma separated, from the vocabulary in schema.py")
    new.add_argument("--unit", choices=sorted(UNITS), help="required for numeric answers")
    new.add_argument("--enum-options", help="comma separated; required for enum answers")
    new.add_argument("--by", help="labeller initials (or set LABELLER in .env)")
    new.add_argument("--dry-run", action="store_true", help="print the item, write nothing")

    check = items_sub.add_parser("check", help="validate items against the schema and the corpus")
    check.add_argument(
        "--schema-only", action="store_true", help="skip the checks that need the corpus on disk"
    )

    items_sub.add_parser("stats", help="counts by answer type, difficulty and trap")

    export_cmd = items_sub.add_parser(
        "export", help="questions in a split, for a system under test (never gold answers)"
    )
    export_cmd.add_argument("--split", required=True, choices=list(SPLITS))
    export_cmd.add_argument("--reason", help="required for heldout; written to a committed log")

    splits_cmd = sub.add_parser("splits", help="freeze and inspect the dev/test/heldout split")
    splits_sub = splits_cmd.add_subparsers(dest="splits_command", required=True)

    freeze_cmd = splits_sub.add_parser("freeze", help="cut the split, once")
    freeze_cmd.add_argument("--seed", type=int, default=20261005)
    freeze_cmd.add_argument(
        "--force", action="store_true", help="re-cut an existing split (almost never right)"
    )

    splits_sub.add_parser("assign-new", help="place documents fetched since the freeze")
    splits_sub.add_parser("status", help="composition, and whether heldout was ever opened")
    splits_sub.add_parser("check", help="verify the split is sound")
    splits_sub.add_parser("sync", help="copy splits.json into the manifest for display")
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
        if args.command == "items":
            if args.items_command == "new":
                return cmd_items_new(args)
            if args.items_command == "check":
                return cmd_items_check(args)
            if args.items_command == "stats":
                return cmd_items_stats()
            if args.items_command == "export":
                return cmd_items_export(args)
        if args.command == "splits":
            if args.splits_command == "freeze":
                return cmd_splits_freeze(args)
            if args.splits_command == "assign-new":
                return cmd_splits_assign_new()
            if args.splits_command == "status":
                return cmd_splits_status()
            if args.splits_command == "check":
                return cmd_splits_check()
            if args.splits_command == "sync":
                return cmd_splits_sync()
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
