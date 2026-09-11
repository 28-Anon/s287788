"""Tests for spend tracking.

The arithmetic here is worth checking properly: a budget that is quietly wrong is worse
than no budget, because you stop looking at it.
"""

import pytest

from covenant_evals.budget import Usage, cache_hit_rate, cost_usd, record, summary


def test_plain_input_and_output_cost():
    # 1,000 input at $5/M = $0.005; 500 output at $25/M = $0.0125
    usage = Usage(input_tokens=1000, output_tokens=500)
    assert cost_usd("claude-opus-5", usage) == pytest.approx(0.0175)


def test_cache_reads_cost_a_tenth_of_normal_input():
    cached = Usage(cache_read_input_tokens=10_000)
    uncached = Usage(input_tokens=10_000)
    assert cost_usd("claude-opus-5", cached) == pytest.approx(
        cost_usd("claude-opus-5", uncached) * 0.1
    )


def test_full_call_with_cache_writes_and_reads():
    usage = Usage(
        input_tokens=1000,
        output_tokens=500,
        cache_read_input_tokens=10_000,
        cache_creation_input_tokens=2000,
    )
    # 0.005 + 0.0125 + 0.005 + 0.0125
    assert cost_usd("claude-opus-5", usage) == pytest.approx(0.035)


def test_cheaper_models_cost_less_for_identical_usage():
    usage = Usage(input_tokens=100_000, output_tokens=2000)
    opus = cost_usd("claude-opus-5", usage)
    sonnet = cost_usd("claude-sonnet-5", usage)
    haiku = cost_usd("claude-haiku-4-5", usage)
    assert opus > sonnet > haiku


def test_unknown_model_raises_rather_than_pricing_at_zero():
    with pytest.raises(KeyError):
        cost_usd("claude-imaginary-9", Usage(input_tokens=100))


def test_cache_hit_rate():
    assert cache_hit_rate(Usage(input_tokens=1000, cache_read_input_tokens=9000)) == 0.9
    assert cache_hit_rate(Usage()) == 0.0


def test_record_then_summarise(tmp_path):
    log = tmp_path / "spend.jsonl"
    record("claude-opus-5", Usage(input_tokens=1000, output_tokens=500), note="smoke", log=log)
    record("claude-haiku-4-5", Usage(input_tokens=1000), log=log)

    totals = summary(log)
    assert totals["calls"] == 2
    assert totals["by_model"]["claude-opus-5"]["calls"] == 1
    assert totals["total_usd"] == pytest.approx(0.0185, abs=1e-6)


def test_summary_of_a_missing_log_is_zero_not_a_crash(tmp_path):
    assert summary(tmp_path / "nothing.jsonl")["calls"] == 0
