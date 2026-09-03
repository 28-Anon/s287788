"""A polite, rate-limited EDGAR client.

EDGAR is free and unauthenticated, and in exchange the SEC asks two things. Break either
and you get a 403 and a roughly ten-minute IP block:

1. Send a `User-Agent` that identifies you, with a contact email.
2. Stay under 10 requests per second.

This module enforces both on your behalf, and refuses to make a request at all if the
User-Agent is missing or looks generic. That refusal is a feature: a loud failure on your
laptop is much cheaper than a silent block halfway through fetching 25 documents.

Network access is injected (`transport=`), so every test in tests/test_edgar.py runs
offline. Nothing here reaches the network unless you call it with the default transport.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

#: EDGAR full-text search. The uppercase /LATEST/ matters — /latest/ returns 404.
#: Coverage does not extend to the whole EDGAR archive; confirm the earliest covered year
#: on your first run rather than trusting this comment.
FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

#: The SEC's published ceiling is 10 requests/second. We sit under it deliberately: the
#: cost of being slightly slow is nothing, the cost of being blocked is your afternoon.
DEFAULT_REQUESTS_PER_SECOND = 8.0

#: EFTS returns at most 100 hits per request regardless of what you ask for.
PAGE_SIZE = 100

#: Retried once each, with exponential backoff. 429 is rate limiting; 5xx is EDGAR having
#: a moment. A 403 is never retried — it means your User-Agent is wrong, and hammering it
#: extends the block.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4


class EdgarError(RuntimeError):
    """Anything that went wrong talking to EDGAR, with an actionable message."""


@dataclass(frozen=True)
class Hit:
    """One document returned by full-text search.

    The field names below are what EDGAR actually returns, confirmed against a live
    response on 2026-09-03 — not what its documentation implies. The two differ: there is
    no `root_form`, only `root_forms` (a list) and `form`.
    """

    accession: str  # with dashes, e.g. "0000950170-24-012345"
    filename: str  # e.g. "ex101creditagreement.htm"
    cik: str  # numeric, no leading zeros, e.g. "320193"
    company: str
    form: str  # the filing: "8-K", "10-Q"
    filed: str  # ISO date as EDGAR reports it
    file_type: str = ""  # the exhibit within it: "EX-10.1". This is the useful one
    description: str = ""  # EDGAR's own description of the exhibit

    @property
    def ref(self) -> str:
        """The identifier used everywhere else: `accession:filename`."""
        return f"{self.accession}:{self.filename}"

    @property
    def url(self) -> str:
        return document_url(self.cik, self.accession, self.filename)


def _accession_nodash(accession: str) -> str:
    return accession.replace("-", "")


def _cik_numeric(cik: str) -> str:
    """EDGAR reports CIKs zero-padded to 10 digits; Archives paths want them unpadded."""
    stripped = cik.strip().lstrip("0")
    if not stripped:
        raise ValueError(f"not a usable CIK: {cik!r}")
    return stripped


def document_url(cik: str, accession: str, filename: str) -> str:
    """Direct URL to one document inside a filing."""
    return f"{ARCHIVES_BASE}/{_cik_numeric(cik)}/{_accession_nodash(accession)}/{filename}"


def filing_index_url(cik: str, accession: str) -> str:
    """Machine-readable listing of every file in a filing, including exhibit types."""
    return f"{ARCHIVES_BASE}/{_cik_numeric(cik)}/{_accession_nodash(accession)}/index.json"


def validate_user_agent(user_agent: str | None) -> str:
    """Return the User-Agent, or raise with an explanation of how to set one.

    The SEC asks for identification and a contact address. A blank or obviously generic
    value is rejected here rather than by EDGAR, because EDGAR rejects it with a block.
    """
    if not user_agent or not user_agent.strip():
        raise EdgarError(
            "EDGAR_USER_AGENT is not set.\n"
            "The SEC requires a User-Agent identifying you and a contact email.\n"
            'Set it in your .env, e.g.  EDGAR_USER_AGENT="Ada Lovelace ada@example.com"'
        )

    value = user_agent.strip()
    lowered = value.lower()

    if "@" not in value:
        raise EdgarError(
            f"EDGAR_USER_AGENT ({value!r}) has no contact email. "
            "The SEC's fair-access policy asks for one."
        )

    generic = ("python-urllib", "python-requests", "curl/", "mozilla/", "test", "example.com")
    if any(marker in lowered for marker in generic):
        raise EdgarError(
            f"EDGAR_USER_AGENT ({value!r}) looks generic or like a placeholder. "
            "Use your real name and a real contact email — this is the header the SEC "
            "uses to reach you if your script misbehaves."
        )

    return value


class RateLimiter:
    """Spaces requests out to at most `per_second`. Clock and sleep are injectable."""

    def __init__(
        self,
        per_second: float = DEFAULT_REQUESTS_PER_SECOND,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if per_second <= 0:
            raise ValueError("per_second must be positive")
        self._min_interval = 1.0 / per_second
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            remaining = self._min_interval - (self._clock() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()


@dataclass
class Response:
    """What a transport hands back. Deliberately tiny so fakes are one line to write."""

    status: int
    body: bytes


def urllib_transport(url: str, headers: dict[str, str]) -> Response:
    """The real network call. The only function in this package that touches the internet."""
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 - https URLs only
    try:
        with urllib.request.urlopen(request, timeout=30) as handle:  # noqa: S310
            return Response(status=handle.status, body=handle.read())
    except urllib.error.HTTPError as exc:
        return Response(status=exc.code, body=exc.read() if exc.fp else b"")
    except urllib.error.URLError as exc:
        raise EdgarError(f"could not reach {url}: {exc.reason}") from exc


class EdgarClient:
    """Search EDGAR and download filing documents, politely.

    >>> client = EdgarClient(user_agent="Ada Lovelace ada@example.org")  # doctest: +SKIP
    >>> hits = client.search('"credit agreement"', forms=["8-K"], limit=20)  # doctest: +SKIP
    """

    def __init__(
        self,
        user_agent: str,
        *,
        transport: Callable[[str, dict[str, str]], Response] = urllib_transport,
        rate_limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.user_agent = validate_user_agent(user_agent)
        self._transport = transport
        self._limiter = rate_limiter or RateLimiter()
        self._sleep = sleep

    # -- low level ----------------------------------------------------------------

    def _get(self, url: str, *, accept: str = "application/json") -> bytes:
        headers = {"User-Agent": self.user_agent, "Accept": accept}

        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._limiter.wait()
            response = self._transport(url, headers)

            if response.status == 200:
                return response.body

            if response.status == 403:
                raise EdgarError(
                    f"EDGAR returned 403 for {url}.\n"
                    "This almost always means the User-Agent was rejected. Do not retry — "
                    "repeated requests extend the block. Fix EDGAR_USER_AGENT and wait "
                    "about ten minutes."
                )

            if response.status in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                self._sleep(2.0**attempt)
                continue

            raise EdgarError(f"EDGAR returned {response.status} for {url}")

        raise EdgarError(f"gave up on {url} after {MAX_ATTEMPTS} attempts")

    # -- search -------------------------------------------------------------------

    def search_raw(
        self,
        query: str,
        *,
        forms: list[str] | None = None,
        offset: int = 0,
    ) -> bytes:
        """The undecoded search response.

        Exists so the doctor can inspect the envelope EDGAR actually returns rather than
        only what the parser managed to make of it — the difference between "no results"
        and "the field names changed" is the whole diagnosis.
        """
        params: dict[str, str] = {"q": query, "from": str(offset)}
        if forms:
            params["forms"] = ",".join(forms)
        return self._get(f"{FULL_TEXT_SEARCH_URL}?{urllib.parse.urlencode(params)}")

    def search(
        self,
        query: str,
        *,
        forms: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = PAGE_SIZE,
    ) -> list[Hit]:
        """Full-text search across filings.

        Wrap a phrase in double quotes for an exact match — unquoted terms are treated as
        an OR search and will bury you in irrelevant filings.
        """
        hits: list[Hit] = []
        offset = 0

        while len(hits) < limit:
            params: dict[str, str] = {"q": query, "from": str(offset)}
            if forms:
                params["forms"] = ",".join(forms)
            if start_date and end_date:
                params["dateRange"] = "custom"
                params["startdt"] = start_date
                params["enddt"] = end_date

            url = f"{FULL_TEXT_SEARCH_URL}?{urllib.parse.urlencode(params)}"
            page = parse_search_response(self._get(url))
            if not page:
                break

            hits.extend(page)

            # A short page means there is no next page. Without this, a backend that
            # keeps serving the same page would loop until `limit` was reached — which
            # is exactly what happened the first time this was tested.
            if len(page) < PAGE_SIZE:
                break

            offset += PAGE_SIZE

        return hits[:limit]

    # -- documents ----------------------------------------------------------------

    def filing_index(self, cik: str, accession: str) -> list[dict[str, object]]:
        """Every file in a filing, with its exhibit type. Useful for finding EX-10s."""
        body = self._get(filing_index_url(cik, accession))
        payload = json.loads(body)
        items = payload.get("directory", {}).get("item", [])
        return list(items)

    def document(self, cik: str, accession: str, filename: str) -> bytes:
        """Raw bytes of one document. Normalisation happens elsewhere, deliberately."""
        return self._get(document_url(cik, accession, filename), accept="*/*")


def parse_search_response(body: bytes) -> list[Hit]:
    """Turn an EFTS response into Hits.

    Response shape, for reference:

        {"hits": {"total": {"value": 412},
                  "hits": [{"_id": "0000950170-24-012345:ex101.htm",
                            "_source": {"adsh": "0000950170-24-012345",
                                        "ciks": ["0000320123"],
                                        "display_names": ["Acme Corp (ACME) (CIK 0000320123)"],
                                        "root_form": "8-K",
                                        "file_date": "2024-03-04"}}]}}

    Malformed hits are skipped rather than raising: one odd record should not abort a
    search that returned ninety-nine good ones.
    """
    payload = json.loads(body)
    raw_hits = payload.get("hits", {}).get("hits", [])

    parsed: list[Hit] = []
    for raw in raw_hits:
        identifier = raw.get("_id", "")
        if ":" not in identifier:
            continue
        accession, filename = identifier.split(":", 1)

        source = raw.get("_source", {})
        ciks = source.get("ciks") or []
        if not ciks:
            continue

        display_names = source.get("display_names") or [""]

        # EDGAR returns `root_forms` (a list) and `form` (a string). An earlier version of
        # this code read `root_form`, which does not exist, and silently recorded "" as the
        # form for every hit — the kind of bug that only appears against the real service.
        root_forms = source.get("root_forms") or []
        form = root_forms[0] if root_forms else source.get("form", "")

        parsed.append(
            Hit(
                accession=source.get("adsh", accession),
                filename=filename,
                cik=_cik_numeric(ciks[0]),
                company=display_names[0],
                form=form,
                filed=source.get("file_date", ""),
                file_type=source.get("file_type", ""),
                description=source.get("file_description", ""),
            )
        )

    return parsed


# ---------------------------------------------------------------------------
# Telling an agreement from everything that merely mentions one
# ---------------------------------------------------------------------------

#: Full-text search for a phrase like "Majority Lenders" returns every document that
#: *references* a facility — amendments, waivers, DIP orders, notices — and those vastly
#: outnumber the agreements themselves. They are structurally different documents and they
#: do not produce good items.
DERIVATIVE_HINTS = (
    "amend",
    "supplement",
    "waiver",
    "consent",
    "joinder",
    "notice",
    "assignment",
    "guarant",
    "forbearance",
    "termination",
    "payoff",
    "reaffirm",
)

AGREEMENT_HINTS = ("credit", "loan", "facility", "financing", "indenture")

CREDIT_EXHIBIT_HINTS = ("ex-10", "ex-4")


def looks_like_agreement(hit: Hit) -> int:
    """Rough score: 2 a plain agreement, 0 unclear, negative a derivative document.

    Deliberately crude. It orders a search result list and picks a sample; it does not
    decide what goes in the corpus. That judgement is the labeller's, and it is the single
    biggest source of bias in the results, so it stays manual.
    """
    haystack = f"{hit.filename} {hit.description}".lower()

    score = 0
    if any(hint in hit.file_type.lower() for hint in CREDIT_EXHIBIT_HINTS):
        score += 1
    if any(hint in haystack for hint in AGREEMENT_HINTS):
        score += 1
    if any(hint in haystack for hint in DERIVATIVE_HINTS):
        # Enough to outweigh both positive signals: a document that says "Amendment to
        # Credit Agreement" scores every agreement marker and is still not one, so it must
        # rank below an exhibit we know nothing about rather than level with it.
        score -= 3

    return score


def is_derivative(hit: Hit) -> bool:
    """True for a document that amends, waives or supplements an agreement."""
    haystack = f"{hit.filename} {hit.description}".lower()
    return any(hint in haystack for hint in DERIVATIVE_HINTS)
