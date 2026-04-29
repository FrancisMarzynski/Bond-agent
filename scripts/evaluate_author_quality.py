#!/usr/bin/env python3
"""Local author-quality regression sweep with curated Polish prompts."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langgraph.types import Command

from bond.api.author_input import normalize_author_input
from bond.graph.graph import compile_graph


def now_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


@dataclass
class AuthorQualityCase:
    id: str
    message: str
    keywords: list[str] | None = None
    context_dynamic: str | None = None
    expected_topic: str | None = None
    expected_keywords: list[str] | None = None
    expected_context_dynamic: str | None = None


@dataclass
class AuthorQualityResult:
    case_id: str
    status: str
    thread_id: str
    duration_seconds: float
    normalized_topic: str
    normalized_keywords: list[str]
    normalized_context_dynamic: str | None
    normalization_errors: list[str] = field(default_factory=list)
    checkpoint_id: str | None = None
    draft_validated: bool | None = None
    attempt_count: int | None = None
    first_attempt_passed: bool | None = None
    first_attempt_failed_codes: list[str] = field(default_factory=list)
    final_failure_codes: list[str] = field(default_factory=list)
    final_failure_messages: list[str] = field(default_factory=list)
    draft_path: str | None = None
    error: str | None = None


def load_cases(path: Path) -> list[AuthorQualityCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Cases payload must be a JSON array.")

    cases: list[AuthorQualityCase] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Each case must be a JSON object.")
        cases.append(
            AuthorQualityCase(
                id=str(item["id"]),
                message=str(item["message"]),
                keywords=list(item["keywords"]) if isinstance(item.get("keywords"), list) else None,
                context_dynamic=(
                    str(item["context_dynamic"])
                    if item.get("context_dynamic") is not None
                    else None
                ),
                expected_topic=(
                    str(item["expected_topic"])
                    if item.get("expected_topic") is not None
                    else None
                ),
                expected_keywords=(
                    list(item["expected_keywords"])
                    if isinstance(item.get("expected_keywords"), list)
                    else None
                ),
                expected_context_dynamic=(
                    str(item["expected_context_dynamic"])
                    if item.get("expected_context_dynamic") is not None
                    else None
                ),
            )
        )
    return cases


def _extract_interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        return None

    interrupt = interrupts[0]
    payload = interrupt.value if hasattr(interrupt, "value") else interrupt
    return payload if isinstance(payload, dict) else None


def _build_initial_state(
    case: AuthorQualityCase,
    *,
    thread_id: str,
    normalized: dict[str, Any],
) -> dict[str, Any]:
    return {
        "topic": normalized["topic"],
        "keywords": normalized["keywords"],
        "context_dynamic": normalized["context_dynamic"],
        "messages": [{"role": "user", "content": case.message}],
        "mode": "author",
        "thread_id": thread_id,
        "search_cache": {},
        "cp1_iterations": 0,
        "cp2_iterations": 0,
        "metadata_saved": False,
        "duplicate_match": None,
        "duplicate_override": None,
        "research_report": None,
        "heading_structure": None,
        "cp1_approved": None,
        "cp1_feedback": None,
        "draft": None,
        "draft_validated": None,
        "draft_validation_details": None,
        "cp2_approved": None,
        "cp2_feedback": None,
    }


def _check_normalization_expectations(
    case: AuthorQualityCase,
    normalized: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    if case.expected_topic is not None and normalized["topic"] != case.expected_topic:
        errors.append(
            f"expected topic={case.expected_topic!r}, got {normalized['topic']!r}"
        )
    if case.expected_keywords is not None and normalized["keywords"] != case.expected_keywords:
        errors.append(
            f"expected keywords={case.expected_keywords!r}, got {normalized['keywords']!r}"
        )
    if (
        case.expected_context_dynamic is not None
        and normalized["context_dynamic"] != case.expected_context_dynamic
    ):
        errors.append(
            "expected context_dynamic="
            f"{case.expected_context_dynamic!r}, got {normalized['context_dynamic']!r}"
        )

    return errors


async def run_case(
    graph,
    case: AuthorQualityCase,
    *,
    output_dir: Path,
) -> AuthorQualityResult:
    started_at = time.perf_counter()
    thread_id = str(uuid.uuid4())
    normalized = normalize_author_input(
        case.message,
        keywords=case.keywords,
        context_dynamic=case.context_dynamic,
    )
    normalization_errors = _check_normalization_expectations(case, normalized)
    checkpoint_id: str | None = None
    draft_validated: bool | None = None
    attempt_count: int | None = None
    first_attempt_passed: bool | None = None
    first_attempt_failed_codes: list[str] = []
    final_failure_codes: list[str] = []
    final_failure_messages: list[str] = []
    draft_path: str | None = None
    error: str | None = None
    status = "pass"

    try:
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 50,
        }
        result = await graph.ainvoke(
            _build_initial_state(case, thread_id=thread_id, normalized=normalized),
            config=config,
        )

        for _ in range(12):
            payload = _extract_interrupt_payload(result)
            if payload is None:
                raise ValueError("Graph completed without reaching checkpoint_2.")

            checkpoint_id = payload.get("checkpoint")
            if checkpoint_id == "checkpoint_2":
                snapshot = await graph.aget_state(config)
                values = snapshot.values if snapshot and hasattr(snapshot, "values") else {}
                draft = values.get("draft") or ""
                if draft:
                    drafts_dir = output_dir / "drafts"
                    drafts_dir.mkdir(parents=True, exist_ok=True)
                    draft_file = drafts_dir / f"{case.id}.md"
                    draft_file.write_text(draft, encoding="utf-8")
                    draft_path = str(draft_file)

                draft_validated = values.get("draft_validated")
                details = values.get("draft_validation_details") or {}
                attempt_count = details.get("attempt_count")
                attempts = details.get("attempts") or []
                if attempts:
                    first_attempt = attempts[0]
                    first_attempt_passed = first_attempt.get("passed")
                    first_attempt_failed_codes = list(first_attempt.get("failed_codes", []))
                final_failure_codes = list(details.get("failure_codes", []))
                final_failure_messages = [
                    str(failure.get("message", ""))
                    for failure in details.get("failures", [])
                    if isinstance(failure, dict)
                ]
                break

            if checkpoint_id not in {"duplicate_check", "low_corpus", "checkpoint_1"}:
                raise ValueError(f"Unexpected interrupt before checkpoint_2: {checkpoint_id}")

            result = await graph.ainvoke(
                Command(resume={"action": "approve"}),
                config=config,
            )
        else:
            raise ValueError("Exceeded interrupt safety limit before checkpoint_2.")

        if checkpoint_id != "checkpoint_2":
            raise ValueError("Did not capture checkpoint_2 state.")

        if normalization_errors:
            status = "fail"
        elif draft_validated is False:
            status = "pass_with_warnings"
    except Exception as exc:
        status = "fail"
        error = str(exc)

    return AuthorQualityResult(
        case_id=case.id,
        status=status,
        thread_id=thread_id,
        duration_seconds=time.perf_counter() - started_at,
        normalized_topic=normalized["topic"],
        normalized_keywords=normalized["keywords"],
        normalized_context_dynamic=normalized["context_dynamic"],
        normalization_errors=normalization_errors,
        checkpoint_id=checkpoint_id,
        draft_validated=draft_validated,
        attempt_count=attempt_count,
        first_attempt_passed=first_attempt_passed,
        first_attempt_failed_codes=first_attempt_failed_codes,
        final_failure_codes=final_failure_codes,
        final_failure_messages=final_failure_messages,
        draft_path=draft_path,
        error=error,
    )


async def run_quality_sweep(
    cases: list[AuthorQualityCase],
    *,
    output_dir: Path,
) -> list[AuthorQualityResult]:
    async with compile_graph() as graph:
        results: list[AuthorQualityResult] = []
        for case in cases:
            results.append(await run_case(graph, case, output_dir=output_dir))
        return results


def build_markdown_report(results: list[AuthorQualityResult]) -> str:
    lines = [
        "# Author Quality Evaluation",
        "",
        "| Case | Status | draft_validated | attempts | first_passed | final_failures |",
        "|------|--------|-----------------|----------|--------------|----------------|",
    ]

    for result in results:
        lines.append(
            f"| `{result.case_id}` | `{result.status}` | `{result.draft_validated}` | "
            f"`{result.attempt_count}` | `{result.first_attempt_passed}` | "
            f"`{', '.join(result.final_failure_codes) or '-'} `|"
        )

    for result in results:
        lines.extend(
            [
                "",
                f"## {result.case_id}",
                "",
                f"- Status: `{result.status}`",
                f"- Thread ID: `{result.thread_id}`",
                f"- Czas: `{result.duration_seconds:.2f}s`",
                f"- checkpoint_2 reached: `{result.checkpoint_id == 'checkpoint_2'}`",
                f"- draft_validated: `{result.draft_validated}`",
                f"- attempt_count: `{result.attempt_count}`",
                f"- first_attempt_passed: `{result.first_attempt_passed}`",
                f"- normalized_topic: `{result.normalized_topic}`",
                f"- normalized_keywords: `{', '.join(result.normalized_keywords) or 'brak'}`",
                f"- normalized_context_dynamic: `{result.normalized_context_dynamic or 'brak'}`",
            ]
        )

        if result.first_attempt_failed_codes:
            lines.extend(
                [
                    "",
                    "### First-pass failures",
                    "",
                    *[f"- `{code}`" for code in result.first_attempt_failed_codes],
                ]
            )

        if result.final_failure_messages:
            lines.extend(
                [
                    "",
                    "### Final validation failures",
                    "",
                    *[f"- {message}" for message in result.final_failure_messages],
                ]
            )

        if result.normalization_errors:
            lines.extend(
                [
                    "",
                    "### Normalization errors",
                    "",
                    *[f"- {error}" for error in result.normalization_errors],
                ]
            )

        if result.error:
            lines.extend(
                [
                    "",
                    "### Error",
                    "",
                    f"- {result.error}",
                ]
            )

        if result.draft_path:
            lines.extend(
                [
                    "",
                    f"- Draft artifact: `{result.draft_path}`",
                ]
            )

    return "\n".join(lines) + "\n"


def build_json_payload(results: list[AuthorQualityResult]) -> dict[str, Any]:
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


def save_report(results: list[AuthorQualityResult], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "summary.json"
    markdown_path = output_dir / "summary.md"

    json_path.write_text(
        json.dumps(build_json_payload(results), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(build_markdown_report(results), encoding="utf-8")
    return json_path, markdown_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("tests/fixtures/author_quality_cases.json"),
        help="Path to the curated Author quality case matrix.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".planning") / "artifacts" / f"author-quality-{now_slug()}",
        help="Directory for JSON and Markdown evaluation artifacts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cases = load_cases(args.cases)
    results = asyncio.run(run_quality_sweep(cases, output_dir=args.output_dir))
    json_path, markdown_path = save_report(results, args.output_dir)
    payload = build_json_payload(results)

    print(f"Author quality status: {payload['overall_status']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    for result in results:
        print(
            f"- {result.case_id}: status={result.status}, draft_validated={result.draft_validated}, "
            f"attempts={result.attempt_count}, first_passed={result.first_attempt_passed}"
        )

    return 1 if payload["overall_status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
