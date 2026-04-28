"""Centralized LLM factory for Bond agent nodes.

All ChatOpenAI / ChatAnthropic instantiation goes through this module so that
timeout, max_retries, and model selection are configured in one place.

Usage:
    from bond.llm import get_research_llm, get_draft_llm

    llm = get_research_llm()                     # defaults: max_tokens=2500, temperature=0
    llm = get_research_llm(max_tokens=800)       # override for lightweight calls
    llm = get_draft_llm(temperature=0.7)         # creative draft generation
    llm = get_draft_llm(temperature=0)           # deterministic (structured output)
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from bond.config import settings

# Default token budgets per role — overridable via kwargs
_RESEARCH_MAX_TOKENS = 2500
_DRAFT_MAX_TOKENS = 4096

# USD cost per 1 million tokens: {model_substring: (input_price, output_price)}
# Prices are approximate and based on public OpenAI / Anthropic pricing pages.
_MODEL_COSTS_USD_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-opus": (15.00, 75.00),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return approximate USD cost for a single LLM call.

    Matches ``model`` against the longest substring key in ``_MODEL_COSTS_USD_PER_1M``.
    Falls back to gpt-4o pricing when no match is found (conservative over-estimate).
    """
    model_lower = model.lower()
    matched_key = max(
        (k for k in _MODEL_COSTS_USD_PER_1M if k in model_lower),
        key=len,
        default=None,
    )
    input_price, output_price = _MODEL_COSTS_USD_PER_1M.get(matched_key or "", (2.50, 10.00))
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def _build_llm(model: str, tokens: int, temperature: float) -> BaseChatModel:
    """Instantiate the correct LLM class based on model name."""
    kwargs = dict(
        model=model,
        max_tokens=tokens,
        temperature=temperature,
        timeout=float(settings.openai_timeout),
        max_retries=settings.openai_max_retries,
    )
    if "claude" in model.lower():
        if settings.anthropic_api_key:
            kwargs["api_key"] = settings.anthropic_api_key
        return ChatAnthropic(**kwargs)
    if settings.openai_api_key:
        kwargs["api_key"] = settings.openai_api_key
    return ChatOpenAI(**kwargs)


def get_research_llm(
    max_tokens: int | None = None,
    temperature: float = 0,
) -> BaseChatModel:
    """Return an LLM configured for research and analysis tasks.

    Uses ``settings.research_model``.  For OpenAI models, ``timeout`` and
    ``max_retries`` are applied from settings so transient API failures are
    retried automatically and hung requests are killed after a deadline.

    Args:
        max_tokens: Override the default token budget (default: 2500).
        temperature: Sampling temperature (default: 0 — deterministic).
    """
    tokens = max_tokens if max_tokens is not None else _RESEARCH_MAX_TOKENS
    return _build_llm(settings.research_model, tokens, temperature)


def get_draft_llm(
    max_tokens: int | None = None,
    temperature: float = 0.7,
) -> BaseChatModel:
    """Return an LLM configured for draft generation tasks.

    Uses ``settings.draft_model`` with ``settings.research_model`` as an
    automatic fallback in case of rate-limit or availability errors.

    Args:
        max_tokens: Override the default token budget (default: 4096).
        temperature: Sampling temperature (default: 0.7 — creative drafts).
                     Pass 0 for deterministic structured-output calls.
    """
    tokens = max_tokens if max_tokens is not None else _DRAFT_MAX_TOKENS
    primary = _build_llm(settings.draft_model, tokens, temperature)
    fallback = _build_llm(settings.research_model, tokens, temperature)
    return primary.with_fallbacks([fallback])
