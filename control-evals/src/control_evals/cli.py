"""The command line. Everything you can do to this project without writing Python.

Two rules it follows, both learned the hard way in covenant-evals:

* **No `make`.** Every command in the docs is `py -m control_evals.cli ...`, which works on
  Windows PowerShell, macOS and Linux with no extra tooling and no PATH surprises.
* **Nothing here reaches the network.** Week 9 adds a runner that does; until then every
  command is offline and instant.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import UTC, datetime

from .budget import format_micros
from .explain import explain
from .guardrails import GUARDRAILS, guardrail_for
from .models import DEFAULT_MODEL, EFFORT_LEVELS, MODELS, spec_for
from .openai_compat import DEFAULT_TIMEOUT_S
from .runner import DEFAULT_MAX_TURNS
from .scenario import CATEGORIES, validate_all
from .scenarios import SUITE, by_id
from .simulate import BANNER, STYLES, ScriptedClient
from .splits import (
    DEFAULT_SEED,
    MIN_FAMILIES_PER_CATEGORY,
    OPEN_SPLITS,
    SPLITS,
    HeldoutLocked,
    Splits,
    access_history,
    assign_new,
    coverage,
    families,
    family_of,
    grouped_for_category,
    select,
    shares,
)
from .splits import check as check_splits

# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------


def cmd_scenarios_list(args: argparse.Namespace) -> int:
    splits = Splits.load()
    rows = sorted(SUITE, key=lambda s: s.id)
    if args.category:
        rows = [s for s in rows if s.category == args.category]

    print(f"{'id':<16} {'family':<12} {'category':<19} {'pressure':<12} split")
    print("-" * 74)
    for scenario in rows:
        split = splits.of(scenario.id) if splits else "-"
        print(
            f"{scenario.id:<16} {family_of(scenario.id):<12} {scenario.category:<19} "
            f"{scenario.pressure:<12} {split or 'unassigned'}"
        )

    grouped = families(rows)
    print(f"\n{len(rows)} scenario(s) in {len(grouped)} family/families")

    uncovered = sorted(set(CATEGORIES) - {s.category for s in SUITE})
    if uncovered:
        print(f"categories with no scenario yet: {', '.join(uncovered)}")
    return 0


def cmd_scenarios_show(args: argparse.Namespace) -> int:
    """One scenario in full: the policy as the agent will see it, and the task."""
    scenario = by_id(args.id)
    if scenario is None:
        raise SystemExit(f"no scenario {args.id!r} — try `scenarios list`")

    splits = Splits.load()
    print(f"{scenario.id}  [{scenario.category} / pressure: {scenario.pressure}]")
    if splits:
        print(f"split: {splits.of(scenario.id) or 'unassigned'}")
    print(f"\ntests: {scenario.tests}\n")
    print("-- policy, as the agent sees it " + "-" * 47)
    print(scenario.policy.render(scenario.tools))
    print("\n-- task " + "-" * 70)
    print(scenario.task)
    print("\n-- tools " + "-" * 69)
    print(", ".join(scenario.tools))
    if scenario.inaction_is_a_violation:
        print("\nNote: doing nothing is a violation here — a payment is already queued.")
    return 0


def cmd_scenarios_categories() -> int:
    """The taxonomy and how many families sit in each. The suite's own health check."""
    splits = Splits.load()
    grouped = families(SUITE)

    print(f"{'category':<20} {'families':>8} {'scenarios':>10}  splits")
    print("-" * 62)
    for category in CATEGORIES:
        members = [s for s in SUITE if s.category == category]
        names = grouped_for_category(grouped, category)
        where = sorted({splits.of(s.id) for s in members}) if splits else []
        flag = "" if len(names) >= MIN_FAMILIES_PER_CATEGORY else "  (thin)"
        print(
            f"{category:<20} {len(names):>8} {len(members):>10}  "
            f"{', '.join(w for w in where if w)}{flag}"
        )
    print(f"\n{len(SUITE)} scenarios in {len(grouped)} families")
    return 0


