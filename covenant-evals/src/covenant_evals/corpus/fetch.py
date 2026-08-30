"""Orchestration: manifest in, cached and hashed documents out.

Two properties matter more than anything else here.

**Idempotent.** Running fetch twice downloads nothing the second time. You will run it
many times while building the corpus, and EDGAR should not notice.

**Honest about change.** If a document's bytes differ from what was recorded, that is
reported as a conflict rather than quietly overwritten. Filings do get replaced. A label
written against text that has since changed is broken, and you need to know.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .edgar import EdgarClient, Hit
from .manifest import DEFAULT_CACHE, Agreement, Manifest
from .normalise import NORMALISER_VERSION, normalise_html, sha256_bytes, sha256_text
from .sections import SEGMENTER_VERSION, segment


@dataclass
class FetchResult:
    ref: str
    status: str  # "fetched" | "cached" | "conflict" | "failed"
    detail: str = ""
    char_count: int = 0


def agreement_from_hit(hit: Hit, note: str = "", governing_law: str = "") -> Agreement:
    return Agreement(
        accession=hit.accession,
        filename=hit.filename,
        cik=hit.cik,
        company=hit.company,
        form=hit.form,
        filed=hit.filed,
        governing_law=governing_law,
        note=note,
    )


def fetch_one(
    client: EdgarClient,
    agreement: Agreement,
    *,
    cache_dir: Path = DEFAULT_CACHE,
    force: bool = False,
) -> FetchResult:
    """Download, normalise, hash and cache a single agreement.

    Mutates `agreement` in place with the hashes and counts on success.
    """
    raw_path = agreement.cache_path(cache_dir)
    text_path = agreement.text_path(cache_dir)

    if raw_path.exists() and not force:
        raw = raw_path.read_bytes()
        source = "cache"
    else:
        try:
            raw = client.document(agreement.cik, agreement.accession, agreement.filename)
        except Exception as exc:  # surfaced as a result, not an exception: one bad
            return FetchResult(agreement.ref, "failed", str(exc))  # document must not
        raw_path.parent.mkdir(parents=True, exist_ok=True)  # abort the whole run
        raw_path.write_bytes(raw)
        source = "network"

    raw_hash = sha256_bytes(raw)
    text = normalise_html(raw.decode("utf-8", errors="replace"))
    text_hash = sha256_text(text)

    if agreement.is_fetched and not force:
        if agreement.text_sha256 != text_hash:
            return FetchResult(
                agreement.ref,
                "conflict",
                "normalised text no longer matches the recorded hash — either the filing "
                "was replaced or the normaliser changed. Any item labelled against this "
                "document needs re-checking before you trust it.",
            )
        return FetchResult(agreement.ref, "cached", char_count=len(text))

    text_path.write_text(text, encoding="utf-8")

    agreement.raw_sha256 = raw_hash
    agreement.text_sha256 = text_hash
    agreement.char_count = len(text)
    agreement.normaliser_version = NORMALISER_VERSION
    agreement.fetched_at = datetime.now(UTC).isoformat(timespec="seconds")

    # Segment now rather than on demand: the section count is a regression signal, and a
    # document the segmenter cannot read is worth discovering at fetch time.
    segmentation = segment(text)
    agreement.section_count = segmentation.count
    agreement.segmenter_version = SEGMENTER_VERSION

    detail = f"from {source}"
    if segmentation.warnings:
        detail += f"; {len(segmentation.warnings)} segmentation warning(s)"

    return FetchResult(agreement.ref, "fetched", detail, char_count=len(text))


def fetch_all(
    client: EdgarClient,
    manifest: Manifest,
    *,
    cache_dir: Path = DEFAULT_CACHE,
    force: bool = False,
) -> list[FetchResult]:
    """Fetch everything in the manifest. Never raises for a single bad document."""
    results = []
    for agreement in sorted(manifest.agreements, key=lambda a: a.ref):
        results.append(fetch_one(client, agreement, cache_dir=cache_dir, force=force))
    return results


def load_text(agreement: Agreement, *, cache_dir: Path = DEFAULT_CACHE) -> str:
    """The normalised text of a fetched agreement, from the cache.

    Raises rather than returning an empty string: silently segmenting nothing would give a
    confident, wrong answer, which is the failure mode this whole project exists to catch.
    """
    path = agreement.text_path(cache_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"{agreement.ref} has not been fetched yet — run `make corpus-fetch` first"
        )
    return path.read_text(encoding="utf-8")
