"""The endpoint doctor, against servers that misbehave in each specific way.

A check that has never seen its own failure is a guess. Every check here is exercised
against an endpoint that breaks exactly the assumption it exists to test — a server that
answers nothing, one whose model will not call tools, one whose tool arguments are not JSON,
one that reports no usage.

The one that matters most is "model actually calls a tool". A small model that cannot drive
the suite produces a **zero violation rate**, which reads like a perfectly safe agent and is
nothing of the kind. Fifteen seconds here beats an hour of sweeping and a wrong conclusion.
"""

import json

import pytest

from control_evals.doctor import FAIL, PASS, WARN, run_checks, verdict
from control_evals.openai_compat import OpenAICompatClient, OpenAICompatError


def endpoint(*replies):
    """A transport that replays canned payloads; exceptions are raised as they come up."""
    queue = list(replies)

    def transport(url, headers, payload):
        reply = queue.pop(0) if queue else {"choices": [{"message": {"content": "ok"}}]}
        if isinstance(reply, Exception):
            raise reply
        return reply

    return OpenAICompatClient(base_url="http://localhost:11434/v1", transport=transport)


def text_reply(content="ready", prompt=42, output=3):
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": prompt, "completion_tokens": output},
    }


def tool_reply(name="get_balance", arguments="{}", finish="tool_calls"):
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                },
                "finish_reason": finish,
            }
        ],
        "usage": {"prompt_tokens": 90, "completion_tokens": 12},
    }


def status(checks, fragment):
    return next(c.status for c in checks if fragment in c.name)


def test_a_healthy_endpoint_passes_everything():
    checks = run_checks(endpoint(text_reply(), tool_reply()), "qwen2.5:1.5b")

    assert all(c.status == PASS for c in checks), [str(c) for c in checks]
    code, summary = verdict(checks)
    assert code == 0 and "Go ahead and sweep" in summary


def test_an_unreachable_endpoint_fails_fast_and_skips_the_rest():
    checks = run_checks(endpoint(OpenAICompatError("connection refused")), "m")

    assert checks[0].status == FAIL
    assert "connection refused" in checks[0].detail
    assert len(checks) == 2, "no point checking anything else"
    assert verdict(checks)[0] == 1


def test_a_model_that_will_not_call_tools_is_the_headline_failure():
    """A zero violation rate from a model that never acts looks like a safe agent."""
    checks = run_checks(endpoint(text_reply(), text_reply("I cannot do that")), "m")

    assert status(checks, "actually calls a tool") == FAIL
    detail = next(c.detail for c in checks if "actually calls a tool" in c.name)
    assert "violation rate will be zero for the wrong reason" in detail
    assert verdict(checks)[0] == 1


def test_malformed_tool_arguments_are_caught_here_rather_than_mid_sweep():
    checks = run_checks(endpoint(text_reply(), tool_reply(arguments="{not json")), "m")

    assert status(checks, "arguments parse") == FAIL
    assert status(checks, "actually calls a tool") == PASS, "it did call one, badly"


def test_calling_the_wrong_tool_name_is_caught():
    checks = run_checks(endpoint(text_reply(), tool_reply(name="check_balance")), "m")
    assert status(checks, "right name") == FAIL


def test_a_silent_model_warns_because_declining_needs_words():
    """Completion requires the agent to say something. A reply with no text fails that
    everywhere, and it is better to know before than to read it as poor judgement."""
    checks = run_checks(endpoint(text_reply(content=""), tool_reply()), "m")

    assert status(checks, "answers in text") == WARN
    assert verdict(checks)[0] == 0, "a warning is not a failure"


def test_missing_usage_warns_rather_than_fails():
    reply = text_reply()
    del reply["usage"]
    checks = run_checks(endpoint(reply, tool_reply()), "m")

    assert status(checks, "token usage") == WARN
    assert verdict(checks)[0] == 0


def test_a_server_that_says_stop_while_calling_a_tool_only_warns():
    """Common enough that the adapter handles it; still worth reporting.

    This check has to read the server's raw finish_reason. The adapter already rewrites
    "stop" to "tool_use" when tool blocks are present, so inspecting the translated value
    would confirm the adapter's own correction and never detect anything.
    """
    checks = run_checks(endpoint(text_reply(), tool_reply(finish="stop")), "m")

    assert status(checks, "turn is not over") == WARN
    assert verdict(checks)[0] == 0


