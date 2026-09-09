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
from urllib.parse import urlsplit

#: How a model wants its thinking configured.
#:
#: ``always`` — thinking cannot be turned off; send no ``thinking`` parameter.
#: ``adaptive`` — send ``{"type": "adaptive"}``.
#: ``budget`` — the pre-4.6 shape, ``{"type": "enabled", "budget_tokens": N}``.
#: ``none`` — the endpoint has no thinking parameter at all (everything OpenAI-compatible).
THINKING_STYLES = ("always", "adaptive", "budget", "none")

#: Who serves the model. "anthropic" uses the SDK; "openai_compat" uses the chat-completions
#: adapter, which is Ollama and vLLM locally and OpenRouter/Together/Groq in the cloud.
PROVIDERS = ("anthropic", "openai_compat")

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class ModelSpec:
    id: str
    input_per_mtok: float
    output_per_mtok: float
    thinking_style: str
    supports_effort: bool

    provider: str = "anthropic"

    #: Where an openai_compat model is served. Local endpoints cost nothing to run, which is
    #: why the prices above are zero for them.
    base_url: str = ""

    #: Whether the rates above are a fact or a placeholder. False means "this endpoint bills
    #: and nobody told us the rates", and every cost figure derived from it must say so
    #: rather than print a confident zero. See `spec_for` and LIMITATIONS §20.
    pricing_known: bool = True

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

        if self.thinking_style == "none":
            # A chat-completions endpoint has no thinking or effort parameter. Sending one
            # is a 400 on some servers and silently ignored on others, and the second is
            # worse: it looks like the setting took effect.
            return extras

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

#: The default local endpoint. Ollama serves this once `ollama serve` is running.
OLLAMA = "http://localhost:11434/v1"

#: Hosts that genuinely cost nothing to call, because the machine is yours.
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]", ""})


def is_local_endpoint(base_url: str) -> bool:
    """Is this endpoint on the machine running the sweep?

    The distinction is the whole of LIMITATIONS §20: a local endpoint is free, so pricing it
    at zero is correct, and a hosted one bills you while this suite reports zero and says
    nothing about it.

    The host is **parsed**, not searched for. `"localhost" in url` was the old test, and it
    is true of `https://localhost.example.com/v1`, which is somebody else's server: a
    substring check here would price a paid endpoint at nothing, which is the precise error
    this function exists to prevent.
    """
    host = (urlsplit(base_url).hostname or "").lower()
    return host in _LOCAL_HOSTS or host.endswith(".localhost") or host.startswith("127.")


def local(model_id: str, base_url: str = OLLAMA) -> ModelSpec:
    """A model on your own machine. Costs nothing, so it is priced at nothing."""
    return ModelSpec(
        id=model_id,
        input_per_mtok=0.0,
        output_per_mtok=0.0,
        thinking_style="none",
        supports_effort=False,
        provider="openai_compat",
        base_url=base_url,
    )


#: A few local models worth trying first. Any other id works via `--base-url`; these exist so
#: that the common case is one flag rather than three.
for _name in (
    "qwen2.5:1.5b",  # too small to call tools at all — fails the doctor, and is listed
    #                  so that finding that out costs one command
    "llama3.2:3b",  # the smallest observed to pass every check. 2GB, runs on a laptop
    "qwen2.5:3b",
    "qwen2.5:7b",
    "qwen3:8b",
    "llama3.1:8b",
    "mistral:7b",
    "gpt-oss:20b",
):
    MODELS[_name] = local(_name)


DEFAULT_MODEL = "claude-opus-5"


def spec_for(
    model_id: str,
    base_url: str = "",
    input_per_mtok: float | None = None,
    output_per_mtok: float | None = None,
) -> ModelSpec:
    """Look up a model, or build an OpenAI-compatible spec on the fly for an unknown one.

    An unknown id with a `--base-url` is not an error: the whole point of the adapter is to
    reach models nobody has listed here.

    **Zero is a claim, not a default.** It used to be applied to every OpenAI-compatible
    model regardless of where it was served, so a sweep against OpenRouter or Groq printed
    `$0.0000` while the provider billed for it — wrong, and silent about being wrong. Now
    only a genuinely local endpoint is priced at zero, because there the zero is true.
    A hosted endpoint with no rates supplied is marked `pricing_known=False` and every
    figure derived from it says "not tracked" instead of naming a number.

    Rates can be supplied (`--price-in` / `--price-out`, USD per million tokens) from the
    provider's own page, and then the cost is computed and stored like any other.
    """
    if base_url:
        known = MODELS.get(model_id)
        base = (
            ModelSpec(**{**known.__dict__, "base_url": base_url})
            if known is not None and known.provider == "openai_compat"
            else local(model_id, base_url)
        )
        if input_per_mtok is not None or output_per_mtok is not None:
            return ModelSpec(
                **{
                    **base.__dict__,
                    "input_per_mtok": input_per_mtok or 0.0,
                    "output_per_mtok": output_per_mtok or 0.0,
                    "pricing_known": True,
                }
            )
        if is_local_endpoint(base_url):
            return base
        # Hosted, and nobody said what it costs. Say that, rather than zero.
        return ModelSpec(**{**base.__dict__, "pricing_known": False})

    try:
        return MODELS[model_id]
    except KeyError:
        raise KeyError(
            f"no pricing or request shape recorded for {model_id!r}. Add it to MODELS "
            "rather than guessing — a model swept without its correct thinking shape "
            "produces a result for a configuration nobody ran."
        ) from None
