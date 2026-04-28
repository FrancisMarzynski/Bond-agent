from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

DEFAULT_MAX_INPUT_TOKENS = 8192
DEFAULT_SAFETY_MARGIN_TOKENS = 400
RESEARCH_CONTEXT_OMISSION_MARKER = (
    "[Pominięto część źródeł z powodu limitu kontekstu modelu. "
    "Fakty i statystyki zachowano w całości.]"
)

PromptPayload = str | Sequence[Any]
PromptPayloadBuilder = Callable[[str], PromptPayload]


@dataclass(frozen=True, slots=True)
class ResearchSource:
    title: str
    url: str
    summary: str


@dataclass(frozen=True, slots=True)
class ResearchContextVariant:
    kind: str
    content: str
    source_count: int


@dataclass(frozen=True, slots=True)
class ResearchContextSelection:
    variant: ResearchContextVariant
    estimated_prompt_tokens: int
    available_input_tokens: int
    fit_found: bool


def iter_research_context_variants(
    research_report: str,
    research_data: Mapping[str, Any] | Any | None,
) -> tuple[ResearchContextVariant, ...]:
    report = research_report.strip()
    sources = _normalize_sources(_lookup(research_data, "zrodla", []))

    variants: list[ResearchContextVariant] = []
    seen_contents: set[str] = set()

    if report:
        variants.append(
            ResearchContextVariant(
                kind="full_report",
                content=report,
                source_count=len(sources),
            )
        )
        seen_contents.add(report)

    total_sources = len(sources)
    for source_limit in range(total_sources, -1, -1):
        kind = (
            "structured_all_sources"
            if source_limit == total_sources
            else "structured_reduced_sources"
        )
        if source_limit == 0:
            kind = "structured_core_only"

        content = render_structured_research_context(
            research_data,
            max_sources=source_limit,
        )
        if not content or content in seen_contents:
            continue

        variants.append(
            ResearchContextVariant(
                kind=kind,
                content=content,
                source_count=source_limit,
            )
        )
        seen_contents.add(content)

    if variants:
        return tuple(variants)

    return (ResearchContextVariant(kind="empty", content="", source_count=0),)


def render_structured_research_context(
    research_data: Mapping[str, Any] | Any | None,
    *,
    max_sources: int | None = None,
) -> str:
    facts = _normalize_text_list(_lookup(research_data, "fakty", []))
    stats = _normalize_text_list(_lookup(research_data, "statystyki", []))
    sources = _normalize_sources(_lookup(research_data, "zrodla", []))

    if max_sources is None:
        kept_sources = sources
    else:
        kept_sources = sources[: max(0, max_sources)]
    omitted_sources = max(0, len(sources) - len(kept_sources))

    sections: list[str] = []
    if facts:
        sections.append("### Fakty\n" + "\n".join(f"- {fact}" for fact in facts))
    if stats:
        sections.append("### Statystyki\n" + "\n".join(f"- {stat}" for stat in stats))

    source_lines = [
        f"{index}. {source.title} | {source.url} | {source.summary}"
        for index, source in enumerate(kept_sources, start=1)
    ]
    if omitted_sources:
        source_lines.append(
            f"{RESEARCH_CONTEXT_OMISSION_MARKER} (pominięto: {omitted_sources})"
        )
    if source_lines:
        sections.append("### Źródła\n" + "\n".join(source_lines))

    return "\n\n".join(
        section.strip() for section in sections if section.strip()
    ).strip()


