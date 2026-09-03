"""Tests for the manifest and the fetch orchestration."""

import json

import pytest

from covenant_evals.corpus.edgar import EdgarClient, RateLimiter, Response
from covenant_evals.corpus.fetch import fetch_all, fetch_one
from covenant_evals.corpus.manifest import Agreement, Manifest
from covenant_evals.corpus.normalise import NORMALISER_VERSION

GOOD_UA = "Ada Lovelace ada@analytical-engine.org"
DOC_HTML = b"<html><body><p>Section 7.02(b). Not to exceed $35,000,000.</p></body></html>"


def make_agreement(**overrides) -> Agreement:
    defaults = dict(
        accession="0000950170-24-012345",
        filename="ex101.htm",
        cik="320123",
        company="Acme Corp",
        form="EX-10.1",
        filed="2024-03-04",
    )
    defaults.update(overrides)
    return Agreement(**defaults)


def make_client(body=DOC_HTML, status=200):
    calls = []

    def transport(url, headers):
        calls.append(url)
        return Response(status, body)

    client = EdgarClient(
        GOOD_UA,
        transport=transport,
        rate_limiter=RateLimiter(per_second=1000.0, sleep=lambda _: None),
        sleep=lambda _: None,
    )
    return client, calls


# -- manifest --------------------------------------------------------------------


def test_manifest_round_trips(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = Manifest()
    manifest.add(make_agreement(note="sponsor-backed leveraged loan"))
    manifest.save(path)

    reloaded = Manifest.load(path)
    assert len(reloaded.agreements) == 1
    assert reloaded.agreements[0].note == "sponsor-backed leveraged loan"


def test_manifest_load_of_a_missing_file_is_empty(tmp_path):
    assert Manifest.load(tmp_path / "nope.json").agreements == []


def test_adding_the_same_document_twice_is_a_no_op():
    manifest = Manifest()
    assert manifest.add(make_agreement()) is True
    assert manifest.add(make_agreement()) is False
    assert len(manifest.agreements) == 1


def test_manifest_is_written_sorted_for_readable_diffs(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = Manifest()
    manifest.add(make_agreement(accession="0000950170-24-999999", filename="z.htm"))
    manifest.add(make_agreement(accession="0000950170-24-000001", filename="a.htm"))
    manifest.save(path)

    written = json.loads(path.read_text())
    refs = [f"{a['accession']}:{a['filename']}" for a in written["agreements"]]
    assert refs == sorted(refs)


def test_unknown_fields_in_an_old_manifest_are_ignored(tmp_path):
    # Forward compatibility: a manifest written by a later version should still load.
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "agreements": [
                    {
                        "accession": "0000950170-24-012345",
                        "filename": "ex101.htm",
                        "cik": "320123",
                        "company": "Acme",
                        "form": "EX-10.1",
                        "filed": "2024-03-04",
                        "some_future_field": "ignored",
                    }
                ],
            }
        )
    )
    assert len(Manifest.load(path).agreements) == 1


def test_pending_and_stale(tmp_path):
    manifest = Manifest()
    manifest.add(make_agreement(filename="pending.htm"))
    manifest.add(make_agreement(filename="old.htm", text_sha256="a" * 64, normaliser_version=0))
    manifest.add(
        make_agreement(
            filename="current.htm", text_sha256="b" * 64, normaliser_version=NORMALISER_VERSION
        )
    )

    assert [a.filename for a in manifest.pending()] == ["pending.htm"]
    assert [a.filename for a in manifest.stale(NORMALISER_VERSION)] == ["old.htm"]


# -- fetching --------------------------------------------------------------------


def test_fetch_downloads_normalises_and_hashes(tmp_path):
    client, calls = make_client()
    agreement = make_agreement()

    result = fetch_one(client, agreement, cache_dir=tmp_path)

    assert result.status == "fetched"
    assert len(calls) == 1
    assert agreement.is_fetched
    assert len(agreement.text_sha256) == 64
    assert agreement.normaliser_version == NORMALISER_VERSION
    assert agreement.char_count > 0
    assert "Section 7.02(b)" in agreement.text_path(tmp_path).read_text()


