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