def test_a_response_with_no_choices_reports_what_the_server_sent():
    checks = run_checks(endpoint({"error": {"message": "model not found"}}), "m")

    assert status(checks, "expected shape") == FAIL
    assert "model not found" in next(c.detail for c in checks if "expected shape" in c.name)


@pytest.mark.parametrize(
    ("statuses", "code"),
    [([PASS, PASS], 0), ([PASS, WARN], 0), ([PASS, FAIL], 1), ([FAIL, WARN], 1)],
)
def test_only_failures_change_the_exit_code(statuses, code):
    from control_evals.doctor import Check

    assert verdict([Check(f"c{i}", s) for i, s in enumerate(statuses)])[0] == code


def test_the_probe_tool_is_the_simplest_one_in_the_suite():
    """If a model cannot manage a no-argument tool, nothing in the suite will work."""
    from control_evals.doctor import PROBE_TOOL

    schema = PROBE_TOOL[0]["input_schema"]
    assert schema["properties"] == {} and schema["required"] == []
    assert json.dumps(PROBE_TOOL)  # serialisable, which is all the endpoint needs


# ---------------------------------------------------------------------------
# Whose fault was it — the model's, or this suite's?
#
# The tool-call check can tell you nothing happened. It cannot tell you why, and the two
# causes have opposite fixes: swap the model, or open openai_compat.py. LIMITATIONS.md §19
# is the standing warning that a mistranslation looks exactly like a model behaving badly.
# The separating question is whether *forcing* the call works.
# ---------------------------------------------------------------------------


def _fault(checks):
    return next(c for c in checks if "the model's doing" in c.name)


def test_forcing_the_call_working_acquits_the_adapter():
    """Tools arrived and were understood. The model simply does not reach for them."""
    checks = run_checks(
        endpoint(text_reply(), text_reply("The balance is fine."), tool_reply()), "m"
    )

    fault = _fault(checks)
    assert fault.status == WARN
    assert "not this suite's" in fault.name
    assert "Pick a bigger model" in fault.detail
    assert "nothing here needs fixing" in fault.detail


def test_forcing_the_call_failing_too_leaves_the_adapter_a_suspect():
    """The one case where the model is *not* the first thing to blame."""
    checks = run_checks(
        endpoint(text_reply(), text_reply("I cannot do that"), text_reply("Still no.")), "m"
    )

    fault = _fault(checks)
    assert fault.status == WARN
    assert "or this suite's?" in fault.name
    assert "not reaching it in a form this server acts on" in fault.detail


def test_the_prose_the_model_produced_instead_is_quoted_back():
    """Often the giveaway: a model that writes out the call in words understands the tools."""
    checks = run_checks(
        endpoint(text_reply(), text_reply("I would call get_balance here."), text_reply("no")), "m"
    )

    assert "I would call get_balance here." in _fault(checks).detail


def test_a_server_that_rejects_a_named_tool_choice_says_so_rather_than_guessing():
    """Some servers reject tool_choice outright. That is evidence about neither side."""
    checks = run_checks(
        endpoint(text_reply(), text_reply("nope"), OpenAICompatError("400: unsupported")),
        "m",
    )

    fault = _fault(checks)
    assert fault.status == WARN
    assert "could not tell" in fault.detail
    assert "says nothing either way" in fault.detail


def test_the_diagnostic_never_runs_when_the_tool_call_worked():
    """One extra request, only ever on the failure path."""
    sent = []

    def transport(url, headers, payload):
        sent.append(payload)
        return text_reply() if len(sent) == 1 else tool_reply()

    checks = run_checks(
        OpenAICompatClient(base_url="http://localhost:11434/v1", transport=transport), "m"
    )

    assert len(sent) == 2, "a healthy endpoint is asked twice, never three times"
    assert not [c for c in checks if "the model's doing" in c.name]


def test_the_forced_probe_is_the_same_request_with_only_tool_choice_changed():
    """If the forced probe differed in any other way, its result would prove nothing."""
    from control_evals.doctor import probe_payload

    auto = probe_payload("m")
    forced = probe_payload("m", {"type": "function", "function": {"name": "get_balance"}})

    assert auto["tool_choice"] == "auto"
    assert forced["tool_choice"]["function"]["name"] == "get_balance"
    assert {k: v for k, v in auto.items() if k != "tool_choice"} == {
        k: v for k, v in forced.items() if k != "tool_choice"
    }


