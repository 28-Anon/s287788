"""Tests for the EDGAR client. Nothing here touches the network.

The transport is injected, so a "response" is one line of fake data. That is the whole
reason the client takes a transport argument: an HTTP client you cannot test offline is an
HTTP client you will not test.
"""

import json

import pytest

from covenant_evals.corpus.edgar import (
    PAGE_SIZE,
    EdgarClient,
    EdgarError,
    Hit,
    RateLimiter,
    Response,
    document_url,
    filing_index_url,
    parse_search_response,
    validate_user_agent,
)

GOOD_UA = "Ada Lovelace ada@analytical-engine.org"


def search_payload(*ids: str) -> bytes:
    return json.dumps(
        {
            "hits": {
                "total": {"value": len(ids)},
                "hits": [
                    {
                        "_id": identifier,
                        "_source": {
                            "adsh": identifier.split(":")[0],
                            "ciks": ["0000320123"],
                            "display_names": ["Acme Corp (ACME) (CIK 0000320123)"],
                            "root_form": "8-K",
                            "file_date": "2024-03-04",
                        },
                    }
                    for identifier in ids
                ],
            }
        }
    ).encode()


# -- URL construction ------------------------------------------------------------


def test_document_url_strips_dashes_and_leading_zeros():
    url = document_url("0000320123", "0000950170-24-012345", "ex101.htm")
    assert url == "https://www.sec.gov/Archives/edgar/data/320123/000095017024012345/ex101.htm"


def test_filing_index_url():
    url = filing_index_url("320123", "0000950170-24-012345")
    assert url.endswith("/320123/000095017024012345/index.json")


def test_all_zero_cik_is_rejected():
    with pytest.raises(ValueError):
        document_url("0000000000", "0000950170-24-012345", "x.htm")


# -- User-Agent policy -----------------------------------------------------------


def test_a_real_user_agent_is_accepted():
    assert validate_user_agent(GOOD_UA) == GOOD_UA


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        "   ",
        "Ada Lovelace",  # no contact address
        "python-requests/2.31 ada@example.org",  # generic client string
        "Ada Lovelace ada@example.com",  # placeholder domain
    ],
)
def test_missing_or_generic_user_agents_are_refused_before_we_call_edgar(bad):
    with pytest.raises(EdgarError):
        validate_user_agent(bad)


# -- rate limiting ---------------------------------------------------------------


def test_rate_limiter_spaces_requests_out():
    now = [0.0]
    slept: list[float] = []

    def clock():
        return now[0]

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(per_second=10.0, clock=clock, sleep=sleep)
    limiter.wait()  # first call is immediate
    limiter.wait()
    limiter.wait()

    assert slept == [pytest.approx(0.1), pytest.approx(0.1)]


def test_rate_limiter_does_not_sleep_when_time_has_already_passed():
    now = [0.0]

    def sleep(seconds):
        raise AssertionError("should not have slept")

    limiter = RateLimiter(per_second=10.0, clock=lambda: now[0], sleep=sleep)
    limiter.wait()
    now[0] = 5.0
    limiter.wait()


# -- request handling ------------------------------------------------------------


def make_client(responses, **kwargs):
    """A client whose transport replays a list of responses and records the URLs called."""
    calls = []

    def transport(url, headers):
        calls.append((url, headers))
        return responses[min(len(calls) - 1, len(responses) - 1)]

    limiter = RateLimiter(per_second=1000.0, sleep=lambda _: None)
    client = EdgarClient(
        GOOD_UA, transport=transport, rate_limiter=limiter, sleep=lambda _: None, **kwargs
    )
    return client, calls


def test_user_agent_is_sent_on_every_request():
    client, calls = make_client([Response(200, search_payload("0000950170-24-012345:ex.htm"))])
    client.search('"credit agreement"')
    assert calls[0][1]["User-Agent"] == GOOD_UA


def test_403_explains_the_user_agent_and_does_not_retry():
    client, calls = make_client([Response(403, b"")])
    with pytest.raises(EdgarError, match="User-Agent"):
        client.search("x")
    assert len(calls) == 1, "a 403 must not be retried — retrying extends the block"


def test_429_is_retried_then_succeeds():
    ok = search_payload("0000950170-24-012345:ex.htm")
    responses = [Response(429, b""), Response(200, ok)]
    calls = []

    def transport(url, headers):
        calls.append(url)
        return responses[len(calls) - 1] if len(calls) <= len(responses) else responses[-1]

    client = EdgarClient(
        GOOD_UA,
        transport=transport,
        rate_limiter=RateLimiter(per_second=1000.0, sleep=lambda _: None),
        sleep=lambda _: None,
    )
    assert len(client.search("x")) == 1
    assert len(calls) == 2


def test_404_is_reported_not_retried():
    client, calls = make_client([Response(404, b"")])
    with pytest.raises(EdgarError, match="404"):
        client.search("x")
    assert len(calls) == 1


