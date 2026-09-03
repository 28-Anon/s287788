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
from .sections import pattern_census, segment

#: What parse_search_response reads out of each hit, as EDGAR actually names them —
#: confirmed against a live response on 2026-09-03. Documentation implied `root_form`;
#: the service returns `root_forms`, and reading the wrong one silently recorded an empty
#: form for every hit rather than failing.
EXPECTED_SOURCE_KEYS = ("adsh", "ciks", "display_names", "file_date")

#: The form lives under one of these. Either is fine; neither is not.
FORM_KEYS = ("root_forms", "form")

#: Exhibit types that are plausibly a credit agreement. Used to pick a sensible sample
#: document rather than whatever happened to sort first.
CREDIT_EXHIBIT_HINTS = ("ex-10", "ex-4")
CREDIT_NAME_HINTS = ("credit", "loan", "facility", "financing")


@dataclass
class Step:
    name: str
    ok: bool
    detail: str = ""
    fix: str = ""
    #: "fail" stops the verdict; "warn" is reported but does not mean the pipeline is
    #: broken. One oddly-shaped document is not a broken pipeline, and conflating the two
    #: teaches you to ignore the output.
    level: str = "fail"


@dataclass
class Report:
    steps: list[Step] = field(default_factory=list)
    observed: dict[str, Any] = field(default_factory=dict)

    def add(
        self, name: str, ok: bool, detail: str = "", fix: str = "", level: str = "fail"
    ) -> bool:
        self.steps.append(Step(name, ok, detail, fix, level))
        return ok

    @property
    def ok(self) -> bool:
        return all(step.ok or step.level == "warn" for step in self.steps)

    @property
    def warnings(self) -> list[Step]:
        return [s for s in self.steps if not s.ok and s.level == "warn"]


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
    has_form = any(key in source for key in FORM_KEYS)
    if not has_form:
        missing = [*missing, f"one of {list(FORM_KEYS)}"]

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

    hit = _pick_sample(parsed)
    report.observed["sample_url"] = hit.url
    report.observed["sample_file_type"] = hit.file_type
    report.add(
        "sample document chosen",
        True,
        f"{hit.filename} ({hit.file_type or 'type unknown'}) from {hit.form or '?'} "
        f"filed {hit.filed}",
    )

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
        detail += f" — {segmentation.warnings[0]}"

    report.add(
        "segmenter finds sections",
        bool(top),
        detail,
        "One document is not a verdict on the segmenter — amendments, term sheets and "
        "notices are not shaped like an agreement. Re-run with --paste and send the "
        "census: it says whether the headings were not matched at all, or were matched "
        "but rejected for not being set off by a blank line.",
        level="warn",
    )
    report.observed["section_labels"] = [s.label for s in top[:8]]
    report.observed["segmentation_warnings"] = segmentation.warnings
    if not top:
        report.observed["census"] = pattern_census(text)

    return report


def _pick_sample(hits: list) -> object:
    """Choose a hit that is plausibly a credit agreement.

    The first version took hits[0], which on a real search was a second amendment — a
    document with none of the structure the segmenter looks for. Diagnosing the pipeline
    with an unrepresentative sample tells you very little.
    """

    def score(hit) -> tuple[int, int]:
        exhibit = 1 if any(h in hit.file_type.lower() for h in CREDIT_EXHIBIT_HINTS) else 0
        name = f"{hit.filename} {hit.description}".lower()
        named = 1 if any(h in name for h in CREDIT_NAME_HINTS) else 0
        amendment = -1 if "amend" in name else 0
        return (exhibit + named + amendment, -len(hit.filename))

    return max(hits, key=score)


def format_report(report: Report, *, paste: bool = False) -> str:
    """Human-readable result, with an optional structure-only block to send on."""
    lines = []
    for step in report.steps:
        mark = "PASS" if step.ok else ("WARN" if step.level == "warn" else "FAIL")
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
        if report.warnings:
            lines.append(
                f"{len(report.warnings)} warning(s) above: worth a look, but they do not "
                "mean anything is broken."
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