def select_research_context(
    *,
    llm: Any,
    research_report: str,
    research_data: Mapping[str, Any] | Any | None,
    build_prompt_payload: PromptPayloadBuilder,
    reserved_output_tokens: int | None = None,
    safety_margin_tokens: int = DEFAULT_SAFETY_MARGIN_TOKENS,
) -> ResearchContextSelection:
    variants = iter_research_context_variants(research_report, research_data)
    available_input_tokens = get_available_input_tokens(
        llm,
        reserved_output_tokens=reserved_output_tokens,
        safety_margin_tokens=safety_margin_tokens,
    )

    selected_variant = variants[-1]
    selected_tokens = 0
    fit_found = False

    for variant in variants:
        prompt_payload = build_prompt_payload(variant.content)
        token_count = count_prompt_tokens(llm, prompt_payload)
        selected_variant = variant
        selected_tokens = token_count
        if token_count <= available_input_tokens:
            fit_found = True
            break

    return ResearchContextSelection(
        variant=selected_variant,
        estimated_prompt_tokens=selected_tokens,
        available_input_tokens=available_input_tokens,
        fit_found=fit_found,
    )


def get_available_input_tokens(
    llm: Any,
    *,
    reserved_output_tokens: int | None = None,
    safety_margin_tokens: int = DEFAULT_SAFETY_MARGIN_TOKENS,
) -> int:
    max_input_tokens = get_model_max_input_tokens(llm)
    output_tokens = reserved_output_tokens
    if output_tokens is None:
        output_tokens = _coerce_int(getattr(llm, "max_tokens", None)) or 0
    return max(max_input_tokens - output_tokens - safety_margin_tokens, 0)


def get_model_max_input_tokens(llm: Any) -> int:
    configured_limits = [
        limit
        for limit in (
            _extract_max_input_tokens(candidate)
            for candidate in _iter_model_candidates(llm)
        )
        if limit is not None
    ]
    if configured_limits:
        return min(configured_limits)
    return DEFAULT_MAX_INPUT_TOKENS


def count_prompt_tokens(llm: Any, prompt_payload: PromptPayload) -> int:
    if isinstance(prompt_payload, str):
        if hasattr(llm, "get_num_tokens"):
            try:
                return int(llm.get_num_tokens(prompt_payload))
            except Exception:
                pass
        return _approximate_token_count(prompt_payload)

    if hasattr(llm, "get_num_tokens_from_messages"):
        try:
            return int(llm.get_num_tokens_from_messages(list(prompt_payload)))
        except Exception:
            pass

    prompt_text = _stringify_prompt_payload(prompt_payload)
    if hasattr(llm, "get_num_tokens"):
        try:
            return int(llm.get_num_tokens(prompt_text))
        except Exception:
            pass
    return _approximate_token_count(prompt_text)


def _iter_model_candidates(llm: Any) -> list[Any]:
    candidates = [llm]
    runnable = getattr(llm, "runnable", None)
    if runnable is not None:
        candidates.append(runnable)
    candidates.extend(getattr(llm, "fallbacks", []) or [])
    return candidates


def _extract_max_input_tokens(candidate: Any) -> int | None:
    profile = getattr(candidate, "profile", None)
    if isinstance(profile, Mapping):
        return _coerce_int(profile.get("max_input_tokens"))
    if profile is not None:
        return _coerce_int(getattr(profile, "max_input_tokens", None))
    return None


def _lookup(data: Mapping[str, Any] | Any | None, key: str, default: Any) -> Any:
    if data is None:
        return default
    if isinstance(data, Mapping):
        return data.get(key, default)
    return getattr(data, key, default)


def _normalize_text_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    normalized = [str(item).strip() for item in value if str(item).strip()]
    return tuple(normalized)


def _normalize_sources(value: Any) -> tuple[ResearchSource, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()

    normalized: list[ResearchSource] = []
    for item in value:
        if isinstance(item, Mapping):
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            summary = str(item.get("summary", "")).strip()
        else:
            title = str(getattr(item, "title", "")).strip()
            url = str(getattr(item, "url", "")).strip()
            summary = str(getattr(item, "summary", "")).strip()

        if title or url or summary:
            normalized.append(ResearchSource(title=title, url=url, summary=summary))

    return tuple(normalized)


def _stringify_prompt_payload(prompt_payload: Sequence[Any]) -> str:
    parts: list[str] = []
    for message in prompt_payload:
        content = getattr(message, "content", message)
        parts.append(str(content))
    return "\n\n".join(parts)


def _approximate_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
