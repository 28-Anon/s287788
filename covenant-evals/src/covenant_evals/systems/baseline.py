"""The simplest thing that could work: one call, whole document in context.

Deliberately unsophisticated. The point of a baseline is to be the number every cleverer
system has to beat, so it should be the obvious approach done competently and no more.

Two design decisions worth stating:

**A forced tool call, not free text.** The system must return an answer *and* the verbatim
text that justifies it, as separate fields. Parsing those out of prose is a source of
scoring error that has nothing to do with the model's actual competence, and `strict: true`
means the arguments are schema-valid or the call fails.

**The document goes in a cached prefix.** Ten questions about one agreement is one cache
write and nine reads. Ordering work by document rather than by question is the difference
between a $16 run and an $80 one, and it costs one line here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..budget import Usage

#: The model answers by calling this. `strict` guarantees the arguments validate.
ANSWER_TOOL: dict[str, Any] = {
    "name": "record_answer",
    "description": (
        "Record your answer to the question about the credit agreement, together with the "
        "verbatim text from the agreement that proves it."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer", "quote", "reasoning"],
        "properties": {
            "answer": {
                "type": "string",
                "description": (
                    "The answer itself and nothing else. 'true' or 'false' for a yes/no "
                    "question; a bare number for a numeric one; "
                    "'INSUFFICIENT_INFORMATION' if the agreement does not answer it."
                ),
            },
            "quote": {
                "type": "string",
                "description": (
                    "Text copied EXACTLY from the agreement that proves the answer. It "
                    "must appear verbatim in the document. Leave empty only when the "
                    "answer is INSUFFICIENT_INFORMATION."
                ),
            },
            "reasoning": {
                "type": "string",
                "description": "One or two sentences on why the quote settles the question.",
            },
        },
    },
}

SYSTEM_PROMPT = """You answer questions about credit agreements for a credit committee.

Two rules, and the second matters as much as the first:

1. Answer only from the agreement in front of you. Not from what is usual in the market,
   not from what a similar deal would say.
2. Every answer must be supported by text copied EXACTLY from the agreement. If you cannot
   find text that settles the question, answer INSUFFICIENT_INFORMATION. An answer with an
   invented or approximate quote is worse than no answer, because nobody can check it.

Watch for the things that make these documents hard: defined terms that point at other
defined terms, caps expressed as the greater of a fixed amount and a formula, and
prohibitions whose exceptions reverse them."""


@dataclass
class Answer:
    """What a system returned, before anything has been scored."""

    answer: str
    quote: str
    reasoning: str
    usage: Usage
    model: str
    latency_s: float
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def abstained(self) -> bool:
        return self.answer.strip().upper() == "INSUFFICIENT_INFORMATION"


class BaselineSystem:
    """One API call, whole document in a cached prefix.

    The client is injected, so every test runs offline against a fake.
    """

    name = "baseline"

    def __init__(
        self,
        client: Any,
        *,
        model: str = "claude-opus-5",
        max_tokens: int = 2048,
        cache_document: bool = True,
    ) -> None:
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.cache_document = cache_document

    def answer(self, document: str, question: str, *, section: str = "") -> Answer:
        where = f"\n\nThe answer is in section {section}." if section else ""

        document_block: dict[str, Any] = {
            "type": "text",
            "text": f"<agreement>\n{document}\n</agreement>",
        }
        if self.cache_document:
            # The document is the stable prefix; the question follows it and varies.
            document_block["cache_control"] = {"type": "ephemeral"}

        started = time.monotonic()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            tools=[ANSWER_TOOL],
            tool_choice={"type": "tool", "name": "record_answer"},
            messages=[
                {
                    "role": "user",
                    "content": [document_block, {"type": "text", "text": question + where}],
                }
            ],
        )
        latency = time.monotonic() - started

        payload: dict[str, Any] = {}
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                payload = dict(block.input)
                break

        raw_usage = response.usage
        usage = Usage(
            input_tokens=getattr(raw_usage, "input_tokens", 0) or 0,
            output_tokens=getattr(raw_usage, "output_tokens", 0) or 0,
            cache_read_input_tokens=getattr(raw_usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_input_tokens=getattr(raw_usage, "cache_creation_input_tokens", 0) or 0,
        )

        return Answer(
            answer=str(payload.get("answer", "")),
            quote=str(payload.get("quote", "")),
            reasoning=str(payload.get("reasoning", "")),
            usage=usage,
            model=self.model,
            latency_s=latency,
            raw=payload,
        )
