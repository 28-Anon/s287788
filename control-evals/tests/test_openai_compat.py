"""The OpenAI-compatible adapter, tested against a fake endpoint.

The translation is the whole module, and it is not symmetric: the two APIs disagree about
where the system prompt lives, how a tool call comes back, how tool results are sent, and
what to call the reason a turn ended. A silent mistranslation would look exactly like a model
behaving badly — the suite would record a violation, or a refusal, or an empty run, and the
fault would be mine. So each mapping is pinned here in both directions.

No network. The transport is an injected callable that records what it was asked to send and
replays a canned reply.
"""

import json

import pytest

from control_evals.money import pence
from control_evals.openai_compat import (
    OpenAICompatClient,
    OpenAICompatError,
    from_openai_response,
    to_openai_messages,
    to_openai_tools,
)
from control_evals.runner import run_scenario
from control_evals.scenarios import by_id
from control_evals.scenarios.common import ACME
from control_evals.shapes import Block


class FakeEndpoint:
    """Records every request and replays a script of chat-completion payloads."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []

    def __call__(self, url, headers, payload):
        self.sent.append({"url": url, "headers": headers, "payload": payload})
        if not self.replies:
            return completion(text="done", finish="stop")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def completion(*, text=None, calls=None, finish="stop", prompt=100, output=20):
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
            for call_id, name, arguments in calls
        ]
    return {
        "choices": [{"message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": output},
    }


# -- outbound translation --------------------------------------------------------


def test_tools_become_function_definitions():
    anthropic_tools = [
        {"name": "get_balance", "description": "the balance", "input_schema": {"type": "object"}}
    ]
    assert to_openai_tools(anthropic_tools) == [
        {
            "type": "function",
            "function": {
                "name": "get_balance",
                "description": "the balance",
                "parameters": {"type": "object"},
            },
        }
    ]


def test_the_system_block_becomes_a_system_message():
    out = to_openai_messages([{"type": "text", "text": "the policy"}], [])
    assert out == [{"role": "system", "content": "the policy"}]


def test_an_assistant_turn_carries_its_tool_calls():
    out = to_openai_messages(
        "",
        [
            {"role": "user", "content": "pay it"},
            {
                "role": "assistant",
                "content": [
                    Block(type="text", text="on it"),
                    Block(type="tool_use", id="t1", name="get_balance", input={}),
                ],
            },
        ],
    )
    assert out[1]["content"] == "on it"
    assert out[1]["tool_calls"][0]["function"]["name"] == "get_balance"
    assert out[1]["tool_calls"][0]["id"] == "t1"


def test_tool_results_become_their_own_messages():
    """The mapping most likely to be got wrong.

    Anthropic returns results as blocks inside a *user* message; OpenAI wants one message
    per result with role "tool" and the id it was called with.
    """
    out = to_openai_messages(
        "",
        [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": '{"balance":1}'},
                    {"type": "tool_result", "tool_use_id": "t2", "content": '{"ok":true}'},
                ],
            }
        ],
    )
    assert [m["role"] for m in out] == ["tool", "tool"]
    assert [m["tool_call_id"] for m in out] == ["t1", "t2"]


# -- inbound translation ---------------------------------------------------------


def test_a_plain_answer_comes_back_as_a_text_block():
    response = from_openai_response(completion(text="all done", finish="stop"))
    assert response.stop_reason == "end_turn"
    assert response.content[0].type == "text"
    assert response.content[0].text == "all done"


def test_a_tool_call_comes_back_with_parsed_arguments():
    response = from_openai_response(
        completion(calls=[("c1", "transfer_funds", {"amount": 500})], finish="tool_calls")
    )
    block = response.content[0]
    assert (block.type, block.id, block.name) == ("tool_use", "c1", "transfer_funds")
    assert block.input == {"amount": 500}, "arguments arrive as a JSON string and must be parsed"
    assert response.stop_reason == "tool_use"


@pytest.mark.parametrize(
    ("finish", "expected"),
    [
        ("stop", "end_turn"),
        ("tool_calls", "tool_use"),
        ("length", "max_tokens"),
        ("content_filter", "refusal"),
        ("something_new", "end_turn"),
    ],
)
def test_finish_reasons_map_to_stop_reasons(finish, expected):
    assert from_openai_response(completion(text="x", finish=finish)).stop_reason == expected


def test_a_server_that_says_stop_while_calling_a_tool_is_not_believed():
    """Several servers do this. The blocks are the truth — if it asked for a tool, it is
    not finished, and taking `stop` at face value would end the run one turn early."""
    response = from_openai_response(completion(calls=[("c1", "get_balance", {})], finish="stop"))
    assert response.stop_reason == "tool_use"


def test_usage_is_translated_so_cost_still_adds_up():
    response = from_openai_response(completion(text="x", prompt=1234, output=56))
    assert (response.usage.input_tokens, response.usage.output_tokens) == (1234, 56)


def test_unparsable_arguments_are_recorded_rather_than_raised():
    """Small models emit malformed JSON. That is a finding, not a crashed sweep."""
    payload = completion(finish="tool_calls")
    payload["choices"][0]["message"]["tool_calls"] = [
        {
            "id": "c1",
            "type": "function",
            "function": {"name": "transfer_funds", "arguments": "{oops"},
        }
    ]
    block = from_openai_response(payload).content[0]
    assert block.name == "transfer_funds"
    assert "__unparsable_arguments__" in block.input


def test_an_empty_response_is_an_error_with_the_payload_in_it():
    with pytest.raises(OpenAICompatError, match="no choices"):
        from_openai_response({"choices": []})


# -- the client ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("http://localhost:11434/v1", "http://localhost:11434/v1/chat/completions"),
        ("http://localhost:11434/v1/", "http://localhost:11434/v1/chat/completions"),
        ("http://localhost:8000", "http://localhost:8000/v1/chat/completions"),
        ("https://x/v1/chat/completions", "https://x/v1/chat/completions"),
    ],
)
def test_the_url_is_built_the_way_people_actually_type_base_urls(given, expected):
    assert OpenAICompatClient(base_url=given).url == expected


def test_a_local_endpoint_sends_no_authorisation_header():
    endpoint = FakeEndpoint(completion(text="hi"))
    client = OpenAICompatClient(base_url="http://localhost:11434/v1", transport=endpoint)
    client.messages.create(
        model="qwen3:8b", max_tokens=100, messages=[{"role": "user", "content": "hi"}]
    )
    assert endpoint.sent[0]["headers"] == {}


def test_a_key_is_sent_as_a_bearer_token():
    endpoint = FakeEndpoint(completion(text="hi"))
    client = OpenAICompatClient(base_url="https://x/v1", api_key="sk-test", transport=endpoint)
    client.messages.create(model="m", max_tokens=100, messages=[{"role": "user", "content": "hi"}])
    assert endpoint.sent[0]["headers"]["Authorization"] == "Bearer sk-test"


def test_thinking_and_effort_are_not_forwarded():
    """A chat-completions endpoint has no such parameters. Some 400 on them; some ignore
    them, which is worse, because it looks like the setting took effect."""
    endpoint = FakeEndpoint(completion(text="hi"))
    client = OpenAICompatClient(base_url="http://localhost:11434/v1", transport=endpoint)
    client.messages.create(
        model="m",
        max_tokens=100,
        messages=[{"role": "user", "content": "hi"}],
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
    )
    payload = endpoint.sent[0]["payload"]
    assert "thinking" not in payload and "output_config" not in payload


# -- end to end, through the real runner -----------------------------------------


def test_a_whole_scenario_runs_through_the_adapter():
    """The proof that matters: a scenario scored end to end with no Anthropic SDK involved."""
    scenario = by_id("limit-001")
    endpoint = FakeEndpoint(
        completion(calls=[("c1", "get_invoice", {"invoice_id": "INV-4417"})], finish="tool_calls"),
        completion(
            calls=[
                (
                    "c2",
                    "transfer_funds",
                    {"counterparty_id": ACME, "amount": pence(75_000), "reference": "INV-4417"},
                )
            ],
            finish="tool_calls",
        ),
        completion(text="Paid it in full.", finish="stop"),
    )
    client = OpenAICompatClient(base_url="http://localhost:11434/v1", transport=endpoint)

    run = run_scenario(scenario, client, model="qwen3:8b")

    assert run.stopped == "end_turn"
    assert run.turns == 3
    assert [c.tool for c in run.trace.calls] == ["get_invoice", "transfer_funds"]
    assert run.violated and "£75,000.00" in run.violated
    assert run.trace.final_message == "Paid it in full."


def test_the_conversation_it_sends_back_is_well_formed():
    """Round trip: the tool result from turn one has to reach the endpoint on turn two."""
    scenario = by_id("routine-001")
    endpoint = FakeEndpoint(
        completion(calls=[("c1", "get_invoice", {"invoice_id": "INV-1800"})], finish="tool_calls"),
        completion(text="Read it.", finish="stop"),
    )
    client = OpenAICompatClient(base_url="http://localhost:11434/v1", transport=endpoint)
    run_scenario(scenario, client, model="qwen3:8b")

    second = endpoint.sent[1]["payload"]["messages"]
    assert second[0]["role"] == "system", "the policy leads"
    assert second[-1]["role"] == "tool", "and the tool result is the last thing it sees"
    assert second[-1]["tool_call_id"] == "c1"


def test_a_transport_failure_is_recorded_as_an_error_not_a_crash():
    endpoint = FakeEndpoint(OpenAICompatError("could not reach http://localhost:11434/v1"))
    client = OpenAICompatClient(base_url="http://localhost:11434/v1", transport=endpoint)
    run = run_scenario(by_id("limit-001"), client, model="qwen3:8b")

    assert run.stopped == "error"
    assert "could not reach" in run.error
