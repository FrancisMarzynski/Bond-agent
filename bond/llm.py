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
        return ChatAnthropic(**kwargs)
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