# -- parsing ---------------------------------------------------------------------


def test_parse_search_response_extracts_the_pieces():
    hits = parse_search_response(search_payload("0000950170-24-012345:ex101.htm"))
    assert len(hits) == 1
    hit = hits[0]
    assert hit.accession == "0000950170-24-012345"
    assert hit.filename == "ex101.htm"
    assert hit.cik == "320123"  # leading zeros stripped for Archives paths
    assert hit.ref == "0000950170-24-012345:ex101.htm"
    assert hit.url.endswith("/320123/000095017024012345/ex101.htm")


def test_malformed_hits_are_skipped_not_fatal():
    payload = json.dumps(
        {
            "hits": {
                "hits": [
                    {"_id": "no-colon-here", "_source": {"ciks": ["0000320123"]}},
                    {"_id": "0000950170-24-1:a.htm", "_source": {}},  # no ciks
                    {
                        "_id": "0000950170-24-2:b.htm",
                        "_source": {"ciks": ["0000320123"], "adsh": "0000950170-24-2"},
                    },
                ]
            }
        }
    ).encode()
    hits = parse_search_response(payload)
    assert [h.filename for h in hits] == ["b.htm"]


def test_empty_response_is_empty_not_an_error():
    assert parse_search_response(b'{"hits": {"hits": []}}') == []


def paged_client(*pages):
    """A client whose transport serves the given response bodies in order."""
    calls = []

    def transport(url, headers):
        calls.append(url)
        return Response(200, pages[min(len(calls) - 1, len(pages) - 1)])

    client = EdgarClient(
        GOOD_UA,
        transport=transport,
        rate_limiter=RateLimiter(per_second=1000.0, sleep=lambda _: None),
        sleep=lambda _: None,
    )
    return client, calls


def test_a_short_first_page_stops_immediately():
    # EDGAR returns at most 100 hits per page, so fewer than 100 means there is no more.
    client, calls = paged_client(search_payload("0000950170-24-1:a.htm"))
    assert len(client.search("x", limit=500)) == 1
    assert len(calls) == 1


def test_a_full_page_is_followed_by_a_second_request():
    full = search_payload(*[f"0000950170-24-{i:06d}:a.htm" for i in range(PAGE_SIZE)])
    client, calls = paged_client(full, b'{"hits": {"hits": []}}')

    hits = client.search("x", limit=500)

    assert len(hits) == PAGE_SIZE
    assert len(calls) == 2, "should ask for a second page, then stop on the empty one"
    assert "from=100" in calls[1]


# -- telling an agreement from everything that merely mentions one ----------------
#
# A live search for "Majority Lenders" returned twenty hits of which most were DIP
# amendments, waivers and notices. Those are structurally different documents and they do
# not produce good items, so search hides them by default.


def make_hit(filename="ex101.htm", description="", file_type="EX-10.1", filed="2024-03-04"):
    return Hit(
        accession="0000950170-24-012345",
        filename=filename,
        cik="320123",
        company="Acme Corp",
        form="8-K",
        filed=filed,
        file_type=file_type,
        description=description,
    )


def test_a_plain_credit_agreement_scores_highest():
    from covenant_evals.corpus.edgar import looks_like_agreement

    assert looks_like_agreement(make_hit(description="Credit Agreement")) == 2


@pytest.mark.parametrize(
    "description",
    [
        "Second Amendment to Credit Agreement",
        "Credit Agreement Supplement",
        "Waiver and Consent under Credit Agreement",
        "Joinder to Credit Agreement",
        "Notice of Termination",
        "Payoff Letter",
        "Forbearance Agreement",
    ],
)
def test_derivative_documents_are_recognised(description):
    from covenant_evals.corpus.edgar import is_derivative, looks_like_agreement

    hit = make_hit(description=description)
    assert is_derivative(hit)
    assert looks_like_agreement(hit) < looks_like_agreement(
        make_hit(description="Credit Agreement")
    )


def test_a_derivative_is_recognised_from_its_filename_alone():
    # EDGAR descriptions are frequently empty; the filename is often all there is.
    from covenant_evals.corpus.edgar import is_derivative

    assert is_derivative(make_hit(filename="exh102-dipamendment1.htm"))
    assert is_derivative(make_hit(filename="cm-2ndamendmentexecuted.htm"))
    assert not is_derivative(make_hit(filename="ex101creditagreement.htm"))


def test_an_unrelated_exhibit_scores_between_the_two():
    from covenant_evals.corpus.edgar import looks_like_agreement

    unclear = looks_like_agreement(make_hit(filename="ex991.htm", file_type="EX-99.1"))
    assert unclear < looks_like_agreement(make_hit(description="Credit Agreement"))
    assert unclear > looks_like_agreement(make_hit(description="Amendment to Credit Agreement"))
