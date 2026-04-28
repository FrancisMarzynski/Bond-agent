from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ValidationQuery:
    label: str
    text: str


@dataclass(frozen=True)
class ValidationCase:
    slug: str
    topic: str
    queries: tuple[ValidationQuery, ...]


@dataclass
class ParsedSource:
    query_label: str
    title: str
    url: str
    normalized_url: str
    domain: str
    published: str | None
    author: str | None
    highlights: str


@dataclass
class QueryValidationResult:
    label: str
    query: str
    raw_result_count: int
    parsed_result_count: int
    error: str | None


@dataclass
class CaseValidationResult:
    slug: str
    topic: str
    status: str
    duration_seconds: float
    total_raw_results: int
    unique_sources: int
    duplicate_sources: int
    unique_domains: int
    polish_domains: int
    recent_sources: int
    query_results: list[QueryValidationResult]
    failures: list[str]
    warnings: list[str]
    sources: list[ParsedSource]


CURATED_CASES: tuple[ValidationCase, ...] = (
    ValidationCase(
        slug="ai-marketing-b2b",
        topic="Agenci AI w marketingu B2B",
        queries=(
            ValidationQuery(
                label="overview",
                text="agenci AI w marketingu B2B trendy 2025 Polska",
            ),
            ValidationQuery(
                label="stats",
                text="agenci AI marketing B2B statystyki raport 2025 Polska",
            ),
            ValidationQuery(
                label="case-study",
                text="agenci AI marketing B2B studium przypadku Polska",
            ),
        ),
    ),
    ValidationCase(
        slug="bim-instalacje-elektryczne",
        topic="BIM w projektowaniu instalacji elektrycznych",
        queries=(
            ValidationQuery(
                label="overview",
                text="BIM projektowanie instalacji elektrycznych korzyści Polska",
            ),
            ValidationQuery(
                label="stats",
                text="BIM instalacje elektryczne statystyki raport Polska",
            ),
            ValidationQuery(
                label="case-study",
                text="BIM instalacje elektryczne case study Polska",
            ),
        ),
    ),
    ValidationCase(
        slug="xr-szkolenia-przemyslowe",
        topic="XR w szkoleniach przemysłowych",
        queries=(
            ValidationQuery(
                label="overview",
                text="XR szkolenia przemysłowe korzyści Polska",
            ),
            ValidationQuery(
                label="stats",
                text="XR szkolenia VR AR statystyki raport 2025 Polska",
            ),
            ValidationQuery(
                label="case-study",
                text="XR szkolenia przemysłowe case study Polska",
            ),
        ),
    ),
    ValidationCase(
        slug="cyfrowe-blizniaki-budynki",
        topic="Cyfrowe bliźniaki w utrzymaniu budynków",
        queries=(
            ValidationQuery(
                label="overview",
                text="cyfrowe bliźniaki utrzymanie budynków korzyści Polska",
            ),
            ValidationQuery(
                label="stats",
                text="cyfrowe bliźniaki facility management statystyki raport 2025 Polska",
            ),
            ValidationQuery(
                label="case-study",
                text="cyfrowe bliźniaki zarządzanie budynkami case study Polska",
            ),
        ),
    ),
)


def _timestamp_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.upper() == "N/A":
        return None
    return stripped


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    return f"{parts.scheme.lower()}://{host}{path}"


