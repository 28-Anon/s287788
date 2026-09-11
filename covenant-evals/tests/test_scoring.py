"""Tests for the baseline system and the grounded-accuracy scorer.

The client is injected, so nothing here calls a model or costs anything.
"""

from dataclasses import dataclass, field

import pytest

from covenant_evals.harness import fixture
from covenant_evals.harness.scorers import answers_match, grade, summarise
from covenant_evals.schema import validate
from covenant_evals.systems import BaselineSystem

DOC = fixture.DOCUMENT
ITEMS = {item.id: item for item in fixture.items()}


# -- the fixture itself has to be sound ------------------------------------------


def test_every_fixture_item_is_valid():
    for item in fixture.items():
        assert validate(item) == [], item.id


def test_every_fixture_citation_is_verbatim_and_in_its_section():
    from covenant_evals.corpus.sections import segment

    segmentation = segment(DOC)
    for item in fixture.items():
        if item.gold_span is None:
            continue
        start, end = item.gold_span
        assert DOC[start:end] == item.gold_citation, item.id
        section = segmentation.find(item.section)
        assert section is not None, item.section
        assert section.start <= start < section.end, item.id


# -- answer matching -------------------------------------------------------------


@pytest.mark.parametrize("given", ["false", "False", "FALSE", "no", "n", "false."])
def test_boolean_answers_are_matched_regardless_of_spelling(given):
    assert answers_match(given, ITEMS["fixture-001"])


@pytest.mark.parametrize("given", ["true", "yes", "maybe", "", "it depends"])
def test_a_wrong_or_unparseable_boolean_does_not_match(given):
    assert not answers_match(given, ITEMS["fixture-001"])


@pytest.mark.parametrize("given", ["35000000", "35,000,000", "$35,000,000", " 35000000.0 "])
def test_numbers_are_matched_through_formatting(given):
    assert answers_match(given, ITEMS["fixture-002"])


def test_a_different_number_does_not_match():
    # Forgiving about format, strict about content.
    assert not answers_match("50,000,000", ITEMS["fixture-002"])
    assert not answers_match("35000001", ITEMS["fixture-002"])


def test_a_ratio_matches_on_value_not_text():
    assert answers_match("3.5", ITEMS["fixture-003"])
    assert answers_match("3.50", ITEMS["fixture-003"])
    assert not answers_match("4.00", ITEMS["fixture-003"])


# -- grading ---------------------------------------------------------------------


def test_a_correct_answer_with_a_real_citation_is_grounded():
    item = ITEMS["fixture-001"]
    result = grade(item, "false", item.gold_citation, DOC)
    assert result.grounded
    assert result.answer_correct and result.citation_verbatim and result.citation_in_section


def test_a_right_answer_with_an_invented_citation_scores_zero():
    # The single opinion this project has. Nobody can act on an unverifiable answer, so
    # being right by luck earns nothing.
    item = ITEMS["fixture-001"]
    result = grade(item, "false", "the Borrower shall not exceed the applicable basket", DOC)

    assert result.answer_correct
    assert not result.citation_verbatim
    assert not result.grounded
    assert "INVENTED CITATION" in result.detail


def test_a_real_quote_from_the_wrong_section_is_not_grounded():
    item = ITEMS["fixture-001"]
    result = grade(item, "false", "except Permitted Liens", DOC)

    assert result.citation_verbatim
    assert not result.citation_in_section
    assert not result.grounded
    assert "outside section" in result.detail


def test_a_wrong_answer_with_a_perfect_citation_is_not_grounded():
    item = ITEMS["fixture-001"]
    result = grade(item, "true", item.gold_citation, DOC)
    assert result.citation_verbatim and result.citation_in_section
    assert not result.grounded


def test_no_quote_at_all_fails_with_a_clear_reason():
    result = grade(ITEMS["fixture-001"], "false", "", DOC)
    assert not result.grounded
    assert "no quote given" in result.detail


def test_offering_no_citation_is_labelled_differently_from_inventing_one():
    # The taxonomy will want these apart: a system that fabricates support is not the same
    # as one that offers none, and they need different fixes.
    silent = grade(ITEMS["fixture-001"], "false", "", DOC)
    fabricated = grade(ITEMS["fixture-001"], "false", "the Borrower may borrow freely", DOC)

    assert "NO CITATION" in silent.detail
    assert "INVENTED CITATION" in fabricated.detail


