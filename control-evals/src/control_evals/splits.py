"""Splitting the scenario suite into dev, test and heldout — and keeping heldout shut.

Ported from covenant-evals, where the unit was a document. Here it is a **scenario family**,
and the reasoning transfers exactly.

**Split by family, never by scenario.** `limit-001` and `limit-002` are the same situation
with one variable changed: the same policy, the same counterparties, the same invoice, and
one of them split into two payments. Tune a system prompt against the first and you have
tuned against the second. Anything you would call "a variant of" something else belongs in
its family, and a family lives in exactly one split, always.

**Heldout has to be genuinely hard to open.** The point of a heldout split is that no
decision you made was informed by it. Discipline alone will not hold that for seventeen
weeks, so opening it requires an explicit reason and leaves a permanent record in
`runs/heldout-access.log`, which is committed. In week 22 that log is the evidence the split
was opened once — a claim worth more than whatever the score turns out to be.

**A scenario is code, so it can change under you.** In covenant-evals the corpus was a set of
downloaded files and the risk was one going missing. Here the risk is the opposite: the file
is right there and editing a task or an invoice amount is a one-line change that silently
makes this week's numbers incomparable with last week's. So the freeze also records a
content fingerprint per scenario, and `check` reports any that have moved since.

What the fingerprint does **not** cover: the oracles. `violated` and `completed` are
callables, and hashing a lambda's identity or its bytecode is either meaningless or
brittle. An oracle can therefore be rewritten without this noticing. That is a real hole and
it is why `tests/test_scenarios.py` runs every oracle against a compliant and a violating
trace — the fingerprint guards the scenario's data, the tests guard its judgement.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .scenario import Scenario

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPLITS = REPO_ROOT / "data" / "splits.json"
DEFAULT_ACCESS_LOG = REPO_ROOT / "runs" / "heldout-access.log"

SCHEMA_VERSION = 1

SPLITS = ("dev", "test", "heldout")

#: Shares of the suite, counted in scenarios. dev is the split you read constantly and will
#: overfit whether or not you mean to, so it is kept small; heldout is large enough that a
#: rate measured on it has an interval worth quoting; test is where the work happens.
DEFAULT_TARGETS = {"dev": 0.20, "test": 0.50, "heldout": 0.30}

#: Families are shuffled inside their stratum before assignment. Recorded in splits.json so
#: the assignment can be reproduced from scratch rather than trusted.
DEFAULT_SEED = 20260904


class HeldoutLocked(RuntimeError):
    """Raised when something tries to read the heldout split without saying why."""


class SplitsFrozen(RuntimeError):
    """Raised when something tries to re-cut a frozen assignment."""


# ---------------------------------------------------------------------------
# Fingerprints
# ---------------------------------------------------------------------------


def scenario_fingerprint(scenario: Scenario) -> str:
    """Hash of everything about a scenario except its oracles.

    Covers what the agent is given — the policy, the task, the tools, and the starting state
    of the world, invoice amounts and injected notes included — because those are what make
    a result mean what it means. See the module docstring for what this misses.
    """
    payload = {
        "id": scenario.id,
        "family": scenario.family,
        "category": scenario.category,
        "pressure": scenario.pressure,
        "tools": list(scenario.tools),
        "task": scenario.task,
        "tests": scenario.tests,
        "policy": {
            "max_single_payment": scenario.policy.max_single_payment,
            "max_daily_total": scenario.policy.max_daily_total,
            "approval_required_above": scenario.policy.approval_required_above,
            "counterparty_allowlist": list(scenario.policy.counterparty_allowlist),
            "may_add_counterparty": scenario.policy.may_add_counterparty,
            "notes": scenario.policy.notes,
        },
        "world": asdict(scenario.world()),
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def suite_fingerprint(suite: tuple[Scenario, ...]) -> str:
    """Hash of which scenarios exist and which family each is in.

    Deliberately separate from the per-scenario fingerprints: this one changes when the
    shape of the suite changes, which is expected during weeks 6-8, while a per-scenario
    fingerprint changing means an existing scenario was edited, which is not.
    """
    shape = json.dumps(sorted((s.id, s.family) for s in suite))
    return hashlib.sha256(shape.encode()).hexdigest()


# ---------------------------------------------------------------------------
# The assignment
# ---------------------------------------------------------------------------


def families(suite: tuple[Scenario, ...]) -> dict[str, tuple[Scenario, ...]]:
    """The suite grouped by family. The unit of assignment, everywhere in this module."""
    grouped: dict[str, list[Scenario]] = {}
    for scenario in suite:
        grouped.setdefault(scenario.family, []).append(scenario)
    return {name: tuple(members) for name, members in sorted(grouped.items())}


def _stratum(members: tuple[Scenario, ...]) -> str:
    """Families are balanced across splits by failure category.

    If dev were all hard-limit scenarios and heldout all injection, a drop between the two
    would be indistinguishable from heldout being harder — and *which category does this
    model fail on* is one of the results this suite exists to produce.

    A family with more than one category is placed by its most common one, ties broken
    alphabetically, because a family goes to one split whole.
    """
    counts: dict[str, int] = {}
    for scenario in members:
        counts[scenario.category] = counts.get(scenario.category, 0) + 1
    return max(sorted(counts), key=lambda category: counts[category])


def _assign(
    grouped: dict[str, tuple[Scenario, ...]],
    targets: dict[str, float],
    seed: int,
    existing: dict[str, str] | None = None,
) -> dict[str, str]:
    """Greedily assign families to splits, balancing scenario counts within each stratum.

    Deterministic given the same families and seed. Existing assignments are preserved
    exactly — this is how families added after the freeze are placed without disturbing
    anything already decided.
    """
    assignment = dict(existing or {})
    weight = {split: 0.0 for split in SPLITS}
    total = 0.0

    for name, members in grouped.items():
        if name in assignment and assignment[name] in SPLITS:
            weight[assignment[name]] += len(members)
            total += len(members)

    unassigned = {name: m for name, m in grouped.items() if name not in assignment}

    by_stratum: dict[str, list[str]] = {}
    for name, members in unassigned.items():
        by_stratum.setdefault(_stratum(members), []).append(name)

    for stratum in sorted(by_stratum):
        names = sorted(by_stratum[stratum])
        random.Random(f"{seed}:{stratum}").shuffle(names)

        for name in names:
            size = float(len(unassigned[name]))
            projected = total + size
            # Give it to whichever split is furthest below its target share.
            deficit = {s: targets.get(s, 0.0) - (weight[s] / projected) for s in SPLITS}
            chosen = max(SPLITS, key=lambda s: (deficit[s], -weight[s], s))
            assignment[name] = chosen
            weight[chosen] += size
            total = projected

    return assignment


@dataclass
class Splits:
    assignment: dict[str, str] = field(default_factory=dict)  # family -> split
    fingerprints: dict[str, str] = field(default_factory=dict)  # scenario id -> content hash
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
            fingerprints=payload.get("fingerprints", {}),
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
                "split you can silently redraw is not a split. Adding a family is allowed; "
                "moving one between splits is not. The fingerprints are of scenario "
                "content, not of the oracles — see splits.py."
            ),
            "frozen_at": self.frozen_at,
            "seed": self.seed,
            "targets": self.targets,
            "suite_sha256": self.suite_sha256,
            "assignment_sha256": self.assignment_sha256,
            "assignment": dict(sorted(self.assignment.items())),
            "fingerprints": dict(sorted(self.fingerprints.items())),
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

    def of(self, family: str) -> str:
        return self.assignment.get(family, "")

    def assigned_to(self, split: str) -> list[str]:
        """Family names in one split."""
        return sorted(name for name, value in self.assignment.items() if value == split)


def freeze(
    suite: tuple[Scenario, ...],
    *,
    seed: int = DEFAULT_SEED,
    targets: dict[str, float] | None = None,
) -> Splits:
    """Produce the initial assignment. Does not write — the caller decides that."""
    if not suite:
        raise ValueError("no scenarios — there is nothing to split")

    grouped = families(suite)
    resolved = targets or dict(DEFAULT_TARGETS)
    return Splits(
        assignment=_assign(grouped, resolved, seed),
        fingerprints={s.id: scenario_fingerprint(s) for s in suite},
        seed=seed,
        targets=resolved,
        frozen_at=datetime.now(UTC).isoformat(timespec="seconds"),
        suite_sha256=suite_fingerprint(suite),
    )


def assign_new(splits: Splits, suite: tuple[Scenario, ...]) -> tuple[Splits, list[str]]:
    """Place families added since the freeze, without moving anything already assigned.

    Fingerprints are recorded for the new scenarios only. A scenario that already has a
    fingerprint keeps it, so editing an existing scenario is still reported by `check`
    rather than being papered over by the next `assign-new`.
    """
    grouped = families(suite)
    before = set(splits.assignment)

    splits.assignment = _assign(grouped, splits.targets, splits.seed, splits.assignment)
    splits.suite_sha256 = suite_fingerprint(suite)

    for scenario in suite:
        splits.fingerprints.setdefault(scenario.id, scenario_fingerprint(scenario))

    return splits, sorted(set(splits.assignment) - before)


def refresh_fingerprints(splits: Splits, suite: tuple[Scenario, ...]) -> list[str]:
    """Accept the current content of every scenario as the new baseline.

    This is a deliberate act with a cost: any result measured before it was measured on
    different scenarios, and the two are no longer comparable. Prefer giving the changed
    scenario a new id — ids are never reused in this project, so a new id is a new scenario
    and the old results keep meaning what they meant.

    Returns the ids whose content had in fact moved.
    """
    moved = []
    for scenario in suite:
        current = scenario_fingerprint(scenario)
        if splits.fingerprints.get(scenario.id) not in (None, current):
            moved.append(scenario.id)
        splits.fingerprints[scenario.id] = current

    for gone in set(splits.fingerprints) - {s.id for s in suite}:
        del splits.fingerprints[gone]

    splits.suite_sha256 = suite_fingerprint(suite)
    return sorted(moved)


def check(splits: Splits, suite: tuple[Scenario, ...]) -> list[str]:
    """Everything that could be wrong with a frozen split. Empty means it is sound."""
    problems: list[str] = []
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
            f"{len(orphaned)} assigned family/families are no longer in the suite: "
            f"{', '.join(orphaned[:5])}. Deleting a scenario from a frozen split changes "
            "what every past result meant."
        )

    for name, split in sorted(splits.assignment.items()):
        if split not in SPLITS:
            problems.append(f"family {name} has unknown split {split!r}")

    for split in SPLITS:
        if not splits.assigned_to(split):
            problems.append(f"split {split!r} has no scenarios at all")

    known = {s.id for s in suite}
    for scenario in suite:
        recorded = splits.fingerprints.get(scenario.id)
        if recorded is None:
            problems.append(f"{scenario.id} has no recorded fingerprint. Run `splits assign-new`.")
        elif recorded != scenario_fingerprint(scenario):
            problems.append(
                f"{scenario.id} has changed since the freeze — its policy, task, tools or "
                "starting world is not what it was. Results measured before and after this "
                "are not comparable. Give the new version a new id, or accept the change "
                "with `splits refingerprint`."
            )

    for gone in sorted(set(splits.fingerprints) - known):
        problems.append(
            f"{gone} was fingerprinted at the freeze and is no longer in the suite. "
            "Scenario ids are never reused; a removed scenario should be recorded, not "
            "quietly dropped."
        )

    return problems


def shares(splits: Splits, suite: tuple[Scenario, ...]) -> dict[str, dict[str, object]]:
    """Actual composition of each split, to compare against the targets."""
    grouped = families(suite)
    total = sum(len(m) for m in grouped.values()) or 1
    out: dict[str, dict[str, object]] = {}

    for split in SPLITS:
        names = splits.assigned_to(split)
        members = [s for name in names for s in grouped.get(name, ())]
        categories: dict[str, int] = {}
        for scenario in members:
            categories[scenario.category] = categories.get(scenario.category, 0) + 1
        out[split] = {
            "families": len(names),
            "scenarios": len(members),
            "share": len(members) / total,
            "target": splits.targets.get(split, 0.0),
            "categories": categories,
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
    """Gate every read of the heldout split. Call this before returning heldout scenarios.

    dev and test pass through silently. heldout requires a reason, and every access is
    appended to runs/heldout-access.log — which is committed, and is the evidence that the
    split was opened once, in week 22, on purpose.

    The week 9 runner must go through `select`, which calls this. It is wired in now rather
    than promised for later, because a lock nobody has yet had to pass through is not a lock.
    """
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}; expected one of {list(SPLITS)}")

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


def select(
    suite: tuple[Scenario, ...],
    splits: Splits,
    split: str,
    *,
    reason: str = "",
    log_path: Path | None = None,
) -> tuple[Scenario, ...]:
    """The scenarios in one split. **The only supported way to get them.**

    Going through here is what makes the lock real: reading heldout without a reason raises,
    and reading it with one leaves a line in the access log. Iterating `SUITE` directly
    bypasses that, which is why the runner will not.
    """
    require_open(split, reason=reason, log_path=log_path)
    chosen = {name for name in splits.assigned_to(split)}
    return tuple(s for s in suite if s.family in chosen)
