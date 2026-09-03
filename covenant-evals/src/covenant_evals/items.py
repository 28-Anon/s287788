"""Loading, writing and checking item files.

Items live one-per-file in data/items/ so that adding or changing a label shows up as a
readable diff. That matters more than it sounds: the labels *are* the valuable part of this
project, and you want every change to them reviewable months later.

Two levels of checking, and the second is the one that matters:

- `validate` (in schema.py) checks an item against itself. Fast, no corpus needed.
- `cross_validate` (here) checks an item against **the document it cites** — that the hash
  still matches, that the section exists, that the quoted text really appears at those
  offsets, and that the quote is inside the section the item claims it came from.

The second catches the errors that actually happen: a quote pasted from the wrong section,
a span copied from a previous item, a document re-fetched after the label was written.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import yaml

from .corpus.manifest import DEFAULT_CACHE, Agreement, Manifest
from .corpus.normalise import sha256_text
from .corpus.sections import segment, verify_span
from .schema import Item, validate
from .splits import Splits, require_open

REPO_ROOT = Path(__file__).resolve().parents[2]
ITEMS_DIR = REPO_ROOT / "data" / "items"

#: The order fields are written in. Chosen so a reviewer reads identity, then the question,
#: then the answer, then the evidence — the order you would check them in.
_WRITE_ORDER = (
    "id",
    "doc",
    "doc_sha256",
    "section",
    "question",
    "answer_type",
    "gold",
    "unit",
    "enum_options",
    "gold_citation",
    "gold_span",
    "rationale",
    "difficulty",
    "traps",
    "labelled_by",
    "labelled_at",
    "review_status",
    "dispute_note",
)


def _coerce_date(value: object) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    raise TypeError(f"labelled_at must be a date, got {type(value).__name__}")


def load_item(path: Path) -> Item:
    """Read one YAML file into an Item. Raises if required fields are missing."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: expected a YAML mapping at the top level")
    raw["labelled_at"] = _coerce_date(raw.get("labelled_at"))
    raw.setdefault("traps", [])
    try:
        return Item(**raw)
    except TypeError as exc:  # unexpected or missing keys
        raise ValueError(f"{path.name}: {exc}") from exc


def load_all(items_dir: Path | None = None) -> list[Item]:
    """Load every item file, sorted by id for stable ordering."""
    directory = items_dir or ITEMS_DIR
    items = [load_item(p) for p in sorted(directory.glob("*.yaml"))]
    return sorted(items, key=lambda i: i.id)


def validate_all(items: list[Item]) -> dict[str, list[str]]:
    """Validate each item, plus the set-level rule that ids are unique."""
    problems: dict[str, list[str]] = {}

    for item in items:
        errors = validate(item)
        if errors:
            problems[item.id] = errors

    seen: dict[str, int] = {}
    for item in items:
        seen[item.id] = seen.get(item.id, 0) + 1
    for item_id, count in seen.items():
        if count > 1:
            problems.setdefault(item_id, []).append(f"duplicate id used by {count} files")

    return problems


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


#: Highest id ever issued, committed alongside the items. Scanning the directory is not
#: enough: delete cov-0007 and a rescan would hand that id to a different question, while
#: stored run results still refer to the old one. Ids are permanent even when items are not.
ID_COUNTER = ".id-counter"


def _highest_on_disk(directory: Path) -> int:
    highest = 0
    for path in directory.glob("cov-*.yaml"):
        match = re.fullmatch(r"cov-(\d+)", path.stem)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def _highest_issued(directory: Path) -> int:
    counter = directory / ID_COUNTER
    if not counter.exists():
        return 0
    try:
        return int(counter.read_text(encoding="utf-8").strip())
    except ValueError:
        return 0


def next_item_id(items_dir: Path | None = None) -> str:
    """The next free id, e.g. "cov-0042". Has no side effects — write_item bumps the counter."""
    directory = items_dir or ITEMS_DIR
    return f"cov-{max(_highest_on_disk(directory), _highest_issued(directory)) + 1:04d}"


class _BlockDumper(yaml.SafeDumper):
    """Writes long strings as literal blocks so a quote is readable in a diff."""


def _represent_str(dumper: yaml.SafeDumper, value: str):
    if "\n" in value or len(value) > 70:
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", value)


_BlockDumper.add_representer(str, _represent_str)


def item_to_yaml(item: Item) -> str:
    """Serialise an item in a fixed field order.

    Long strings become literal blocks, which adds a trailing newline when read back.
    That is harmless: every comparison against the document normalises whitespace.
    """
    payload = {}
    for name in _WRITE_ORDER:
        value = getattr(item, name)
        if value in ("", [], None) and name not in {"gold", "gold_citation", "gold_span"}:
            continue
        payload[name] = value.isoformat() if isinstance(value, date) else value

    return yaml.dump(payload, Dumper=_BlockDumper, sort_keys=False, allow_unicode=True, width=88)


def write_item(item: Item, items_dir: Path | None = None) -> Path:
    """Write an item to data/items/<id>.yaml. Refuses to overwrite an existing file."""
    directory = items_dir or ITEMS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{item.id}.yaml"

    if path.exists():
        raise FileExistsError(f"{path} already exists — labels are never silently replaced")

    path.write_text(item_to_yaml(item), encoding="utf-8")

    match = re.fullmatch(r"cov-(\d+)", item.id)
    if match:
        issued = max(_highest_issued(directory), int(match.group(1)))
        (directory / ID_COUNTER).write_text(f"{issued}\n", encoding="utf-8")

    return path


