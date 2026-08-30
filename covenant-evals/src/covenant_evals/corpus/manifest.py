"""The corpus manifest: what is in the corpus, and how to prove it has not changed.

This file is committed. The documents are not. Anyone who clones the repository can run
`corpus fetch` and end up with byte-identical text to the text your labels were written
against — or find out loudly that they cannot, which is equally useful information.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = REPO_ROOT / "data" / "corpus" / "manifest.json"
DEFAULT_CACHE = REPO_ROOT / "data" / "corpus" / "cache"

SCHEMA_VERSION = 1


@dataclass
class Agreement:
    """One credit agreement in the corpus."""

    accession: str
    filename: str
    cik: str
    company: str
    form: str
    filed: str

    # Populated by `corpus fetch`; empty until then.
    raw_sha256: str = ""
    text_sha256: str = ""
    char_count: int = 0
    normaliser_version: int = 0
    fetched_at: str = ""

    #: Which law the agreement is governed by: "NY", "English", "Delaware", or "" if not
    #: yet checked. This is NOT the same as where the document was filed. EDGAR is a US
    #: filing system, but plenty of documents on it are English-law LMA-style facility
    #: agreements — filed by UK groups with US listings, or by US groups borrowing in
    #: London. Drafting conventions differ enough between the two traditions that a system
    #: strong on one may be weak on the other, and nobody has measured it.
    governing_law: str = ""

    #: Free-text. Why this agreement is in the corpus — sponsor-backed leveraged loan,
    #: investment-grade revolver, has three later amendments, and so on. Used in
    #: LIMITATIONS.md to describe how the corpus was selected.
    note: str = ""

    #: Which split this document's items belong to. Assigned in week 5, by document,
    #: never by item.
    split: str = ""

    @property
    def ref(self) -> str:
        return f"{self.accession}:{self.filename}"

    @property
    def is_fetched(self) -> bool:
        return bool(self.text_sha256)

    def cache_path(self, cache_dir: Path = DEFAULT_CACHE) -> Path:
        return cache_dir / self.accession / self.filename

    def text_path(self, cache_dir: Path = DEFAULT_CACHE) -> Path:
        return cache_dir / self.accession / f"{self.filename}.txt"


@dataclass
class Manifest:
    agreements: list[Agreement] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
    note: str = (
        "Accession numbers and hashes only. The filings themselves are never committed — "
        "run `make corpus-fetch` to rebuild data/corpus/cache/, which is gitignored."
    )

    # -- persistence ---------------------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None) -> Manifest:
        target = path or DEFAULT_MANIFEST
        if not target.exists():
            return cls()

        payload = json.loads(target.read_text(encoding="utf-8"))
        known = set(Agreement.__dataclass_fields__)
        agreements = [
            Agreement(**{k: v for k, v in entry.items() if k in known})
            for entry in payload.get("agreements", [])
        ]
        return cls(
            agreements=sorted(agreements, key=lambda a: a.ref),
            schema_version=payload.get("schema_version", SCHEMA_VERSION),
            note=payload.get("note", cls.note),
        )

    def save(self, path: Path | None = None) -> None:
        target = path or DEFAULT_MANIFEST
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.schema_version,
            "note": self.note,
            "agreements": [asdict(a) for a in sorted(self.agreements, key=lambda a: a.ref)],
        }
        # Trailing newline and sorted order keep diffs readable when agreements are added.
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # -- queries -------------------------------------------------------------------

    def get(self, ref: str) -> Agreement | None:
        return next((a for a in self.agreements if a.ref == ref), None)

    def add(self, agreement: Agreement) -> bool:
        """Add an agreement. Returns False if it was already there — adding is idempotent."""
        if self.get(agreement.ref) is not None:
            return False
        self.agreements.append(agreement)
        return True

    def pending(self) -> list[Agreement]:
        """Agreements in the manifest that have not been fetched and hashed yet."""
        return [a for a in self.agreements if not a.is_fetched]

    def stale(self, current_version: int) -> list[Agreement]:
        """Fetched agreements whose text was produced by an older normaliser.

        Any item labelled against one of these has character offsets that may no longer
        point where it thinks. Re-normalise, then re-check those items by hand.
        """
        return [
            a for a in self.agreements if a.is_fetched and a.normaliser_version != current_version
        ]
