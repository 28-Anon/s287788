"""Loading item files from disk and validating them as a set.

Items live one-per-file in data/items/ so that adding or changing a label shows up as a
readable diff. That matters more than it sounds: the labels *are* the valuable part of this
project, and you want every change to them to be reviewable months later.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import yaml

from .schema import Item, validate

ITEMS_DIR = Path(__file__).resolve().parents[2] / "data" / "items"


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
    """Validate each item, plus the set-level rule that ids are unique.

    Returns a mapping of item id -> problems. Empty mapping means everything is valid.
    """
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
