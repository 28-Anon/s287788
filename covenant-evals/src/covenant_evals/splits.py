"""Splitting the corpus into dev, test and heldout — and keeping heldout shut.

Two things make this more than a shuffle.

**Split by document, never by item.** Two questions about the same clause, one in dev and
one in test, are not independent: tune against the first and you have tuned against the
second. Every item from one agreement lives in one split, always.

**Heldout has to be genuinely hard to open.** The point of a heldout split is that no
decision you make was informed by it. Discipline alone will not hold that for seventeen
weeks, so opening it requires an explicit reason and leaves a permanent record. When you
publish in week 22, that log is the evidence that you opened it once — which is a claim
worth much more than a high score.

At freeze time most documents have no items yet, so the assignment targets **shares of
text** rather than shares of items, greedily, using char_count as the proxy.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .corpus.manifest import Agreement, Manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPLITS = REPO_ROOT / "data" / "splits.json"
DEFAULT_ACCESS_LOG = REPO_ROOT / "runs" / "heldout-access.log"

SCHEMA_VERSION = 1

SPLITS = ("dev", "test", "heldout")

#: Shares of the corpus, by text volume. dev is small because you look at it constantly;
#: heldout is large enough that a result on it means something.
DEFAULT_TARGETS = {"dev": 0.16, "test": 0.56, "heldout": 0.28}

#: Documents are shuffled inside their stratum before assignment. Recorded in splits.json
#: so the assignment can be reproduced from scratch.
DEFAULT_SEED = 20261005


class HeldoutLocked(RuntimeError):
    """Raised when something tries to read the heldout split without saying why."""


class SplitsFrozen(RuntimeError):
    """Raised when something tries to reassign a document after the freeze."""


@dataclass
class Splits:
    assignment: dict[str, str] = field(default_factory=dict)  # ref -> split
    seed: int = DEFAULT_SEED
    targets: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TARGETS))
    frozen_at: str = ""
    manifest_sha256: str = ""
    schema_version: int = SCHEMA_VERSION

    # -- persistence ---------------------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None) -> Splits | None:
        target = path or DEFAULT_SPLITS
        if not target.exists():
            return None
        payload = json.loads(target.read_text(encoding="utf-8"))
        return cls(
            assignment=payload.get("assignment", {}),
            seed=payload.get("seed", DEFAULT_SEED),
            targets=payload.get("targets", dict(DEFAULT_TARGETS)),
            frozen_at=payload.get("frozen_at", ""),
            manifest_sha256=payload.get("manifest_sha256", ""),
            schema_version=payload.get("schema_version", SCHEMA_VERSION),
        )

    def save(self, path: Path | None = None) -> None:
        target = path or DEFAULT_SPLITS
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.schema_version,
            "note": (
                "Frozen split assignment, by document. Committed deliberately: a split you "
                "can silently change is not a split. Adding a document is allowed; moving "
                "one between splits is not."
            ),
            "frozen_at": self.frozen_at,
            "seed": self.seed,
            "targets": self.targets,
            "manifest_sha256": self.manifest_sha256,
            "assignment_sha256": self.assignment_sha256,
            "assignment": dict(sorted(self.assignment.items())),
        }
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # -- identity ------------------------------------------------------------------

    @property
    def assignment_sha256(self) -> str:
        """Fingerprint of the assignment itself, so a quiet edit is visible."""
        canonical = json.dumps(dict(sorted(self.assignment.items())), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @property
    def is_frozen(self) -> bool:
        return bool(self.frozen_at)

    def of(self, ref: str) -> str:
        return self.assignment.get(ref, "")

    def documents(self, split: str) -> list[str]:
        return sorted(ref for ref, value in self.assignment.items() if value == split)


def manifest_fingerprint(manifest: Manifest) -> str:
    """Hash of which documents exist, so drift since the freeze is detectable."""
    refs = json.dumps(sorted(a.ref for a in manifest.agreements))
    return hashlib.sha256(refs.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------


def _stratum(agreement: Agreement) -> str:
    """Documents are balanced across splits by governing law.

    If dev were all New York-law and heldout all English-law, a drop between the two would
    be indistinguishable from the split being harder — and the English-law comparison is
    one of the results this project exists to produce.
    """
    return agreement.governing_law or "unchecked"


def _assign(
    agreements: list[Agreement],
    targets: dict[str, float],
    seed: int,
    existing: dict[str, str] | None = None,
) -> dict[str, str]:
    """Greedily assign documents to splits, balancing text volume within each stratum.

    Deterministic given the same documents and seed. Existing assignments are preserved
    exactly — this is how documents added after the freeze are placed without disturbing
    anything already decided.
    """
    assignment = dict(existing or {})
    weight = {split: 0.0 for split in SPLITS}
    total = 0.0

    for agreement in agreements:
        if agreement.ref in assignment:
            size = float(agreement.char_count or 1)
            weight[assignment[agreement.ref]] += size
            total += size

    unassigned = [a for a in agreements if a.ref not in assignment]

    by_stratum: dict[str, list[Agreement]] = {}
    for agreement in unassigned:
        by_stratum.setdefault(_stratum(agreement), []).append(agreement)

    for stratum in sorted(by_stratum):
        documents = sorted(by_stratum[stratum], key=lambda a: a.ref)
        random.Random(f"{seed}:{stratum}").shuffle(documents)

        for agreement in documents:
            size = float(agreement.char_count or 1)
            projected = total + size
            # Give it to whichever split is furthest below its target share.
            deficit = {s: targets.get(s, 0.0) - (weight[s] / projected) for s in SPLITS}
            chosen = max(SPLITS, key=lambda s: (deficit[s], -weight[s], s))
            assignment[agreement.ref] = chosen
            weight[chosen] += size
            total = projected

    return assignment


def freeze(
    manifest: Manifest,
    *,
    seed: int = DEFAULT_SEED,
    targets: dict[str, float] | None = None,
) -> Splits:
    """Produce the initial assignment. Does not write — the caller decides that."""
    fetched = [a for a in manifest.agreements if a.is_fetched]
    if not fetched:
        raise ValueError("nothing fetched yet — there is nothing to split")

    resolved = targets or dict(DEFAULT_TARGETS)
    splits = Splits(
        assignment=_assign(fetched, resolved, seed),
        seed=seed,
        targets=resolved,
        frozen_at=datetime.now(UTC).isoformat(timespec="seconds"),
        manifest_sha256=manifest_fingerprint(manifest),
    )
    return splits


def assign_new(splits: Splits, manifest: Manifest) -> tuple[Splits, list[str]]:
    """Place documents added since the freeze, without moving anything already assigned."""
    fetched = [a for a in manifest.agreements if a.is_fetched]
    before = set(splits.assignment)

    splits.assignment = _assign(fetched, splits.targets, splits.seed, splits.assignment)
    splits.manifest_sha256 = manifest_fingerprint(manifest)

    added = sorted(set(splits.assignment) - before)
    return splits, added


def check(splits: Splits, manifest: Manifest) -> list[str]:
    """Everything that could be wrong with a frozen split. Empty list means it is sound."""
    problems: list[str] = []
    fetched = {a.ref: a for a in manifest.agreements if a.is_fetched}

    unassigned = sorted(set(fetched) - set(splits.assignment))
    if unassigned:
        problems.append(
            f"{len(unassigned)} fetched document(s) have no split: {', '.join(unassigned[:5])}"
            f"{'...' if len(unassigned) > 5 else ''}. Run `splits assign-new`."
        )

    orphaned = sorted(set(splits.assignment) - set(fetched))
    if orphaned:
        problems.append(
            f"{len(orphaned)} assigned document(s) are no longer fetched: "
            f"{', '.join(orphaned[:5])}. Removing a document from a frozen split changes "
            "what every past result meant."
        )

    for ref, split in sorted(splits.assignment.items()):
        if split not in SPLITS:
            problems.append(f"{ref} has unknown split {split!r}")

    for ref, agreement in sorted(fetched.items()):
        assigned = splits.of(ref)
        if assigned and agreement.split and agreement.split != assigned:
            problems.append(
                f"{ref}: manifest says split {agreement.split!r}, splits.json says "
                f"{assigned!r}. splits.json is authoritative — run `splits sync`."
            )

    for split in SPLITS:
        if not splits.documents(split):
            problems.append(f"split {split!r} has no documents at all")

    return problems


def sync_manifest(splits: Splits, manifest: Manifest) -> int:
    """Copy the authoritative assignment into the manifest for display. Returns changes."""
    changed = 0
    for agreement in manifest.agreements:
        assigned = splits.of(agreement.ref)
        if assigned and agreement.split != assigned:
            agreement.split = assigned
            changed += 1
    return changed


def shares(splits: Splits, manifest: Manifest) -> dict[str, dict[str, object]]:
    """Actual composition of each split, to compare against the targets."""
    by_ref = {a.ref: a for a in manifest.agreements}
    out: dict[str, dict[str, object]] = {}
    total_chars = sum(by_ref[r].char_count for r in splits.assignment if r in by_ref) or 1

    for split in SPLITS:
        refs = splits.documents(split)
        chars = sum(by_ref[r].char_count for r in refs if r in by_ref)
        laws: dict[str, int] = {}
        for ref in refs:
            if ref in by_ref:
                law = by_ref[ref].governing_law or "unchecked"
                laws[law] = laws.get(law, 0) + 1
        out[split] = {
            "documents": len(refs),
            "chars": chars,
            "share": chars / total_chars,
            "target": splits.targets.get(split, 0.0),
            "governing_law": laws,
        }
    return out


# ---------------------------------------------------------------------------
# The heldout lock
# ---------------------------------------------------------------------------


def require_open(
    split: str,
    *,
    reason: str = "",
    log_path: Path | None = None,
) -> None:
    """Gate every read of the heldout split. Call this before returning heldout content.

    dev and test pass through silently. heldout requires a reason, and every access is
    appended to runs/heldout-access.log — which is committed, and is the evidence that the
    split was opened once, in week 22, on purpose.

    The week 8 runner must call this. It is wired into `items export` today so that it is
    live and tested rather than a promise.
    """
    if split != "heldout":
        return

    if len(reason.strip()) < 10:
        raise HeldoutLocked(
            "the heldout split is closed until week 22.\n"
            "Opening it early is the single easiest way to invalidate this whole project: "
            "any decision informed by heldout turns it into a second test split.\n"
            "If you genuinely mean to open it, pass a reason of at least ten characters. "
            "It is written to runs/heldout-access.log, which is committed."
        )

    path = log_path or DEFAULT_ACCESS_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "reason": reason.strip(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def access_history(log_path: Path | None = None) -> list[dict[str, str]]:
    """Every time heldout has been opened. Publish this alongside your results."""
    path = log_path or DEFAULT_ACCESS_LOG
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