def test_a_citation_matches_across_the_line_break_it_crosses():
    # The stored citation contains a newline; a system quoting it with a space must match.
    item = ITEMS["fixture-001"]
    flattened = " ".join(item.gold_citation.split())
    assert grade(item, "false", flattened, DOC).grounded


# -- abstention ------------------------------------------------------------------


def test_abstaining_correctly_is_grounded():
    result = grade(ITEMS["fixture-004"], "INSUFFICIENT_INFORMATION", "", DOC)
    assert result.grounded
    assert result.abstained
    assert not result.wrong_when_should_abstain


def test_inventing_an_answer_where_the_document_is_silent_is_the_worst_failure():
    result = grade(ITEMS["fixture-004"], "2% above the applicable rate", "default interest", DOC)
    assert not result.grounded
    assert result.wrong_when_should_abstain
    assert "does not say" in result.detail


def test_abstaining_on_an_answerable_question_is_simply_wrong():
    result = grade(ITEMS["fixture-001"], "INSUFFICIENT_INFORMATION", "", DOC)
    assert not result.answer_correct
    assert not result.grounded


# -- aggregation -----------------------------------------------------------------


def test_summarise_separates_answer_accuracy_from_grounded_accuracy():
    # The gap between these two numbers is the finding this project exists to produce.
    grades = [
        grade(ITEMS["fixture-001"], "false", ITEMS["fixture-001"].gold_citation, DOC),
        grade(ITEMS["fixture-002"], "35000000", ITEMS["fixture-002"].gold_citation, DOC),
        grade(ITEMS["fixture-003"], "3.50", "a quote that is not in the document", DOC),
        grade(ITEMS["fixture-004"], "2% per annum", "", DOC),
    ]
    totals = summarise(grades)

    assert totals["answer_accuracy"] == 0.75
    assert totals["grounded_accuracy"] == 0.5
    assert totals["wrong_when_should_abstain"] == 1.0


def test_summarise_of_nothing_is_not_a_crash():
    assert summarise([]) == {"items": 0}


# -- the baseline system ---------------------------------------------------------


@dataclass
class FakeUsage:
    input_tokens: int = 900
    output_tokens: int = 60
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class FakeBlock:
    type: str
    input: dict


@dataclass
class FakeResponse:
    content: list
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeMessages:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(content=[FakeBlock("tool_use", self.payload)])


class FakeClient:
    def __init__(self, payload):
        self.messages = FakeMessages(payload)


def test_the_baseline_returns_the_answer_and_the_quote_separately():
    client = FakeClient({"answer": "false", "quote": "not to exceed", "reasoning": "capped"})
    answer = BaselineSystem(client).answer(DOC, "May the Borrower incur $50m?")

    assert answer.answer == "false"
    assert answer.quote == "not to exceed"
    assert answer.usage.input_tokens == 900
    assert answer.latency_s >= 0


def test_the_document_is_sent_in_a_cached_block():
    # Ten questions about one agreement should be one cache write and nine reads.
    client = FakeClient({"answer": "false", "quote": "x", "reasoning": "y"})
    BaselineSystem(client).answer(DOC, "question?")

    content = client.messages.calls[0]["messages"][0]["content"]
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert "<agreement>" in content[0]["text"]


def test_caching_can_be_turned_off():
    client = FakeClient({"answer": "false", "quote": "x", "reasoning": "y"})
    BaselineSystem(client, cache_document=False).answer(DOC, "question?")
    assert "cache_control" not in client.messages.calls[0]["messages"][0]["content"][0]


def test_the_answer_tool_is_forced_so_the_shape_is_guaranteed():
    client = FakeClient({"answer": "false", "quote": "x", "reasoning": "y"})
    BaselineSystem(client).answer(DOC, "question?")

    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "record_answer"}
    assert call["tools"][0]["strict"] is True
    assert call["tools"][0]["input_schema"]["additionalProperties"] is False


def test_abstention_is_detected():
    client = FakeClient({"answer": "INSUFFICIENT_INFORMATION", "quote": "", "reasoning": "silent"})
    assert BaselineSystem(client).answer(DOC, "what rate?").abstained


def test_a_response_with_no_tool_call_does_not_crash():
    class Empty(FakeClient):
        def __init__(self):
            self.messages = FakeMessages({})
            self.messages.create = lambda **kw: FakeResponse(content=[])

    answer = BaselineSystem(Empty()).answer(DOC, "question?")
    assert answer.answer == ""
    assert not answer.abstained
