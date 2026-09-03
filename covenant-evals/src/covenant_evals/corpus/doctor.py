"""One command that proves the EDGAR pipeline works — or says exactly what to fix.

Every endpoint shape in edgar.py came from EDGAR's documentation rather than from a live
response, because the machine this was written on cannot reach sec.gov. That is a real
weakness and this module exists to discharge it in about thirty seconds on a machine that
can.

It makes four requests, checks one assumption at a time, and on any mismatch prints the
keys it actually found rather than a generic failure. Structure, never content: the paste
output carries field names and one accession number, nothing else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .edgar import (
    FULL_TEXT_SEARCH_URL,
    EdgarClient,
    EdgarError,
    document_url,
    filing_index_url,
    parse_search_response,
)
from .normalise import normalise_html
from .sections import segment

#: What parse_search_response reads out of each hit. If EDGAR renames any of these, the
#: parser silently produces nothing useful, so they are checked individually.
EXPECTED_SOURCE_KEYS = ("adsh", "ciks", "display_names", "root_form", "file_date")


@dataclass
class Step:
    name: str
    ok: bool
    detail: str = ""
    fix: str = ""


@dataclass
class Report:
    steps: list[Step] = field(default_factory=list)
    observed: dict[str, Any] = field(default_factory=dict)

    def add(self, name: str, ok: bool, detail: str = "", fix: str = "") -> bool:
        self.steps.append(Step(name, ok, detail, fix))
        return ok

    @property
    def ok(self) -> bool:
        return all(step.ok for step in self.steps)


def run(client: EdgarClient, *, query: str = '"credit agreement"') -> Report:
    """Walk the pipeline end to end. Never raises — every failure becomes a step."""
    report = Report()

    # 1 -- can we reach full-text search at all -------------------------------------
    try:
        body = client.search_raw(query, forms=["8-K"])
    except EdgarError as exc:
        report.add(
            "search endpoint reachable",
            False,
            str(exc),
            "A 403 means the User-Agent was rejected: set EDGAR_USER_AGENT to your real "
            "name and a real email. Anything else, check the URL casing — /LATEST/ is "
            "uppercase and /latest/ returns 404.",
        )
        return report
    report.add("search endpoint reachable", True, f"HTTP 200 from {FULL_TEXT_SEARCH_URL}")

    # 2 -- is the envelope the shape the parser expects ------------------------------
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        report.add("response is JSON", False, str(exc), "EDGAR returned something else.")
        return report

    hits = payload.get("hits", {}).get("hits")
    if not report.add(
        "response has hits.hits",
        isinstance(hits, list) and bool(hits),
        f"top-level keys: {sorted(payload)}",
        "The envelope changed. parse_search_response in corpus/edgar.py reads "
        "payload['hits']['hits'] — point it at whatever holds the results now.",
    ):
        return report

    first = hits[0]
    report.observed["hit_keys"] = sorted(first)
    report.observed["source_keys"] = sorted(first.get("_source", {}))

    # 3 -- the two things the parser actually depends on ------------------------------
    identifier = first.get("_id", "")
    report.add(
        "_id is accession:filename",
        isinstance(identifier, str) and ":" in identifier,
        f"_id = {identifier!r}",
        "parse_search_response splits _id on ':' to get the accession and the filename. "
        "If the format changed, that split is what needs updating.",
    )
    report.observed["sample_id"] = identifier

    source = first.get("_source", {})
    missing = [key for key in EXPECTED_SOURCE_KEYS if key not in source]
    report.add(
        "_source carries the expected fields",
        not missing,
        f"missing {missing}; present: {sorted(source)}" if missing else "all present",
        "Map the new names in parse_search_response. Everything else keys off it.",
    )

    # 4 -- does the parser produce usable hits ----------------------------------------
    parsed = parse_search_response(body)
    if not report.add(
        "parser produces hits",
        bool(parsed),
        f"{len(parsed)} hit(s) from {len(hits)} raw",
        "The envelope parsed but no hit survived — usually a missing or reshaped 'ciks'.",
    ):
        return report

    hit = parsed[0]
    report.observed["sample_url"] = hit.url

    # 5 -- filing index ----------------------------------------------------------------
    try:
        index = client.filing_index(hit.cik, hit.accession)
        names = [str(entry.get("name")) for entry in index[:3]]
        report.add(
            "filing index lists documents",
            bool(index),
            f"{len(index)} files, e.g. {names}",
            "",
        )
        report.observed["index_keys"] = sorted(index[0]) if index else []
    except EdgarError as exc:
        report.add(
            "filing index lists documents",
            False,
            str(exc),
            f"Expected JSON at {filing_index_url(hit.cik, hit.accession)} with "
            "directory.item[]. `corpus add` uses this to confirm a document exists.",
        )
        return report

    # 6 -- fetch one document and run it through the pipeline ---------------------------
    try:
        raw = client.document(hit.cik, hit.accession, hit.filename)
    except EdgarError as exc:
        report.add(
            "document downloads",
            False,
            str(exc),
            f"Expected the file at {document_url(hit.cik, hit.accession, hit.filename)}",
        )
        return report

    text = normalise_html(raw.decode("utf-8", errors="replace"))
    report.add("document downloads", True, f"{len(raw):,} bytes → {len(text):,} characters")

    segmentation = segment(text)
    top = [s for s in segmentation if s.level <= 1]
    detail = f"{len(top)} top-level sections, {segmentation.count} total"
    if segmentation.warnings:
        detail += f", {len(segmentation.warnings)} warning(s)"
    report.add(
        "segmenter finds sections",
        bool(top),
        detail,
        "This one document may simply be an odd shape — check a few before changing "
        "patterns. `corpus sections --check` runs the whole corpus at once.",
    )
    report.observed["section_labels"] = [s.label for s in top[:8]]
    report.observed["segmentation_warnings"] = segmentation.warnings

    return report


def format_report(report: Report, *, paste: bool = False) -> str:
    """Human-readable result, with an optional structure-only block to send on."""
    lines = []
    for step in report.steps:
        mark = "PASS" if step.ok else "FAIL"
        lines.append(f"[{mark}] {step.name}")
        if step.detail:
            lines.append(f"       {step.detail}")
        if not step.ok and step.fix:
            lines.append(f"       fix: {step.fix}")

    lines.append("")
    if report.ok:
        lines.append(
            "The pipeline works against the live SEC. The 'never run for real' caveat in "
            "YOUR-TURN.md is now discharged — delete it."
        )
    else:
        lines.append(
            "Something differs from what the code expects. Re-run with --paste and send "
            "the block below; it contains field names and one accession number, no "
            "document text."
        )

    if paste:
        lines.append("\n--- structure only, safe to share ---")
        lines.append(json.dumps(report.observed, indent=2))

    return "\n".join(lines)
