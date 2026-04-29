from __future__ import annotations

import re
from typing import TypedDict


class NormalizedAuthorInput(TypedDict):
    topic: str
    keywords: list[str]
    context_dynamic: str | None
    raw_message: str


_SECTION_ALIASES = {
    "temat": "topic",
    "slowa kluczowe": "keywords",
    "słowa kluczowe": "keywords",
    "wymagania": "context_dynamic",
}
_SECTION_PATTERN = re.compile(
    r"^\s*(Temat|Słowa kluczowe|Slowa kluczowe|Wymagania)\s*:\s*(.*)$",
    re.IGNORECASE,
)
_KEYWORD_SPLIT_PATTERN = re.compile(r"[,\n;]+")


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_keywords(values: list[str] | None) -> list[str]:
    if values is None:
        return []

    normalized: list[str] = []
    seen: set[str] = set()

    for value in values:
        for part in _KEYWORD_SPLIT_PATTERN.split(value):
            keyword = part.strip()
            if not keyword:
                continue
            dedupe_key = keyword.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized.append(keyword)

    return normalized


def _parse_labeled_brief(message: str) -> tuple[str | None, list[str], str | None]:
    sections: dict[str, list[str]] = {"topic": [], "keywords": [], "context_dynamic": []}
    current_section: str | None = None
    found_label = False

    for raw_line in message.splitlines():
        match = _SECTION_PATTERN.match(raw_line)
        if match:
            found_label = True
            label = match.group(1).strip().casefold()
            current_section = _SECTION_ALIASES.get(label)
            initial_value = match.group(2).strip()
            if current_section and initial_value:
                sections[current_section].append(initial_value)
            continue

        if current_section is not None:
            stripped = raw_line.strip()
            if stripped:
                sections[current_section].append(stripped)

    if not found_label or not sections["topic"]:
        return None, [], None

    topic = " ".join(sections["topic"]).strip()
    keywords = _normalize_keywords(sections["keywords"])
    context_dynamic = _normalize_optional_text("\n".join(sections["context_dynamic"]))
    return topic or None, keywords, context_dynamic


def normalize_author_input(
    message: str,
    *,
    keywords: list[str] | None = None,
    context_dynamic: str | None = None,
) -> NormalizedAuthorInput:
    parsed_topic, parsed_keywords, parsed_context = _parse_labeled_brief(message)

    normalized_topic = _normalize_optional_text(parsed_topic) or message.strip()
    normalized_keywords = (
        _normalize_keywords(keywords) if keywords is not None else parsed_keywords
    )
    normalized_context = (
        _normalize_optional_text(context_dynamic)
        if context_dynamic is not None
        else parsed_context
    )

    return {
        "topic": normalized_topic,
        "keywords": normalized_keywords,
        "context_dynamic": normalized_context,
        "raw_message": message,
    }
