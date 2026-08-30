"""Getting real credit agreements out of SEC EDGAR and onto disk, reproducibly.

Three jobs, in order:

1. **search** — find candidate exhibits with EDGAR full-text search
2. **fetch**  — download them once, cache them, and never download them again
3. **normalise + hash** — turn messy filing HTML into stable plain text, and pin that text
   with a SHA-256 so a label written today can be checked against the same bytes in a year

The documents themselves are never committed. `data/corpus/manifest.json` holds accession
numbers and hashes; the cache under `data/corpus/cache/` is gitignored and rebuildable.
"""

from .edgar import EdgarClient, EdgarError, Hit, document_url, filing_index_url
from .manifest import Agreement, Manifest
from .normalise import NORMALISER_VERSION, normalise_html, sha256_text
from .sections import (
    SEGMENTER_VERSION,
    Section,
    Segmentation,
    find_spans,
    segment,
    verify_span,
)

__all__ = [
    "Agreement",
    "EdgarClient",
    "EdgarError",
    "Hit",
    "Manifest",
    "NORMALISER_VERSION",
    "SEGMENTER_VERSION",
    "Section",
    "Segmentation",
    "document_url",
    "filing_index_url",
    "find_spans",
    "normalise_html",
    "segment",
    "sha256_text",
    "verify_span",
]
