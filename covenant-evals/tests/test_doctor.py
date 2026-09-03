"""Tests for the EDGAR pipeline doctor, offline.

The doctor exists because the pipeline was written against documentation rather than
against a live response. These tests check that it reports each possible mismatch
precisely — a diagnostic that only says "something is wrong" is not worth running.
"""

import json

from covenant_evals.corpus.doctor import format_report, run
from covenant_evals.corpus.edgar import EdgarClient, RateLimiter, Response

GOOD_UA = "Ada Lovelace ada@analytical-engine.org"

DOC_HTML = b"""<html><body>
<p>ARTICLE VII</p><p>SECTION 7.01. Indebtedness.</p>
<p>The Borrower shall not incur Indebtedness.</p>
<p>SECTION 7.02. Liens.</p><p>The Borrower shall not create any Lien.</p>
<p>SECTION 7.03. Restricted Payments.</p><p>No dividends.</p>
</body></html>"""


def search_body(**source_overrides) -> bytes:
    # These are EDGAR's real field names, taken from a live response on 2026-09-03.
    # The earlier fixture used "root_form", which the service does not return — which is
    # exactly why the mistake survived until someone ran it for real.
    source = {
        "adsh": "0000950170-24-012345",
        "ciks": ["0000320123"],
        "display_names": ["Acme Corp (ACME)"],
        "root_forms": ["8-K"],
        "form": "8-K",
        "file_type": "EX-10.1",
        "file_description": "Credit Agreement",
        "file_date": "2024-03-04",
    }
    source.update(source_overrides)
    return json.dumps(
        {
            "hits": {
                "total": {"value": 1},
                "hits": [{"_id": "0000950170-24-012345:ex101.htm", "_source": source}],
            }
        }
    ).encode()


INDEX_BODY = json.dumps(
    {"directory": {"item": [{"name": "ex101.htm", "type": "EX-10.1", "size": "120000"}]}}
).encode()


def client_for(responses: dict[str, Response]):
    """Route by URL fragment so each step can be failed independently."""

    def transport(url, headers):
        for fragment, response in responses.items():
            if fragment in url:
                return response
        return Response(404, b"")

    return EdgarClient(
        GOOD_UA,
        transport=transport,
        rate_limiter=RateLimiter(per_second=1000.0, sleep=lambda _: None),
        sleep=lambda _: None,
    )


def healthy(**source_overrides):
    return client_for(
        {
            "search-index": Response(200, search_body(**source_overrides)),
            "index.json": Response(200, INDEX_BODY),
            "ex101.htm": Response(200, DOC_HTML),
        }
    )


def steps(report):
    return {step.name: step for step in report.steps}


def test_a_working_pipeline_passes_every_step():
    report = run(healthy())
    assert report.ok, [s.name for s in report.steps if not s.ok]
    assert {s.name for s in report.steps} == {
        "search endpoint reachable",
        "response has hits.hits",
        "_id is accession:filename",
        "_source carries the expected fields",
        "parser produces hits",
        "sample document chosen",
        "filing index lists documents",
        "document downloads",
        "segmenter finds sections",
    }


def test_a_403_stops_at_the_first_step_and_names_the_cause():
    report = run(client_for({"search-index": Response(403, b"")}))
    assert not report.ok
    assert len(report.steps) == 1
    assert "User-Agent" in steps(report)["search endpoint reachable"].fix


def test_a_renamed_source_field_is_named_precisely():
    # The failure this is really guarding: EDGAR renames a field, the parser silently
    # produces nothing, and the message says "no results" instead of "adsh is now called X".
    renamed = json.dumps(
        {
            "hits": {
                "hits": [
                    {
                        "_id": "0000950170-24-012345:ex101.htm",
                        # EDGAR has renamed adsh to accession, hypothetically
                        "_source": {
                            "accession": "0000950170-24-012345",
                            "ciks": ["0000320123"],
                        },
                    }
                ]
            }
        }
    ).encode()
    report = run(
        client_for(
            {
                "search-index": Response(200, renamed),
                "index.json": Response(200, INDEX_BODY),
                "ex101.htm": Response(200, DOC_HTML),
            }
        )
    )
    step = steps(report)["_source carries the expected fields"]
    assert not step.ok
    assert "adsh" in step.detail
    assert "accession" in step.detail, "must show what IS there, not only what is missing"


def test_a_changed_id_format_is_caught():
    body = json.dumps(
        {"hits": {"hits": [{"_id": "no-colon", "_source": {"ciks": ["0000320123"]}}]}}
    ).encode()
    report = run(client_for({"search-index": Response(200, body)}))
    assert not steps(report)["_id is accession:filename"].ok


def test_a_changed_envelope_is_caught_before_anything_else():
    body = json.dumps({"results": []}).encode()
    report = run(client_for({"search-index": Response(200, body)}))
    step = steps(report)["response has hits.hits"]
    assert not step.ok
    assert "results" in step.detail


def test_a_document_that_will_not_download_is_reported_with_its_url():
    report = run(
        client_for(
            {
                "search-index": Response(200, search_body()),
                "index.json": Response(200, INDEX_BODY),
                "ex101.htm": Response(500, b""),
            }
        )
    )
    step = steps(report)["document downloads"]
    assert not step.ok
    assert "Archives/edgar/data" in step.fix


def test_the_paste_block_carries_structure_not_content():
    report = run(healthy())
    output = format_report(report, paste=True)
    assert "structure only" in output
    assert "adsh" in output
    assert "Borrower" not in output, "document text must never reach the paste block"


def test_a_clean_run_says_the_caveat_is_discharged():
    assert "caveat" in format_report(run(healthy()))


# -- sample selection ------------------------------------------------------------


def test_the_sample_prefers_an_agreement_over_an_amendment():
    # The first live run picked a second amendment, which has none of the structure the
    # segmenter looks for — and then reported the segmenter as broken.
    from covenant_evals.corpus.doctor import _pick_sample
    from covenant_evals.corpus.edgar import Hit

    amendment = Hit(
        accession="0001005229-20-000280",
        filename="cm-2ndamendmentexecuted.htm",
        cik="320123",
        company="Acme",
        form="8-K",
        filed="2020-01-01",
        file_type="EX-10.1",
        description="Second Amendment to Credit Agreement",
    )
    agreement = Hit(
        accession="0000950170-24-012345",
        filename="ex101creditagreement.htm",
        cik="320123",
        company="Acme",
        form="8-K",
        filed="2024-03-04",
        file_type="EX-10.1",
        description="Credit Agreement",
    )

    assert _pick_sample([amendment, agreement]) is agreement
    assert _pick_sample([agreement, amendment]) is agreement


def test_an_unreadable_document_is_a_warning_not_a_failure():
    # Structure that the segmenter cannot read is a fact about one document, not a broken
    # pipeline. Conflating the two teaches you to ignore the output.
    prose = (
        b"<html><body><p>" + b"Plain prose with no headings at all. " * 200 + b"</p></body></html>"
    )
    report = run(
        client_for(
            {
                "search-index": Response(200, search_body()),
                "index.json": Response(200, INDEX_BODY),
                "ex101.htm": Response(200, prose),
            }
        )
    )
    step = steps(report)["segmenter finds sections"]
    assert not step.ok
    assert step.level == "warn"
    assert report.ok, "warnings must not fail the run"
    assert "census" in report.observed, "an unreadable document must attach the diagnosis"