def extract_domain(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host.removeprefix("www.")


def parse_exa_item(item: dict[str, Any], query_label: str) -> list[ParsedSource]:
    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        return []

    parsed_sources: list[ParsedSource] = []
    for block in text.split("\n---\n"):
        stripped_block = block.strip()
        if not stripped_block:
            continue

        header, separator, highlights = stripped_block.partition("\nHighlights:\n")
        if not separator:
            highlights = ""

        fields: dict[str, str] = {}
        for line in header.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()

        title = fields.get("Title", "").strip()
        url = fields.get("URL", "").strip()
        if not title or not url:
            continue

        parsed_sources.append(
            ParsedSource(
                query_label=query_label,
                title=title,
                url=url,
                normalized_url=normalize_url(url),
                domain=extract_domain(url),
                published=_normalize_optional(fields.get("Published")),
                author=_normalize_optional(fields.get("Author")),
                highlights=highlights.strip(),
            )
        )

    return parsed_sources


def dedupe_sources(sources: Iterable[ParsedSource]) -> list[ParsedSource]:
    unique: dict[str, ParsedSource] = {}
    for source in sources:
        unique.setdefault(source.normalized_url, source)
    return list(unique.values())


def is_recent_source(
    published: str | None,
    *,
    earliest_year: int = 2024,
) -> bool:
    if not published:
        return False
    try:
        parsed = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.astimezone(timezone.utc).year >= earliest_year


def evaluate_case(
    case: ValidationCase,
    query_results: list[QueryValidationResult],
    sources: list[ParsedSource],
    *,
    duration_seconds: float,
) -> CaseValidationResult:
    deduped_sources = dedupe_sources(sources)
    failures: list[str] = []
    warnings: list[str] = []

    queries_without_results = [
        result.label for result in query_results if result.parsed_result_count == 0
    ]
    if queries_without_results:
        failures.append(
            "Brak wyników dla zapytań: " + ", ".join(sorted(queries_without_results))
        )

    query_errors = [result.label for result in query_results if result.error]
    if query_errors:
        failures.append(
            "Błąd wywołania Exa dla zapytań: " + ", ".join(sorted(query_errors))
        )

    unique_source_count = len(deduped_sources)
    unique_domain_count = len({source.domain for source in deduped_sources})
    polish_domain_count = sum(
        1 for source in deduped_sources if source.domain.endswith(".pl")
    )
    recent_source_count = sum(
        1 for source in deduped_sources if is_recent_source(source.published)
    )

    if unique_source_count < 6:
        failures.append(
            f"Za mało unikalnych źródeł: {unique_source_count} < 6 dla tematu '{case.topic}'"
        )
    if unique_domain_count < 4:
        failures.append(
            f"Za mało unikalnych domen: {unique_domain_count} < 4 dla tematu '{case.topic}'"
        )
    if polish_domain_count == 0:
        warnings.append("Brak domen .pl w deduplikowanych wynikach")
    if recent_source_count < 2:
        warnings.append("Mniej niż 2 źródła z datą publikacji od 2024 roku")

    duplicate_count = len(sources) - unique_source_count
    if unique_source_count > 0 and duplicate_count / max(len(sources), 1) > 0.4:
        warnings.append("Wysoki udział duplikatów między zapytaniami (>40%)")

    status = "fail"
    if not failures:
        status = "pass_with_warnings" if warnings else "pass"

    return CaseValidationResult(
        slug=case.slug,
        topic=case.topic,
        status=status,
        duration_seconds=round(duration_seconds, 2),
        total_raw_results=sum(result.raw_result_count for result in query_results),
        unique_sources=unique_source_count,
        duplicate_sources=duplicate_count,
        unique_domains=unique_domain_count,
        polish_domains=polish_domain_count,
        recent_sources=recent_source_count,
        query_results=query_results,
        failures=failures,
        warnings=warnings,
        sources=deduped_sources,
    )


async def _run_query(query: ValidationQuery, *, num_results: int) -> tuple[list[dict[str, Any]], str | None]:
    from bond.graph.nodes.researcher import _get_exa_tools

    tools = await _get_exa_tools()
    web_search = next((tool for tool in tools if tool.name == "web_search_exa"), None)
    if web_search is None:
        raise RuntimeError("web_search_exa not found in Exa MCP tool list")

    try:
        raw = await web_search.ainvoke({"query": query.text, "numResults": num_results})
    except Exception as exc:  # pragma: no cover - exercised in live runs
        return [], str(exc)

    if not isinstance(raw, list):
        return [], f"Unexpected Exa payload type: {type(raw).__name__}"

    normalized_items = [item for item in raw if isinstance(item, dict)]
    return normalized_items, None


async def run_case(case: ValidationCase, *, num_results: int) -> CaseValidationResult:
    started_at = time.perf_counter()
    raw_query_results = await asyncio.gather(
        *[_run_query(query, num_results=num_results) for query in case.queries]
    )

    query_results: list[QueryValidationResult] = []
    parsed_sources: list[ParsedSource] = []

    for query, (raw_items, error) in zip(case.queries, raw_query_results):
        parsed_items = [
            parsed_source
            for item in raw_items
            for parsed_source in parse_exa_item(item, query.label)
        ]
        parsed_sources.extend(parsed_items)
        query_results.append(
            QueryValidationResult(
                label=query.label,
                query=query.text,
                raw_result_count=len(raw_items),
                parsed_result_count=len(parsed_items),
                error=error,
            )
        )

    return evaluate_case(
        case,
        query_results,
        parsed_sources,
        duration_seconds=time.perf_counter() - started_at,
    )


async def run_validation(
    *,
    cases: Iterable[ValidationCase],
    num_results: int,
) -> list[CaseValidationResult]:
    results: list[CaseValidationResult] = []
    for case in cases:
        results.append(await run_case(case, num_results=num_results))
    return results


def build_markdown_report(results: list[CaseValidationResult]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Exa Polish Validation",
        "",
        f"Wygenerowano: {generated_at}",
        "",
        "Walidacja obejmuje 4 kuratorowane przypadki researchowe w języku polskim.",
        "Każdy case uruchamia 3 zapytania (overview / stats / case-study) bez udziału LLM i ocenia surową jakość wyników Exa MCP.",
        "",
        "| Case | Status | Unique sources | Unique domains | `.pl` domains | Recent sources | Duplicates |",
        "|------|--------|----------------|----------------|---------------|----------------|------------|",
    ]

    for result in results:
        lines.append(
            f"| `{result.slug}` | `{result.status}` | {result.unique_sources} | "
            f"{result.unique_domains} | {result.polish_domains} | {result.recent_sources} | "
            f"{result.duplicate_sources} |"
        )

    for result in results:
        lines.extend(
            [
                "",
                f"## {result.topic}",
                "",
                f"- Status: `{result.status}`",
                f"- Czas: `{result.duration_seconds:.2f}s`",
                f"- Surowe wyniki: `{result.total_raw_results}`",
                f"- Unikalne źródła: `{result.unique_sources}`",
                f"- Unikalne domeny: `{result.unique_domains}`",
                f"- Domeny `.pl`: `{result.polish_domains}`",
                f"- Źródła od 2024 roku: `{result.recent_sources}`",
                f"- Duplikaty między zapytaniami: `{result.duplicate_sources}`",
                "",
                "### Zapytania",
                "",
            ]
        )
        for query in result.query_results:
            query_line = (
                f"- `{query.label}`: `{query.query}` "
                f"(raw={query.raw_result_count}, parsed={query.parsed_result_count})"
            )
            if query.error:
                query_line += f" — ERROR: {query.error}"
            lines.append(query_line)

        if result.failures:
            lines.extend(["", "### Failures", ""])
            lines.extend(f"- {failure}" for failure in result.failures)

        if result.warnings:
            lines.extend(["", "### Warnings", ""])
            lines.extend(f"- {warning}" for warning in result.warnings)

        lines.extend(["", "### Sources", ""])
        for source in result.sources[:8]:
            published = source.published or "brak daty"
            lines.append(
                f"- `{source.query_label}` • `{source.domain}` • {published} — "
                f"[{source.title}]({source.url})"
            )

    return "\n".join(lines) + "\n"


def build_json_payload(results: list[CaseValidationResult]) -> dict[str, Any]:
    overall_status = "pass"
    if any(result.status == "fail" for result in results):
        overall_status = "fail"
    elif any(result.status == "pass_with_warnings" for result in results):
        overall_status = "pass_with_warnings"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "cases": [asdict(result) for result in results],
    }


