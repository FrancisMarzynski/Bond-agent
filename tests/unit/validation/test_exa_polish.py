from bond.validation.exa_polish import (
    ValidationCase,
    ValidationQuery,
    QueryValidationResult,
    ParsedSource,
    dedupe_sources,
    evaluate_case,
    extract_domain,
    normalize_url,
    parse_exa_item,
)


def _case() -> ValidationCase:
    return ValidationCase(
        slug="test-case",
        topic="Temat testowy",
        queries=(
            ValidationQuery(label="overview", text="zapytanie 1"),
            ValidationQuery(label="stats", text="zapytanie 2"),
            ValidationQuery(label="case-study", text="zapytanie 3"),
        ),
    )


def test_parse_exa_item_extracts_core_fields() -> None:
    item = {
        "type": "text",
        "text": (
            "Title: Raport AI w Polsce\n"
            "URL: https://www.example.pl/raport-ai?utm_source=test\n"
            "Published: 2026-01-20T22:28:59.000Z\n"
            "Author: Jan Kowalski\n"
            "Highlights:\n"
            "Najważniejsze wnioski z raportu."
        ),
    }

    parsed = parse_exa_item(item, "overview")

    assert len(parsed) == 1
    assert parsed[0].title == "Raport AI w Polsce"
    assert parsed[0].url == "https://www.example.pl/raport-ai?utm_source=test"
    assert parsed[0].normalized_url == "https://www.example.pl/raport-ai"
    assert parsed[0].domain == "example.pl"
    assert parsed[0].published == "2026-01-20T22:28:59.000Z"
    assert parsed[0].author == "Jan Kowalski"
    assert parsed[0].highlights == "Najważniejsze wnioski z raportu."


def test_parse_exa_item_splits_multiple_blocks() -> None:
    item = {
        "type": "text",
        "text": (
            "Title: Pierwszy wynik\n"
            "URL: https://example.com/one\n"
            "Published: N/A\n"
            "Author: N/A\n"
            "Highlights:\n"
            "Pierwszy opis.\n"
            "\n---\n\n"
            "Title: Drugi wynik\n"
            "URL: https://example.com/two\n"
            "Published: 2025-05-01T00:00:00.000Z\n"
            "Author: N/A\n"
            "Highlights:\n"
            "Drugi opis."
        ),
    }

    parsed = parse_exa_item(item, "overview")

    assert [source.title for source in parsed] == ["Pierwszy wynik", "Drugi wynik"]
    assert parsed[0].published is None
    assert parsed[1].published == "2025-05-01T00:00:00.000Z"


def test_dedupe_sources_uses_normalized_url() -> None:
    first = ParsedSource(
        query_label="overview",
        title="T1",
        url="https://example.com/a?utm_source=x",
        normalized_url=normalize_url("https://example.com/a?utm_source=x"),
        domain=extract_domain("https://example.com/a"),
        published=None,
        author=None,
        highlights="",
    )
    second = ParsedSource(
        query_label="stats",
        title="T2",
        url="https://example.com/a",
        normalized_url=normalize_url("https://example.com/a"),
        domain=extract_domain("https://example.com/a"),
        published=None,
        author=None,
        highlights="",
    )

    deduped = dedupe_sources([first, second])

    assert deduped == [first]


def test_evaluate_case_passes_with_warning_when_no_polish_domain() -> None:
    query_results = [
        QueryValidationResult(
            label="overview",
            query="q1",
            raw_result_count=2,
            parsed_result_count=2,
            error=None,
        ),
        QueryValidationResult(
            label="stats",
            query="q2",
            raw_result_count=2,
            parsed_result_count=2,
            error=None,
        ),
        QueryValidationResult(
            label="case-study",
            query="q3",
            raw_result_count=2,
            parsed_result_count=2,
            error=None,
        ),
    ]
    sources = [
        ParsedSource(
            query_label="overview",
            title="A",
            url="https://a.com/1",
            normalized_url="https://a.com/1",
            domain="a.com",
            published="2026-01-01T00:00:00+00:00",
            author=None,
            highlights="",
        ),
        ParsedSource(
            query_label="overview",
            title="B",
            url="https://b.com/1",
            normalized_url="https://b.com/1",
            domain="b.com",
            published="2025-01-01T00:00:00+00:00",
            author=None,
            highlights="",
        ),
        ParsedSource(
            query_label="stats",
            title="C",
            url="https://c.com/1",
            normalized_url="https://c.com/1",
            domain="c.com",
            published="2024-01-01T00:00:00+00:00",
            author=None,
            highlights="",
        ),
        ParsedSource(
            query_label="stats",
            title="D",
            url="https://d.com/1",
            normalized_url="https://d.com/1",
            domain="d.com",
            published=None,
            author=None,
            highlights="",
        ),
        ParsedSource(
            query_label="case-study",
            title="E",
            url="https://e.com/1",
            normalized_url="https://e.com/1",
            domain="e.com",
            published=None,
            author=None,
            highlights="",
        ),
        ParsedSource(
            query_label="case-study",
            title="F",
            url="https://f.com/1",
            normalized_url="https://f.com/1",
            domain="f.com",
            published=None,
            author=None,
            highlights="",
        ),
    ]

    result = evaluate_case(
        _case(),
        query_results,
        sources,
        duration_seconds=1.23,
    )

    assert result.status == "pass_with_warnings"
    assert result.unique_sources == 6
    assert result.unique_domains == 6
    assert result.polish_domains == 0
    assert result.recent_sources == 3
    assert result.failures == []
    assert "Brak domen .pl w deduplikowanych wynikach" in result.warnings