def test_show_request_prints_the_body_that_was_actually_sent():
    """A diagnostic that prints a different request than it sent is worse than none."""
    from control_evals.doctor import probe_payload

    sent = []

    def transport(url, headers, payload):
        sent.append(payload)
        return text_reply() if len(sent) == 1 else tool_reply()

    run_checks(OpenAICompatClient(base_url="http://localhost:11434/v1", transport=transport), "m")

    assert sent[1] == probe_payload("m")
    assert json.loads(json.dumps(probe_payload("m"))) == probe_payload("m"), "must be printable"


# ---------------------------------------------------------------------------
# The first request fails for three different reasons
#
# All three used to be reported as "endpoint reachable", which is the wrong thing to check
# in two of them: an uninstalled model means the endpoint answered perfectly, and a slow one
# means it accepted the request. The fix is `ollama pull`, a smaller model, and `ollama
# serve` respectively — three different places to look.
# ---------------------------------------------------------------------------


def test_an_uninstalled_model_is_named_as_such_not_as_an_unreachable_endpoint():
    detail = (
        "HTTP 404 from http://localhost:11434/v1/chat/completions: model 'llama3.2:3b' not found"
    )
    checks = run_checks(endpoint(OpenAICompatError(detail)), "llama3.2:3b")

    assert "is installed" in checks[0].name
    assert "llama3.2:3b" in checks[0].name
    assert "ollama pull llama3.2:3b" in checks[0].detail
    assert "the server is running and answered" in checks[0].detail
    assert verdict(checks)[0] == 1


def test_a_slow_first_reply_is_a_deadline_failure_not_an_unreachable_endpoint():
    checks = run_checks(
        endpoint(OpenAICompatError("no response from http://x/v1 within 180s. The server ...")),
        "qwen2.5:7b",
    )

    assert checks[0].name == "answers within the deadline"
    assert verdict(checks)[0] == 1


def test_a_genuinely_dead_endpoint_still_says_so():
    """The label must still be right in the case it was always right for."""
    checks = run_checks(endpoint(OpenAICompatError("could not reach http://x: [Errno 111]")), "m")

    assert checks[0].name == "endpoint reachable"


def test_another_models_404_is_not_read_as_this_model_missing():
    """The name has to match, or an unrelated 404 gets a misleading remedy attached."""
    detail = "HTTP 404 from http://x/v1: model 'some-other-model' not found"
    checks = run_checks(endpoint(OpenAICompatError(detail)), "llama3.2:3b")

    assert checks[0].name == "endpoint reachable", (
        "no ollama pull suggestion for someone else's 404"
    )


def test_a_403_is_not_reported_as_an_unreachable_endpoint():
    """The server answered. It answered "no".

    Reporting that as "endpoint reachable [FAIL]" sends the reader to check their URL when
    the URL was never the problem — the same mislabelling as the model-not-installed and
    the too-slow cases, and the fourth instance on this path.
    """
    from control_evals.doctor import _first_failure
    from control_evals.openai_compat import OpenAICompatError

    exc = OpenAICompatError(
        "HTTP 403 from https://api.groq.com/openai/v1/chat/completions: error code: 1010"
    )
    check = _first_failure(exc, "llama-3.3-70b-versatile")

    assert check.name != "endpoint reachable"
    assert "1010" in check.detail
    assert "signature" in check.detail


def test_a_401_points_at_the_key_and_not_the_url():
    from control_evals.doctor import _first_failure
    from control_evals.openai_compat import OpenAICompatError

    check = _first_failure(OpenAICompatError("HTTP 401 from https://x/v1: unauthorized"), "m")

    assert "key" in check.name
    assert "--api-key-env" in check.detail


def test_a_plain_403_without_cloudflare_blames_entitlement_not_the_client():
    from control_evals.doctor import _first_failure
    from control_evals.openai_compat import OpenAICompatError

    check = _first_failure(OpenAICompatError("HTTP 403 from https://x/v1: forbidden"), "m")

    assert "1010" not in check.detail
    assert "entitled" in check.detail
