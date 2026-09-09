"""Where results go, and what a stored run has to contain.

One rule shapes this file: **a stored run must be enough to recompute every metric without
re-running anything.** Runs cost money and a model's behaviour drifts, so a run you cannot
re-score is a run you have to buy again. That means storing the trace and the outcomes, not
just the rates, and storing the model, effort, split, prices and suite fingerprint alongside
them so a number can always be traced back to the configuration that produced it.

Results are not committed. `runs/*/` is gitignored on purpose — what belongs in the
repository is the code that produces a result and the split it was produced against, not the
result itself, which anyone with a key can reproduce.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import spec_for
from .scenario import SCHEMA_VERSION
from .trace import Trace

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_DIR = REPO_ROOT / "runs"


#: Characters that cannot appear in a Windows path. A run id becomes a directory name, so
#: anything here has to go — `simulated:careful` produced a colon and would have failed to
#: create the directory on Windows while working fine on Linux and macOS.
_UNSAFE = ':<>"/\\|?*'


def safe_name(text: str) -> str:
    for character in _UNSAFE:
        text = text.replace(character, "-")
    return text.strip(". ")


def new_run_id(model: str, effort: str, split: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    tail = f"{model}-{effort}" if effort else model
    return safe_name(f"{stamp}-{split}-{tail}")


@dataclass
class RunSet:
    """One sweep: a split, a model, an effort, and every run it produced."""

    run_id: str
    split: str
    model: str
    effort: str
    suite_sha256: str
    splits_sha256: str
    started_at: str = ""
    records: list[dict[str, Any]] = field(default_factory=list)

    @property
    def simulated(self) -> bool:
        return self.model.startswith("simulated:")

    @property
    def meta(self) -> dict[str, Any]:
        # A simulated run has no model and therefore no prices. Recording a price for it
        # would be the one way its numbers could later be mistaken for a real result.
        spec = None if self.simulated else spec_for(self.model)
        return {
            "run_id": self.run_id,
            "split": self.split,
            "model": self.model,
            "effort": self.effort,
            "started_at": self.started_at,
            "scenario_schema_version": SCHEMA_VERSION,
            "suite_sha256": self.suite_sha256,
            "splits_sha256": self.splits_sha256,
            "simulated": self.simulated,
            # Recorded so a cost can be recomputed later even if published rates change.
            "pricing": None
            if spec is None
            else {
                "input_per_mtok": spec.input_per_mtok,
                "output_per_mtok": spec.output_per_mtok,
            },
            "runs": len(self.records),
        }

    def directory(self, root: Path | None = None) -> Path:
        return (root or DEFAULT_RUNS_DIR) / self.run_id

    def save(self, root: Path | None = None) -> Path:
        target = self.directory(root)
        target.mkdir(parents=True, exist_ok=True)
        (target / "meta.json").write_text(json.dumps(self.meta, indent=2) + "\n", encoding="utf-8")
        with (target / "runs.jsonl").open("w", encoding="utf-8") as handle:
            for record in self.records:
                handle.write(json.dumps(record, default=str) + "\n")
        return target

    @classmethod
    def load(cls, run_id: str, root: Path | None = None) -> RunSet:
        target = (root or DEFAULT_RUNS_DIR) / run_id
        meta_path = target / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"no run {run_id!r} under {target.parent}")

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        records = [
            json.loads(line)
            for line in (target / "runs.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return cls(
            run_id=meta["run_id"],
            split=meta["split"],
            model=meta["model"],
            effort=meta.get("effort", ""),
            suite_sha256=meta.get("suite_sha256", ""),
            splits_sha256=meta.get("splits_sha256", ""),
            started_at=meta.get("started_at", ""),
            records=records,
        )


def trace_from_record(record: dict[str, Any], scenario: Any = None) -> Trace:
    """Rebuild the agent's trace from a stored record.

    The file's rule is that a stored run must be enough to recompute every metric without
    re-running anything. `report <run-id>` was recomputing the trace-derived signals one at
    a time and inline — escalation from the calls, the silent claim from the final message —
    and `units_note` was simply forgotten when it was added. The consequence was the one
    that matters: re-reading a stored run printed the violation rate WITHOUT the banner
    saying it was unmeasured. The caveat evaporated and the number survived it.

    Rebuilding the trace once, here, means the next signal derived from it is recomputed by
    asking the same question of the same object rather than by remembering to.

    Only the error is stored from each result, which is all `Call.ok` reads. `offered_tools`
    comes from the scenario when one is given, because decision 19 needs to know what the
    agent was offered and declined to use, and that is not recoverable from the calls.
    """
    trace = Trace(offered_tools=tuple(scenario.tools) if scenario is not None else ())
    for call in record.get("calls", []):
        error = call.get("error")
        trace.record(call["tool"], call.get("arguments", {}), {"error": error} if error else {})
    trace.final_message = record.get("final_message", "")
    return trace


def list_runs(root: Path | None = None) -> list[str]:
    target = root or DEFAULT_RUNS_DIR
    if not target.exists():
        return []
    return sorted((p.name for p in target.iterdir() if (p / "meta.json").exists()), reverse=True)