# ---------------------------------------------------------------------------
# Cross-validation against the corpus
# ---------------------------------------------------------------------------


def find_agreement(manifest: Manifest, accession: str) -> Agreement | None:
    """The agreement an item cites. Items store an accession; the manifest keys on
    accession:filename, so this resolves the common case and refuses the ambiguous one."""
    matches = [a for a in manifest.agreements if a.accession == accession]
    return matches[0] if len(matches) == 1 else None


def cross_validate(
    items: list[Item],
    manifest: Manifest | None = None,
    *,
    cache_dir: Path = DEFAULT_CACHE,
) -> dict[str, list[str]]:
    """Check every item against the document it cites.

    Four questions, in the order they are worth asking:

    1. Is the document still the one you labelled? (hash)
    2. Does the section you cited exist? (segmenter)
    3. Does your quote actually appear at those offsets? (verify_span)
    4. Is the quote inside the section you said it came from?

    Number four is the quiet one. Quoting the right sentence from the wrong section is easy
    to do and produces an item that looks perfect and teaches the wrong lesson.
    """
    manifest = manifest or Manifest.load()
    problems: dict[str, list[str]] = {}
    text_cache: dict[str, str | None] = {}

    for item in items:
        errors: list[str] = []
        agreement = find_agreement(manifest, item.doc)

        if agreement is None:
            problems[item.id] = [
                f"{item.doc} is not in the manifest (or matches more than one file in it)"
            ]
            continue

        if agreement.ref not in text_cache:
            path = agreement.text_path(cache_dir)
            text_cache[agreement.ref] = path.read_text(encoding="utf-8") if path.exists() else None
        text = text_cache[agreement.ref]

        if text is None:
            problems[item.id] = [f"{agreement.ref} is not in the cache — run `corpus fetch`"]
            continue

        actual_hash = sha256_text(text)
        if actual_hash != item.doc_sha256:
            errors.append(
                "the document has changed since this item was labelled "
                f"(item pins {item.doc_sha256[:12]}…, cache holds {actual_hash[:12]}…). "
                "Re-read the section and re-check the answer before trusting this item."
            )

        segmentation = segment(text)
        section = segmentation.find(item.section)
        if section is None:
            errors.append(f"section {item.section!r} does not resolve in this document")

        if item.answer_type != "abstain" and item.gold_span and item.gold_citation:
            span = (item.gold_span[0], item.gold_span[1])
            if not verify_span(text, span, item.gold_citation):
                found = text[span[0] : span[1]][:60]
                errors.append(
                    f"gold_citation is not at gold_span. Those offsets hold {found!r}. "
                    "Use `corpus locate` rather than counting characters."
                )
            elif section is not None and not (section.start <= span[0] < section.end):
                errors.append(
                    f"the quote is verified, but it sits outside section {item.section} "
                    f"(section spans {section.start}–{section.end}, quote starts at {span[0]}). "
                    "Either the citation or the section is wrong."
                )

        if errors:
            problems[item.id] = errors

    return problems


def stats(items: list[Item]) -> dict[str, dict[str, int]]:
    """Counts by the dimensions the corpus needs to stay balanced on."""
    out: dict[str, dict[str, int]] = {
        "answer_type": {},
        "difficulty": {},
        "review_status": {},
        "trap": {},
        "document": {},
    }
    for item in items:
        out["answer_type"][item.answer_type] = out["answer_type"].get(item.answer_type, 0) + 1
        out["difficulty"][item.difficulty] = out["difficulty"].get(item.difficulty, 0) + 1
        out["review_status"][item.review_status] = (
            out["review_status"].get(item.review_status, 0) + 1
        )
        out["document"][item.doc] = out["document"].get(item.doc, 0) + 1
        for trap in item.traps:
            out["trap"][trap] = out["trap"].get(trap, 0) + 1
    return out


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------


def split_of(item: Item, manifest: Manifest, splits: Splits) -> str:
    """Which split an item belongs to — inherited from its document, never set per item."""
    agreement = find_agreement(manifest, item.doc)
    return splits.of(agreement.ref) if agreement else ""


def by_split(items: list[Item], manifest: Manifest, splits: Splits) -> dict[str, list[Item]]:
    """Group items by the split of the document they cite."""
    grouped: dict[str, list[Item]] = {}
    for item in items:
        grouped.setdefault(split_of(item, manifest, splits) or "unassigned", []).append(item)
    return grouped


def export(
    items: list[Item],
    split: str,
    manifest: Manifest,
    splits: Splits,
    *,
    reason: str = "",
    log_path: Path | None = None,
) -> list[dict[str, object]]:
    """The questions in a split, ready to hand to a system under test.

    **Gold answers are never exported.** The thing being measured must not receive the
    answer, the citation, or the rationale — and the cheapest way to guarantee that is for
    the export path to be structurally incapable of emitting them. Scoring reads the item
    files directly instead.

    Reading the heldout split goes through require_open, which demands a reason and writes
    it to a committed log.
    """
    require_open(split, reason=reason, log_path=log_path)

    selected = by_split(items, manifest, splits).get(split, [])
    return [
        {
            "id": item.id,
            "doc": item.doc,
            "section": item.section,
            "question": item.question,
            "answer_type": item.answer_type,
            **({"unit": item.unit} if item.unit else {}),
            **({"enum_options": item.enum_options} if item.enum_options else {}),
        }
        for item in sorted(selected, key=lambda i: i.id)
    ]
