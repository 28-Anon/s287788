"""Tests for assembling a candidate corpus. No network.

The behaviour that matters most here is what bootstrap *refuses* to decide: it must not
record a guessed governing law as though it were checked, because the US/English
comparison is one of the headline results and a guess in that field is indistinguishable
from a fact six weeks later.
"""

import json

from covenant_evals.corpus.bootstrap import DEFAULT_QUERIES, bootstrap, gather, to_agreements
from covenant_evals.corpus.edgar import EdgarClient, RateLimiter, Response
from covenant_evals.corpus.manifest import Manifest

GOOD_UA = "Ada Lovelace ada@analytical-engine.org"


def hit_json(accession, filename, description="Credit Agreement", filed="2024-03-04"):
    return {
        "_id": f"{accession}:{filename}",
        "_source": {
            "adsh": accession,
            "ciks": ["0000320123"],
            "display_names": ["Acme Corp (ACME)"],
            "root_forms": ["8-K"],
            "file_type": "EX-10.1",
            "file_description": description,
            "file_date": filed,
        },
    }


def client_returning(per_query_hits):
    """A client that serves a different result set for each query string."""
    calls = []

    def transport(url, headers):
        calls.append(url)
        for fragment, hits in per_query_hits.items():
            if fragment.replace(" ", "+") in url or fragment.replace(" ", "%20") in url:
                return Response(200, json.dumps({"hits": {"hits": hits}}).encode())
        return Response(200, json.dumps({"hits": {"hits": []}}).encode())

    client = EdgarClient(
        GOOD_UA,
        transport=transport,
        rate_limiter=RateLimiter(per_second=1000.0, sleep=lambda _: None),
        sleep=lambda _: None,
    )
    return client, calls


def test_every_query_is_run():
    client, calls = client_returning({})
    gather(client)
    assert len(calls) == len(DEFAULT_QUERIES)


def test_derivatives_never_reach_the_manifest():
    client, _ = client_returning(
        {
            "Required Lenders": [
                hit_json("0000950170-24-000001", "amendment.htm", "Second Amendment"),
                hit_json("0000950170-24-000002", "ex101.htm", "Credit Agreement"),
            ]
        }
    )
    refs = [c.hit.ref for c in gather(client)]
    assert refs == ["0000950170-24-000002:ex101.htm"]


def test_the_same_document_found_by_two_queries_is_added_once():
    shared = [hit_json("0000950170-24-000001", "ex101.htm")]
    client, _ = client_returning({"Required Lenders": shared, "Majority Lenders": shared})
    assert len(gather(client)) == 1


def test_results_are_interleaved_so_one_phrase_cannot_dominate():
    # A global ranking would let the busiest query fill the corpus, and the point of using
    # several is to get both drafting traditions.
    client, _ = client_returning(
        {
            "Required Lenders": [
                hit_json(f"0000950170-24-{i:06d}", "ex101.htm") for i in range(10)
            ],
            "Majority Lenders": [
                hit_json(f"0000950170-25-{i:06d}", "ex101.htm") for i in range(10)
            ],
        }
    )
    first_four = [c.query for c in gather(client)[:4]]
    assert '"Required Lenders"' in first_four
    assert '"Majority Lenders"' in first_four


def test_a_failing_query_does_not_lose_the_others():
    def transport(url, headers):
        if "Consolidated" in url or "Consolidated+EBITDA" in url:
            return Response(500, b"")
        return Response(
            200,
            json.dumps(
                {"hits": {"hits": [hit_json("0000950170-24-000001", "ex101.htm")]}}
            ).encode(),
        )

    client = EdgarClient(
        GOOD_UA,
        transport=transport,
        rate_limiter=RateLimiter(per_second=1000.0, sleep=lambda _: None),
        sleep=lambda _: None,
    )
    assert len(gather(client)) >= 1


def test_governing_law_is_never_guessed():
    # The query hints at the tradition, but a hint recorded in the same field as a checked
    # fact is indistinguishable from one later.
    client, _ = client_returning(
        {"Majority Lenders": [hit_json("0000950170-24-000001", "ex101.htm")]}
    )
    agreements = to_agreements(gather(client))
    assert agreements[0].governing_law == ""
    assert "probably English law" in agreements[0].note
    assert "PROVISIONAL" in agreements[0].note


def test_bootstrap_respects_the_count():
    client, _ = client_returning(
        {"Required Lenders": [hit_json(f"0000950170-24-{i:06d}", "ex101.htm") for i in range(50)]}
    )
    added, _ = bootstrap(client, Manifest(), count=7)
    assert len(added) == 7


def test_bootstrap_is_idempotent():
    client, _ = client_returning(
        {"Required Lenders": [hit_json(f"0000950170-24-{i:06d}", "ex101.htm") for i in range(5)]}
    )
    manifest = Manifest()
    first, _ = bootstrap(client, manifest, count=25)
    second, already = bootstrap(client, manifest, count=25)

    assert len(first) == 5
    assert second == []
    assert already == 5
    assert len(manifest.agreements) == 5
