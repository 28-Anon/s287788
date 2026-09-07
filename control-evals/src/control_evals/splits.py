"""Splitting the scenario suite into dev, test and heldout — and keeping heldout shut.

Carried over from covenant-evals, where the unit of independence was the document. Here it
is the **scenario family**, and the reason is the same one.

**Split by family, never by scenario.** `limit-001` and `limit-002` share a policy, a world
and an invoice; the second is the first with the payment split in two. Tune a prompt against
one and you have tuned it against the other, so a suite that puts one in dev and the other
in test reports a test score that dev already bought. A family is the id up to the trailing
number: `limit-002` -> `limit`. Every scenario in a family lives in one split, always.

**Heldout has to be genuinely hard to open.** A scenario suite is *easier* to overfit than a
labelled corpus, not harder: the scenarios are written by the same person who reads the
failures, so every error analysis is a chance to quietly author the fix. Opening heldout
requires an explicit reason and appends to ``runs/heldout-access.log``, which is committed.
In week 22 that log is the evidence that it was opened once, which is a claim worth more
than whatever the number turns out to be.

**Balance is by scenario count, and it drifts.** At freeze time most families hold a single
scenario; weeks 6-8 grow them unevenly. Assignment therefore targets shares of the scenario
count *as it stands when a family is placed*, and :func:`shares` reports the drift since. The
alternative — reassigning to keep the shares exact — would mean moving families between
splits after results exist, which is the one thing a frozen split may never do.

**The coverage problem this design creates, stated plainly.** With one family per category,
a category can only land in one split, so a per-category violation rate cannot be computed on
test alone. :func:`coverage` reports this and :func:`check` raises it as a problem. It is not
a bug in the split; it is a statement about the suite being too small yet, and it clears when
weeks 6-8 give each category several families.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .scenario import CATEGORIES, Scenario

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPLITS = REPO_ROOT / "data" / "splits.json"
DEFAULT_ACCESS_LOG = REPO_ROOT / "runs" / "heldout-access.log"

SCHEMA_VERSION = 1

SPLITS = ("dev", "test", "heldout")

#: The splits that can be read without opening the lock. "Run the whole suite" means
#: these, and saying so out loud is better than leaving the heldout question implicit.
OPEN_SPLITS = ("dev", "test")

#: Shares of the suite, by scenario count. dev is larger than covenant-evals gave it (0.16)
#: because the suite is an order of magnitude smaller: a 16% dev split of 40 scenarios is six
#: scenarios, which is not enough to iterate against without reading all of them constantly.
#: heldout is 0.30 so that a violation rate measured on it has a confidence interval worth
#: printing.
DEFAULT_TARGETS = {"dev": 0.20, "test": 0.50, "heldout": 0.30}

#: Families are shuffled inside their stratum before assignment. Recorded in splits.json so
#: the assignment can be reproduced from scratch.
DEFAULT_SEED = 20260906

#: How many families a category needs before its results can be reported per split.
MIN_FAMILIES_PER_CATEGORY = 3

_FAMILY = re.compile(r"^(?P<family>[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*?)-(?P<number>\d+)$")


class HeldoutLocked(RuntimeError):
    """Raised when something tries to read the heldout split without saying why."""


class SplitsFrozen(RuntimeError):
    """Raised when something tries to reassign a family after the freeze."""


def family_of(scenario_id: str) -> str:
    """``limit-002`` -> ``limit``. The unit of independence.

    An id with no trailing number is its own family, which is the safe reading: a scenario
    nothing else shares a name with shares nothing else either.
    """
    match = _FAMILY.match(scenario_id.strip())
    return match.group("family") if match else scenario_id.strip()


def families(scenarios: Iterable[Scenario]) -> dict[str, list[Scenario]]:
    out: dict[str, list[Scenario]] = {}
    for scenario in scenarios:
        out.setdefault(family_of(scenario.id), []).append(scenario)
    for members in out.values():
        members.sort(key=lambda s: s.id)
    return out


@dataclass
class Splits:
    assignment: dict[str, str] = field(default_factory=dict)  # family -> split
    seed: int = DEFAULT_SEED
    targets: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TARGETS))
    frozen_at: str = ""
    suite_sha256: str = ""
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
            suite_sha256=payload.get("suite_sha256", ""),
            schema_version=payload.get("schema_version", SCHEMA_VERSION),
        )

    def save(self, path: Path | None = None) -> None:
        target = path or DEFAULT_SPLITS
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.schema_version,
            "note": (
                "Frozen split assignment, by scenario family. Committed deliberately: a "
                "split you can silently change is not a split. Adding a family is allowed "
                "and is what `splits assign-new` does; moving one between splits is not."
            ),
            "frozen_at": self.frozen_at,
            "seed": self.seed,
            "targets": self.targets,
            "suite_sha256": self.suite_sha256,
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

    def of(self, scenario_id: str) -> str:
        """The split a scenario belongs to, by way of its family."""
        return self.assignment.get(family_of(scenario_id), "")

    def family_split(self, family: str) -> str:
        return self.assignment.get(family, "")

    def family_names(self, split: str) -> list[str]:
        return sorted(name for name, value in self.assignment.items() if value == split)


def suite_fingerprint(scenarios: Iterable[Scenario]) -> str:
    """Hash of which scenarios exist, so drift since the freeze is detectable."""
    ids = json.dumps(sorted(s.id for s in scenarios))
    return hashlib.sha256(ids.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------


def _stratum(members: list[Scenario]) -> str:
    """Families are balanced across splits by category.

    If dev held every injection scenario and heldout every hard-limit one, a drop between
    the two would be indistinguishable from heldout simply being harder — and comparing
    categories is most of what this suite exists to do.
    """
    categories = {s.category for s in members}
    return sorted(categories)[0] if len(categories) == 1 else "mixed"


def _assign(
    grouped: dict[str, list[Scenario]],
    targets: dict[str, float],
    seed: int,
    existing: dict[str, str] | None = None,
) -> dict[str, str]:
    """Greedily assign families to splits, balancing scenario count within each stratum.

    Deterministic given the same families and seed. Existing assignments are preserved
    exactly — this is how families added after the freeze are placed without disturbing
    anything already decided.
    """
    assignment = dict(existing or {})
    weight = {split: 0.0 for split in SPLITS}
    total = 0.0

    for name, members in grouped.items():
        if name in assignment and assignment[name] in weight:
            size = float(len(members) or 1)
            weight[assignment[name]] += size
            total += size

    unplaced = {name: members for name, members in grouped.items() if name not in assignment}

    by_stratum: dict[str, list[str]] = {}
    for name, members in unplaced.items():
        by_stratum.setdefault(_stratum(members), []).append(name)

    for stratum in sorted(by_stratum):
        names = sorted(by_stratum[stratum])
        random.Random(f"{seed}:{stratum}").shuffle(names)

        for name in names:
            size = float(len(unplaced[name]) or 1)
            projected = total + size
            # Give it to whichever split is furthest below its target share.
            deficit = {s: targets.get(s, 0.0) - (weight[s] / projected) for s in SPLITS}
            chosen = max(SPLITS, key=lambda s: (deficit[s], -weight[s], s))
            assignment[name] = chosen
            weight[chosen] += size
            total = projected

    return assignment


def freeze(
    scenarios: Iterable[Scenario],
    *,
    seed: int = DEFAULT_SEED,
    targets: dict[str, float] | None = None,
) -> Splits:
    """Produce the initial assignment. Does not write — the caller decides that."""
    suite = list(scenarios)
    if not suite:
        raise ValueError("no scenarios — there is nothing to split")

    resolved = targets or dict(DEFAULT_TARGETS)
    return Splits(
        assignment=_assign(families(suite), resolved, seed),
        seed=seed,
        targets=resolved,
        frozen_at=datetime.now(UTC).isoformat(timespec="seconds"),
        suite_sha256=suite_fingerprint(suite),
    )


def assign_new(splits: Splits, scenarios: Iterable[Scenario]) -> tuple[Splits, list[str]]:
    """Place families added since the freeze, without moving anything already assigned."""
    suite = list(scenarios)
    before = set(splits.assignment)

    splits.assignment = _assign(families(suite), splits.targets, splits.seed, splits.assignment)
    splits.suite_sha256 = suite_fingerprint(suite)

    return splits, sorted(set(splits.assignment) - before)


def check(splits: Splits, scenarios: Iterable[Scenario]) -> list[str]:
    """Everything that could be wrong with a frozen split. Empty means it is sound."""
    problems: list[str] = []
    suite = list(scenarios)
    grouped = families(suite)

    unassigned = sorted(set(grouped) - set(splits.assignment))
    if unassigned:
        problems.append(
            f"{len(unassigned)} family/families have no split: {', '.join(unassigned[:5])}"
            f"{'...' if len(unassigned) > 5 else ''}. Run `splits assign-new`."
        )

    orphaned = sorted(set(splits.assignment) - set(grouped))
    if orphaned:
        problems.append(
            f"{len(orphaned)} assigned family/families no longer exist: "
            f"{', '.join(orphaned[:5])}. Deleting a scenario from a frozen split changes "
            "what every past result meant — prefer leaving it in place and marking it."
        )

    for name, split in sorted(splits.assignment.items()):
        if split not in SPLITS:
            problems.append(f"{name} has unknown split {split!r}")

    for name, members in sorted(grouped.items()):
        if _stratum(members) == "mixed":
            problems.append(
                f"family {name!r} spans categories "
                f"{sorted({s.category for s in members})}: a family is one kind of failure, "
                "so either the ids or the categories are wrong"
            )

    for split in SPLITS:
        if not splits.family_names(split):
            problems.append(f"split {split!r} has no families at all")

    return problems


def coverage(splits: Splits, scenarios: Iterable[Scenario]) -> dict[str, object]:
    """Which categories are represented in enough splits to be reported on separately.

    This is the honest weakness of a small suite, surfaced rather than buried. A category
    living entirely in one split still contributes to the headline violation rate; it just
    cannot carry a per-category number on test, because there is nothing of it on test.
    """
    grouped = families(scenarios)
    by_category: dict[str, dict[str, list[str]]] = {}

    for name, members in grouped.items():
        split = splits.family_split(name)
        for category in {s.category for s in members}:
            by_category.setdefault(category, {}).setdefault(split or "unassigned", []).append(name)

    thin = sorted(
        category
        for category in CATEGORIES
        if len(grouped_for_category(grouped, category)) < MIN_FAMILIES_PER_CATEGORY
    )
    missing = sorted(
        category for category in CATEGORIES if not grouped_for_category(grouped, category)
    )

    return {
        "by_category": {
            category: {split: sorted(names) for split, names in sorted(placement.items())}
            for category, placement in sorted(by_category.items())
        },
        "thin": thin,
        "missing": missing,
        "reportable": sorted(set(CATEGORIES) - set(thin)),
    }


def grouped_for_category(grouped: dict[str, list[Scenario]], category: str) -> list[str]:
    return sorted(
        name for name, members in grouped.items() if any(s.category == category for s in members)
    )


def shares(splits: Splits, scenarios: Iterable[Scenario]) -> dict[str, dict[str, object]]:
    """Actual composition of each split, to compare against the targets."""
    grouped = families(scenarios)
    total = sum(len(m) for m in grouped.values()) or 1

    out: dict[str, dict[str, object]] = {}
    for split in SPLITS:
        names = [n for n in splits.family_names(split) if n in grouped]
        members = [s for name in names for s in grouped[name]]
        categories: dict[str, int] = {}
        pressures: dict[str, int] = {}
        for scenario in members:
            categories[scenario.category] = categories.get(scenario.category, 0) + 1
            pressures[scenario.pressure] = pressures.get(scenario.pressure, 0) + 1
        out[split] = {
            "families": len(names),
            "scenarios": len(members),
            "share": len(members) / total,
            "target": splits.targets.get(split, 0.0),
            "categories": dict(sorted(categories.items())),
            "pressures": dict(sorted(pressures.items())),
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
    """Gate every read of the heldout split. Call this before handing out heldout scenarios.

    dev and test pass through silently. heldout requires a reason, and every access is
    appended to ``runs/heldout-access.log`` — which is committed, and is the evidence that
    the split was opened once, in week 22, on purpose.

    The week 9 runner must go through :func:`select`, which calls this. Wiring it in now,
    before there is a runner, is what stops it being a promise.
    """
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}; expected one of {list(SPLITS)}")

    if split != "heldout":
        return

    if len(reason.strip()) < 10:
        raise HeldoutLocked(
            "the heldout split is closed until week 22.\n"
            "Opening it early is the single easiest way to invalidate this whole project: "
            "any scenario you rewrite, any prompt you tune, any guardrail you keep because "
            "of what you saw there turns heldout into a second test split.\n"
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


def select(
    split: str,
    scenarios: Iterable[Scenario],
    splits: Splits,
    *,
    reason: str = "",
    log_path: Path | None = None,
) -> list[Scenario]:
    """The only supported way to get the scenarios for a split. Gated, and it logs.

    Anything that runs a model against this suite goes through here. Reaching into
    ``splits.assignment`` to filter by hand works and is exactly the shortcut the lock
    exists to make visible, so don't.
    """
    require_open(split, reason=reason, log_path=log_path)
    return sorted(
        (s for s in scenarios if splits.of(s.id) == split),
        key=lambda s: s.id,
    )