def test_fetching_twice_does_not_hit_the_network_again(tmp_path):
    client, calls = make_client()
    agreement = make_agreement()

    fetch_one(client, agreement, cache_dir=tmp_path)
    result = fetch_one(client, agreement, cache_dir=tmp_path)

    assert result.status == "cached"
    assert len(calls) == 1, "the second fetch must be served from disk"


def test_changed_document_is_reported_as_a_conflict_not_overwritten(tmp_path):
    client, _ = make_client()
    agreement = make_agreement()
    fetch_one(client, agreement, cache_dir=tmp_path)
    original_hash = agreement.text_sha256

    # The filing is replaced on EDGAR and the cache is cleared.
    agreement.cache_path(tmp_path).unlink()
    replaced, _ = make_client(b"<p>Section 7.02(b). Not to exceed $50,000,000.</p>")
    result = fetch_one(client=replaced, agreement=agreement, cache_dir=tmp_path)

    assert result.status == "conflict"
    assert "re-checking" in result.detail
    assert agreement.text_sha256 == original_hash, "the recorded hash must not be silently updated"


def test_force_re_fetches_and_updates_the_hash(tmp_path):
    client, _ = make_client()
    agreement = make_agreement()
    fetch_one(client, agreement, cache_dir=tmp_path)
    original = agreement.text_sha256

    replaced, calls = make_client(b"<p>Section 7.02(b). Not to exceed $50,000,000.</p>")
    result = fetch_one(replaced, agreement, cache_dir=tmp_path, force=True)

    assert result.status == "fetched"
    assert agreement.text_sha256 != original
    assert len(calls) == 1


def test_one_failing_document_does_not_abort_the_run(tmp_path):
    def transport(url, headers):
        if "bad.htm" in url:
            return Response(500, b"")
        return Response(200, DOC_HTML)

    client = EdgarClient(
        GOOD_UA,
        transport=transport,
        rate_limiter=RateLimiter(per_second=1000.0, sleep=lambda _: None),
        sleep=lambda _: None,
    )

    manifest = Manifest()
    manifest.add(make_agreement(filename="good.htm"))
    manifest.add(make_agreement(filename="bad.htm"))

    results = fetch_all(client, manifest, cache_dir=tmp_path)
    by_status = {r.status for r in results}

    assert by_status == {"fetched", "failed"}
    assert any(a.is_fetched for a in manifest.agreements)


def test_hash_recorded_matches_the_text_on_disk(tmp_path):
    from covenant_evals.corpus.normalise import sha256_text

    client, _ = make_client()
    agreement = make_agreement()
    fetch_one(client, agreement, cache_dir=tmp_path)

    on_disk = agreement.text_path(tmp_path).read_text(encoding="utf-8")
    assert sha256_text(on_disk) == agreement.text_sha256


@pytest.mark.parametrize("status", [403, 404, 500])
def test_failures_are_returned_as_results_not_raised(tmp_path, status):
    client, _ = make_client(b"", status=status)
    result = fetch_one(client, make_agreement(), cache_dir=tmp_path)
    assert result.status == "failed"
    assert result.detail


# -- governing law ---------------------------------------------------------------


def test_governing_law_is_recorded_and_survives_a_round_trip(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = Manifest()
    manifest.add(make_agreement(filename="ny.htm", governing_law="NY"))
    manifest.add(make_agreement(filename="eng.htm", governing_law="English"))
    manifest.save(path)

    reloaded = Manifest.load(path)
    laws = {a.filename: a.governing_law for a in reloaded.agreements}
    assert laws == {"ny.htm": "NY", "eng.htm": "English"}


def test_governing_law_defaults_to_unchecked_rather_than_assumed():
    # An unchecked document must never be silently counted as NY law just because it was
    # filed with the SEC. Where it was filed and which law governs it are different facts.
    assert make_agreement().governing_law == ""


def test_agreement_from_hit_carries_governing_law():
    from covenant_evals.corpus.edgar import Hit
    from covenant_evals.corpus.fetch import agreement_from_hit

    hit = Hit(
        accession="0000950170-24-012345",
        filename="ex101.htm",
        cik="320123",
        company="Acme",
        form="8-K",
        filed="2024-03-04",
    )
    agreement = agreement_from_hit(hit, note="LMA-style", governing_law="English")
    assert agreement.governing_law == "English"
    assert agreement.note == "LMA-style"