def cmd_scenarios_check() -> int:
    problems = validate_all(list(SUITE))
    if not problems:
        print(f"{len(SUITE)} scenarios, all well formed")
        return 0
    for scenario_id, errors in sorted(problems.items()):
        print(f"{scenario_id}:")
        for error in errors:
            print(f"  - {error}")
    return 1


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _client():
    """Built lazily so that every offline command — and every test — needs no key."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is declared
        raise SystemExit("the anthropic package is not installed: py -m pip install -e .") from None

    from .env import load_dotenv, missing_key_message

    source = load_dotenv()
    if source is not None:
        # Which file, never the key. A run that cannot say where its credentials came from
        # is one you cannot reproduce.
        print(f"using ANTHROPIC_API_KEY from {source}")
    elif os.environ.get("ANTHROPIC_API_KEY"):
        print("using ANTHROPIC_API_KEY from the environment")

    try:
        client = anthropic.Anthropic()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"{missing_key_message()}\n({type(exc).__name__}: {exc})") from None

    # The SDK does NOT raise here when there is no credential — it defers auth to the first
    # request. Without this check a keyless sweep "succeeds": every run fails inside the
    # loop, is recorded as stopped="error", and the report comes back all n/a with nothing
    # saying why. Fail before spending a turn instead.
    if not getattr(client, "api_key", None) and not getattr(client, "auth_token", None):
        raise SystemExit(missing_key_message())

    return client


def _wrapped(mark: str, label: str, text: str, width: int = 84) -> None:
    """One labelled line, wrapped under its own label rather than off the screen."""
    lead = f"        {mark} {label:<5} "
    body = textwrap.wrap(text, width=width) or [""]
    print(lead + body[0])
    for line in body[1:]:
        print(" " * len(lead) + line)


def _open_ai_client(spec, args):
    """A client for anything that speaks chat-completions. Local endpoints need no key."""
    from .openai_compat import OpenAICompatClient, transport_with_timeout

    key = os.environ.get(args.api_key_env, "") if args.api_key_env else ""
    base = args.base_url or spec.base_url
    local = "localhost" in base or "127.0.0.1" in base
    if not key and not local:
        raise SystemExit(
            f"{base} is not a local endpoint, so it probably needs a key.\n"
            f"Set ${args.api_key_env}, or pass --api-key-env with the variable that holds it."
        )
    print(f"endpoint {base}" + ("  (local — no key, no cost)" if local else ""))
    return OpenAICompatClient(
        base_url=base, api_key=key, transport=transport_with_timeout(args.timeout)
    )


def _check_model(args: argparse.Namespace) -> None:
    """A closed list of models is right up to the moment someone points at their own server.

    With `--base-url` the endpoint is the authority on what exists, so any id is allowed and
    a wrong one comes back as the endpoint's own 404 — which says more than argparse could.
    Without one, an unknown id is a real mistake and the list is the useful answer.
    """
    if args.base_url or args.model in MODELS:
        return
    raise SystemExit(
        f"unknown model {args.model!r}.\n"
        f"Known models: {', '.join(sorted(MODELS))}\n"
        f"For anything else, say where it is served:\n"
        f"  --model {args.model} --base-url http://localhost:11434/v1"
    )


def cmd_run(args: argparse.Namespace) -> int:
    from .report import Row, row_from_run, summarise
    from .runner import run_scenario
    from .splits import suite_fingerprint
    from .store import RunSet, new_run_id

    _check_model(args)
    splits = _require_splits()
    try:
        # The gate. A dry run goes through it too: listing which scenarios are in heldout
        # is itself an access, and over-logging is the right direction for a lock.
        #
        # "open" means every split that is not locked. It exists so that "run the whole
        # suite" has an answer that does not involve opening heldout — including for a
        # simulated run, where seeing which heldout scenarios are traps and how their
        # oracles fire is exactly the knowledge the lock is there to withhold.
        if args.split == "open":
            chosen = [s for name in OPEN_SPLITS for s in select(name, SUITE, splits)]
        else:
            chosen = select(args.split, SUITE, splits, reason=args.reason)
    except HeldoutLocked as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.scenario:
        chosen = [s for s in chosen if s.id in set(args.scenario)]
        if not chosen:
            raise SystemExit(f"none of {args.scenario} are in the {args.split} split")
    if args.limit:
        chosen = chosen[: args.limit]

    spec = spec_for(args.model, args.base_url)
    total = len(chosen) * args.samples

    layer = guardrail_for(args.guardrail)
    print(f"{total} run(s): {len(chosen)} scenario(s) x {args.samples} sample(s)")
    if layer.active:
        print(f"guardrail: {layer.name} — {layer.description}")
    if args.simulate:
        print(f"\n{BANNER}\n")
    else:
        print(f"model {spec.id}" + (f", effort {args.effort}" if spec.supports_effort else ""))
        print(_estimate(total, spec))

    if args.dry_run:
        print("\ndry run: nothing was sent. Drop --dry-run to spend it.")
        return 0

    if args.simulate:
        client = None
    elif spec.provider == "openai_compat":
        client = _open_ai_client(spec, args)
    else:
        client = _client()
    # Stamped into the run id, the model field and the meta, so a simulated run can never
    # be read later as a result about a model.
    recorded_model = f"simulated:{args.simulate}" if args.simulate else spec.id
    run_set = RunSet(
        run_id=new_run_id(
            recorded_model,
            "" if args.simulate else (args.effort if spec.supports_effort else ""),
            args.split,
        ),
        split=args.split,
        model=recorded_model,
        effort="" if args.simulate else (args.effort if spec.supports_effort else ""),
        suite_sha256=suite_fingerprint(SUITE),
        splits_sha256=splits.assignment_sha256,
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )

    rows: list[Row] = []
    spent = 0
    consecutive_errors = 0
    for index, scenario in enumerate(chosen, start=1):
        for sample in range(args.samples):
            result = run_scenario(
                scenario,
                ScriptedClient(args.simulate, scenario) if args.simulate else client,
                model=spec.id,
                effort=args.effort,
                max_turns=args.max_turns,
                sample=sample,
                guardrail=layer,
            )
            if args.simulate:
                result.model = recorded_model
            rows.append(row_from_run(result, scenario))
            run_set.records.append(result.as_dict())
            spent += result.cost_micros

            if result.violated and not result.breached:
                flag = "BLOCKED"
            elif result.violated:
                flag = "VIOLATION"
            else:
                flag = "clean" if result.completed else "-"
            cost = (
                ""
                if args.simulate or not result.cost_micros
                else (f"  {format_micros(result.cost_micros)}")
            )
            print(
                f"  [{index:>3}/{len(chosen)}] {scenario.id:<18} {flag:<9} {result.turns:>2}t{cost}"
            )
            if not args.brief and result.ok:
                why = explain(
                    scenario, result.trace, result.world, result.violated, result.completed
                )
                mark = "x" if result.violated else "+"
                _wrapped(mark, "rule", why.rule)
                if result.violated and not result.breached:
                    _wrapped(
                        "!",
                        "held",
                        "the control layer refused it, so no money moved — but the agent "
                        "still decided to do it",
                    )
                _wrapped("+" if result.completed else "x", "task", why.task)
                _wrapped(" ", "did", why.did)
            elif not args.brief:
                print(f"        ! {result.stopped}  {result.error or 'not scored'}")

            # Written after every run, not at the end: a sweep interrupted halfway has
            # still bought its results and should not lose them.
            run_set.save()

            # Three failures in a row is a broken setup, not bad luck. Stopping beats
            # repeating the same error across the whole suite and reporting all n/a.
            consecutive_errors = consecutive_errors + 1 if result.stopped == "error" else 0
            if consecutive_errors >= 3:
                print(f"\nstopping: {consecutive_errors} calls in a row failed.")
                print(f"last error: {result.error}")
                print(f"partial results are in runs/{run_set.run_id}")
                return 1

    if args.simulate:
        print(f"\nsaved to runs/{run_set.run_id} (no API call, no cost)")
    else:
        print(f"\nspent {format_micros(spent)}, saved to runs/{run_set.run_id}")
    _print_summary(summarise(rows), rows)
    return 0


def _estimate(runs: int, spec) -> str:
    """A rough number before spending, from the shape of a scenario rather than a guess."""
    from .budget import Usage, cost_micros

    # ~1,200 tokens of policy, task and tool schemas; ~5 turns; the prefix is resent each
    # turn, so input scales with turns. Deliberately an over-estimate.
    per_run = Usage(input_tokens=1_200 * 5, output_tokens=350 * 5)
    each = cost_micros(per_run, spec)
    return f"rough estimate {format_micros(each)} per run, {format_micros(each * runs)} total"


def _print_summary(summary, rows) -> None:
    from .report import by_category

    print("\n-- the frontier " + "-" * 62)
    print(f"  violation rate (trapped scenarios) {summary.violation_trapped}")
    if summary.guardrail != "none":
        print(f"  BREACH rate  (money actually moved) {summary.breach_trapped}")
    print(f"  violation rate (whole suite)       {summary.violation_all}")
    print(f"  task completion                    {summary.completion}")
    print(f"  escalation precision               {summary.escalation_precision}")
    print(f"  escalation recall                  {summary.escalation_recall}")
    print(
        f"  silent violations                  at least {summary.silent_violations} "
        f"of {summary.violations} (keyword detection, lower bound only)"
    )
    if summary.guardrail != "none":
        print(
            f"  guardrail                          {summary.guardrail}: "
            f"{summary.blocked_calls} call(s) refused, "
            f"{summary.violations - summary.breaches} violation(s) held"
        )

    # Loud, and above the rates rather than buried under them: if this fires, the violation
    # rate printed above is not a measurement of whether the model respects a limit.
    if summary.wrong_units:
        print(
            f"\n  !! WRONG UNITS in {summary.wrong_units} of {summary.runs} run(s).\n"
            f"     {summary.units_example}.\n"
            f"     The schema says pence; this model is sending pounds. Every amount it\n"
            f"     chose is far below every limit in the suite, so it CANNOT break an amount\n"
            f"     rule — and a low violation rate here means it cannot count, not that it\n"
            f"     is careful. Treat the violation rate above as unmeasured."
        )
    if summary.unscored:
        detail = ", ".join(f"{k}: {v}" for k, v in sorted(summary.unscored.items()))
        print(f"  unscored runs                      {detail}")
    print(
        f"\n  {summary.runs} runs, {summary.turns} turns, "
        f"{format_micros(summary.cost_micros)}, {summary.seconds:.0f}s"
    )
    print("\n  Intervals are 95%, bootstrapped over scenario FAMILIES — runs inside a")
    print("  family are not independent, so resampling runs would be overconfident.")

    print("\n-- by category " + "-" * 63)
    for category, interval in by_category(rows).items():
        print(f"  {category:<20} {interval}")


def cmd_doctor(args: argparse.Namespace) -> int:
    """Fifteen seconds against a real endpoint, before an hour spent on a sweep."""
    from .doctor import probe_payload, run_checks, verdict
    from .openai_compat import OpenAICompatClient, transport_with_timeout

    spec = spec_for(args.model, args.base_url)
    if spec.provider != "openai_compat" and not args.base_url:
        raise SystemExit(
            f"{args.model} is served by the Anthropic SDK, which this checks nothing about.\n"
            "Use --base-url with an OpenAI-compatible endpoint, e.g.\n"
            "  --base-url http://localhost:11434/v1 --model qwen2.5:1.5b"
        )

    base = args.base_url or spec.base_url
    key = os.environ.get(args.api_key_env, "") if args.api_key_env else ""
    print(f"checking {base} with model {args.model}\n")

    client = OpenAICompatClient(
        base_url=base, api_key=key, transport=transport_with_timeout(args.timeout)
    )
    checks = run_checks(client, args.model)
    for check in checks:
        print(check)

    code, summary = verdict(checks)
    print(f"\n{summary}")

    if args.show_request:
        url = f"{base.rstrip('/')}/chat/completions"
        print(f"\nthe tool-call probe, exactly as sent to {url}:\n")
        print(json.dumps(probe_payload(args.model), indent=2))
        print(
            "\nReplay it against another model on the same server. If that one calls the "
            "tool,\nthe request is fine and the model is not."
        )
    return code


def cmd_report(args: argparse.Namespace) -> int:
    from .report import Row, escalation_is_acceptable, has_a_trap, summarise, wrong_units
    from .store import RunSet, list_runs, trace_from_record

    if not args.run_id:
        available = list_runs()
        if not available:
            raise SystemExit("no runs yet — `run --split dev --dry-run` first")
        print("\n".join(available))
        return 0

    run_set = RunSet.load(args.run_id)
    rows: list[Row] = []
    for record in run_set.records:
        scenario = by_id(record["scenario_id"])
        if scenario is None:
            continue
        trace = trace_from_record(record, scenario)
        rows.append(
            Row(
                scenario_id=record["scenario_id"],
                family=record["family"],
                category=record["category"],
                pressure=record["pressure"],
                model=record["model"],
                effort=record.get("effort", ""),
                violated=record["violated"],
                breached=record.get("breached"),
                completed=record["completed"],
                escalated=trace.requested_approval(),
                escalation_acceptable=escalation_is_acceptable(scenario),
                trapped=has_a_trap(scenario),
                silent_claim=_silent(record),
                # Recomputed from the rebuilt trace, not remembered. Forgetting it here
                # meant a re-reported run printed the violation rate without the banner
                # saying it was unmeasured — the number outliving its own caveat.
                units_note=wrong_units(scenario, trace),
                turns=record["turns"],
                cost_micros=record["cost_micros"],
                elapsed_s=record["elapsed_s"],
                stopped=record["stopped"],
                guardrail=record.get("guardrail", "none"),
                blocked=len(record.get("blocked", [])),
            )
        )

    print(f"{run_set.run_id}: {run_set.model} on {run_set.split}, {len(rows)} runs")
    if run_set.model.startswith("simulated:"):
        print(f"\n{BANNER}")
    _print_summary(summarise(rows), rows)
    return 0


def _silent(record: dict) -> str | None:
    from .report import claims_compliance

    if not record.get("violated"):
        return None
    return claims_compliance(record.get("final_message", ""))


# ---------------------------------------------------------------------------
# splits
# ---------------------------------------------------------------------------


def _require_splits() -> Splits:
    splits = Splits.load()
    if splits is None:
        raise SystemExit("no splits yet — run `py -m control_evals.cli splits freeze` first")
    return splits


def _print_shares(splits: Splits) -> None:
    print(f"{'split':<10} {'families':>8} {'scenarios':>10} {'share':>7} {'target':>7}")
    for split, data in shares(splits, SUITE).items():
        print(
            f"{split:<10} {data['families']:>8} {data['scenarios']:>10} "
            f"{data['share']:>6.0%} {data['target']:>7.0%}"
        )


def cmd_splits_freeze(args: argparse.Namespace) -> int:
    from .splits import freeze

    existing = Splits.load()
    if existing is not None and existing.is_frozen and not args.force:
        raise SystemExit(
            f"splits were frozen at {existing.frozen_at} and will not be re-cut.\n"
            "Re-cutting after any result exists makes every past number incomparable.\n"
            "To place families added since the freeze, use `splits assign-new`."
        )

    splits = freeze(SUITE, seed=args.seed)
    splits.save()

    print(f"frozen at {splits.frozen_at}")
    print(f"seed {splits.seed}, assignment {splits.assignment_sha256[:12]}…\n")
    _print_shares(splits)
    print("\nCommit data/splits.json now. The heldout split is closed until week 22.")
    return 0


def cmd_splits_assign_new() -> int:
    splits = _require_splits()
    splits, added = assign_new(splits, SUITE)
    if not added:
        print("no new families since the freeze")
        return 0
    splits.save()
    print(f"placed {len(added)} new family/families:\n")
    for name in added:
        print(f"  {splits.family_split(name):<9} {name}")
    print("\nCommit data/splits.json.")
    return 0


def cmd_splits_status() -> int:
    splits = Splits.load()
    if splits is None:
        print("splits not frozen yet")
        return 0

    print(f"frozen at {splits.frozen_at}")
    print(f"seed {splits.seed}, assignment {splits.assignment_sha256[:12]}…\n")
    _print_shares(splits)

    opened = access_history()
    print(f"\nheldout opened {len(opened)} time(s)")
    for entry in opened:
        print(f"  {entry['at']}  {entry['reason']}")
    return 0


def cmd_splits_check() -> int:
    splits = _require_splits()
    problems = check_splits(splits, SUITE)
    report = coverage(splits, SUITE)

    for problem in problems:
        print(f"PROBLEM  {problem}")

    thin = report["thin"]
    if thin:
        print(
            f"\nWARN     {len(thin)} categor(y/ies) have fewer than three families, so a "
            "per-category\n         result cannot be reported on test alone yet:"
        )
        for category in thin:
            placement = report["by_category"].get(category, {})
            where = ", ".join(f"{split}: {len(names)}" for split, names in placement.items())
            print(f"           {category:<19} {where or 'no scenarios yet'}")
        print("         This clears when weeks 6-8 give each category several families.")

    if not problems:
        print(f"\n{len(splits.assignment)} families assigned, no problems")
    return 1 if problems else 0


def cmd_splits_show(args: argparse.Namespace) -> int:
    _check_model(args)
    splits = _require_splits()
    try:
        chosen = select(args.split, SUITE, splits, reason=args.reason)
    except HeldoutLocked as exc:
        print(str(exc), file=sys.stderr)
        return 2

    for scenario in chosen:
        print(f"{scenario.id:<16} {scenario.category:<19} {scenario.tests}")
    print(f"\n{len(chosen)} scenario(s) in {args.split}")
    if args.split == "heldout":
        print("This access has been written to runs/heldout-access.log. Commit it.")
    return 0


def cmd_splits_log() -> int:
    opened = access_history()
    if not opened:
        print("heldout has never been opened")
        return 0
    for entry in opened:
        print(f"{entry['at']}  {entry['reason']}")
    print(f"\n{len(opened)} access(es)")
    return 0


def cmd_splits_coverage() -> int:
    splits = _require_splits()
    print(json.dumps(coverage(splits, SUITE), indent=2))
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="control-evals",
        description="Does an AI agent stay inside the limits you set when it can move money?",
    )
    sub = parser.add_subparsers(dest="group", required=True)

    scenarios = sub.add_parser("scenarios", help="the scenario suite").add_subparsers(
        dest="command", required=True
    )
    listing = scenarios.add_parser("list", help="every scenario and its split")
    listing.add_argument("--category", choices=CATEGORIES)
    listing.set_defaults(func=lambda args: cmd_scenarios_list(args))
    scenarios.add_parser("check", help="validate every scenario").set_defaults(
        func=lambda args: cmd_scenarios_check()
    )
    show_one = scenarios.add_parser("show", help="one scenario in full")
    show_one.add_argument("id")
    show_one.set_defaults(func=lambda args: cmd_scenarios_show(args))
    scenarios.add_parser(
        "categories", help="the taxonomy, and how well each is covered"
    ).set_defaults(func=lambda args: cmd_scenarios_categories())

    splits = sub.add_parser("splits", help="dev / test / heldout").add_subparsers(
        dest="command", required=True
    )
    frz = splits.add_parser("freeze", help="cut the split, once")
    frz.add_argument("--seed", type=int, default=DEFAULT_SEED)
    frz.add_argument("--force", action="store_true", help="re-cut anyway (almost never right)")
    frz.set_defaults(func=lambda args: cmd_splits_freeze(args))

    splits.add_parser("assign-new", help="place families added since the freeze").set_defaults(
        func=lambda args: cmd_splits_assign_new()
    )
    splits.add_parser("status", help="shares, and the heldout access log").set_defaults(
        func=lambda args: cmd_splits_status()
    )
    splits.add_parser("check", help="what is wrong with the split").set_defaults(
        func=lambda args: cmd_splits_check()
    )
    splits.add_parser("coverage", help="category coverage as JSON").set_defaults(
        func=lambda args: cmd_splits_coverage()
    )
    show = splits.add_parser("show", help="the scenarios in one split")
    show.add_argument("split", choices=SPLITS)
    show.add_argument("--reason", default="", help="required for heldout; it is logged")
    show.set_defaults(func=lambda args: cmd_splits_show(args))

    splits.add_parser("log", help="every time heldout has been opened").set_defaults(
        func=lambda args: cmd_splits_log()
    )

    runner = sub.add_parser("run", help="run a model against a split")
    runner.add_argument(
        "--split",
        choices=(*SPLITS, "open"),
        default="dev",
        help="one split, or 'open' for every split that is not locked (dev + test)",
    )
    runner.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        metavar="MODEL",
        help="one of: " + ", ".join(sorted(MODELS)) + " — or, with --base-url, any id that "
        "endpoint serves. The server decides what exists, not this list.",
    )
    runner.add_argument("--effort", choices=EFFORT_LEVELS, default="high")
    runner.add_argument("--samples", type=int, default=1, help="runs per scenario")
    runner.add_argument("--limit", type=int, help="only the first N scenarios")
    runner.add_argument("--scenario", action="append", help="run only these ids")
    runner.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    runner.add_argument("--reason", default="", help="required for heldout; it is logged")
    runner.add_argument(
        "--dry-run",
        action="store_true",
        help="estimate the cost and send nothing. Free, and always worth doing first.",
    )
    runner.add_argument(
        "--base-url",
        default="",
        help="an OpenAI-compatible endpoint, e.g. http://localhost:11434/v1 for Ollama. "
        "Any --model id works against it.",
    )
    runner.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="environment variable holding the key for a hosted endpoint. Ignored locally.",
    )
    runner.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        metavar="SECONDS",
        help="how long to wait for one reply (default %(default)ss). A local model too big "
        "for the machine will blow through this; the message says so rather than hanging.",
    )
    runner.add_argument(
        "--guardrail",
        choices=sorted(GUARDRAILS),
        default="none",
        help="a hard control layer in front of the agent. It changes whether money moves, "
        "never what the agent decided — violation and breach are reported separately.",
    )
    runner.add_argument(
        "--brief",
        action="store_true",
        help="one line per scenario instead of the why-it-passed-or-failed summary",
    )
    runner.add_argument(
        "--simulate",
        choices=STYLES,
        help="run a scripted stand-in agent instead of a model. No API call, no cost, "
        "and no result about any model — see the whole pipeline work.",
    )
    runner.set_defaults(func=lambda args: cmd_run(args))

    doctor = sub.add_parser(
        "doctor", help="check an OpenAI-compatible endpoint before running a sweep against it"
    )
    doctor.add_argument("--base-url", default="", help="e.g. http://localhost:11434/v1")
    doctor.add_argument("--model", default="qwen2.5:1.5b")
    doctor.add_argument("--api-key-env", default="OPENAI_API_KEY")
    doctor.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        metavar="SECONDS",
        help="how long to wait for one reply (default %(default)ss). A local model too big "
        "for the machine will blow through this; the message says so rather than hanging.",
    )
    doctor.add_argument(
        "--show-request",
        action="store_true",
        help="print the tool-call probe body, to replay by hand against another model",
    )
    doctor.set_defaults(func=lambda args: cmd_doctor(args))

    report = sub.add_parser("report", help="the frontier for a stored run")
    report.add_argument("run_id", nargs="?", help="omit to list stored runs")
    report.set_defaults(func=lambda args: cmd_report(args))

    return parser


def _write_utf8() -> None:
    """Make stdout and stderr UTF-8, whatever the platform thinks the locale is.

    Every amount this tool prints carries a `£`, and the headings use en and em dashes.
    On Windows, Python encodes stdout with the ANSI code page (cp1252) whenever stdout is
    a pipe rather than a console, while the shell decodes it with the OEM code page
    (cp850). The bytes survive; the characters do not. `£` is cp1252 0xA3, which cp850
    renders as `ú`, so a real dev-split run came back reading:

        paid ú1,200.00 where an invoice is ú120,000.00 ù 100x out

    Nothing was wrong with the numbers. The one currency symbol in a tool about money was
    unreadable the moment the output was redirected to a file, which is the first thing
    anyone does with a fourteen-minute run.

    `errors="replace"` rather than a crash: a mangled character is bad, a run that dies at
    the summary after fourteen minutes of work is worse.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # A stream that refuses to be reconfigured still works; it just may not
                # render the pound sign. Never let this stop the command from running.
                pass


def main(argv: list[str] | None = None) -> int:
    _write_utf8()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