def save_report(results: list[CaseValidationResult], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "summary.json"
    markdown_path = output_dir / "summary.md"

    json_path.write_text(
        json.dumps(build_json_payload(results), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(build_markdown_report(results), encoding="utf-8")
    return json_path, markdown_path


def resolve_cases(case_slugs: list[str]) -> list[ValidationCase]:
    if not case_slugs:
        return list(CURATED_CASES)

    available = {case.slug: case for case in CURATED_CASES}
    resolved: list[ValidationCase] = []
    missing = [slug for slug in case_slugs if slug not in available]
    if missing:
        raise ValueError(
            "Unknown case slug(s): "
            + ", ".join(sorted(missing))
            + ". Available: "
            + ", ".join(sorted(available))
        )
    for slug in case_slugs:
        resolved.append(available[slug])
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live validation of Exa MCP for curated Polish research queries."
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Optional case slug to run. Can be provided multiple times.",
    )
    parser.add_argument(
        "--num-results",
        type=int,
        default=5,
        help="Number of Exa results requested per query.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".planning") / "artifacts" / f"exa-polish-{_timestamp_slug()}",
        help="Directory for JSON and Markdown artifacts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cases = resolve_cases(args.case)
    results = asyncio.run(run_validation(cases=cases, num_results=args.num_results))
    json_path, markdown_path = save_report(results, args.output_dir)

    overall_status = build_json_payload(results)["overall_status"]
    print(f"Exa validation status: {overall_status}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")

    for result in results:
        print(
            f"- {result.slug}: {result.status} "
            f"(sources={result.unique_sources}, domains={result.unique_domains}, "
            f".pl={result.polish_domains}, recent={result.recent_sources})"
        )

    return 1 if overall_status == "fail" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
