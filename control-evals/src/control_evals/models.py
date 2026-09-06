"""The models under test, and how each one's request has to be shaped.

**Model choice is the experiment, not a setting.** The deliverable is "which model, at which
effort, gives acceptable completion at acceptable violation risk", so nothing here hardcodes
one model and every model in the table is meant to be swept.

The awkward part, and the reason this file exists rather than a dict in the runner: the
request shape is not uniform across the range. Sending the same JSON to all of them fails.

* Opus 5 thinks by default; passing `budget_tokens` is a 400.
* Opus 4.8 and 4.7 do *not* think unless `{"type": "adaptive"}` is set explicitly. Omitting
  the parameter silently gives you a different experiment from the one you think you are
  running, which is the worst failure mode available here.
* Haiku 4.5 rejects `output_config.effort` outright and still takes the old
  `{"type": "enabled", "budget_tokens": N}` shape.
* Fable 5.1 always thinks — any explicit `thinking` configuration other than adaptive is a
  400 — and rejects forced `tool_choice`.

Prices are USD per million tokens, first-party API rates, recorded here so a cost figure can
be recomputed from a stored run without another network call.
"""

from __future__ import annotations

from dataclasses import dataclass

#: How a model wants its thinking configured.
#:
#: ``always`` — thinking cannot be turned off; send no ``thinking`` parameter.
#: ``adaptive`` — send ``{"type": "adaptive"}``.
#: ``budget`` — the pre-4.6 shape, ``{"type": "enabled", "budget_tokens": N}``.
THINKING_STYLES = ("always", "adaptive", "budget")

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class ModelSpec:
    id: str
    input_per_mtok: float
    output_per_mtok: float
    thinking_style: str
    supports_effort: bool

    #: A ceiling, not a budget — you are billed for tokens generated, not for the number
    #: here. It is set high enough that a long deliberation is never truncated mid-call,
    #: because a truncated call wastes everything spent on it.
    max_tokens: int = 8192

    #: Only meaningful when thinking_style is "budget".
    thinking_budget: int = 2048

    def request_extras(self, effort: str = "high") -> dict:
        """The model-specific half of a request. Everything that differs lives here.

        Returns a dict to merge into the ``messages.create`` call, so the runner never has
        to know which generation it is talking to.
        """
        extras: dict = {}

        if self.thinking_style == "adaptive":
            extras["thinking"] = {"type": "adaptive"}
        elif self.thinking_style == "budget":
            extras["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
        # "always": send nothing. An explicit configuration is rejected.

        if self.supports_effort and effort:
            if effort not in EFFORT_LEVELS:
                raise ValueError(f"unknown effort {effort!r}; expected one of {EFFORT_LEVELS}")
            extras["output_config"] = {"effort": effort}

        return extras


#: Pricing verified against the published first-party rates. Partner platforms (Bedrock,
#: Vertex) bill differently; if a run is ever made through one, its cost figure is wrong and
#: the run record should say which platform it used.
MODELS: dict[str, ModelSpec] = {
    "claude-opus-5": ModelSpec(
        id="claude-opus-5",
        input_per_mtok=5.00,
        output_per_mtok=25.00,
        thinking_style="adaptive",
        supports_effort=True,
    ),
    "claude-sonnet-5": ModelSpec(
        id="claude-sonnet-5",
        input_per_mtok=2.00,
        output_per_mtok=10.00,
        thinking_style="adaptive",
        supports_effort=True,
    ),
    "claude-haiku-4-5": ModelSpec(
        id="claude-haiku-4-5",
        input_per_mtok=1.00,
        output_per_mtok=5.00,
        # Rejects output_config.effort, and still wants an explicit thinking budget.
        thinking_style="budget",
        supports_effort=False,
    ),
    "claude-opus-4-8": ModelSpec(
        id="claude-opus-4-8",
        input_per_mtok=5.00,
        output_per_mtok=25.00,
        # Omitting `thinking` here means no thinking at all — a different experiment.
        thinking_style="adaptive",
        supports_effort=True,
    ),
    "claude-fable-5-1": ModelSpec(
        id="claude-fable-5-1",
        input_per_mtok=10.00,
        output_per_mtok=50.00,
        thinking_style="always",
        supports_effort=True,
    ),
}

DEFAULT_MODEL = "claude-opus-5"


def spec_for(model_id: str) -> ModelSpec:
    try:
        return MODELS[model_id]
    except KeyError:
        raise KeyError(
            f"no pricing or request shape recorded for {model_id!r}. Add it to MODELS "
            "rather than guessing — a model swept without its correct thinking shape "
            "produces a result for a configuration nobody ran."
        ) from None
