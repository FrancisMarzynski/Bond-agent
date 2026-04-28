import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from bond.prompts.research_context import (
    RESEARCH_CONTEXT_OMISSION_MARKER,
    iter_research_context_variants,
)


def _research_data() -> dict:
    return {
        "fakty": [
            "FAKT_ALPHA: Automatyzacja skraca czas przygotowania publikacji.",
            "FAKT_OMEGA: Redakcja dalej wymaga akceptacji człowieka.",
        ],
        "statystyki": [
            "STAT_01: 42% - firmy przyspieszają publikację po standaryzacji procesu.",
            "STAT_TAIL: 93% - zespoły lepiej oceniają jakość przy kontroli redakcyjnej.",
        ],
        "zrodla": [
            {
                "title": "Źródło 1",
                "url": "https://example.com/1",
                "summary": "SUMMARY_1: Wczesne źródło testowe.",
            },
            {
                "title": "Źródło 2",
                "url": "https://example.com/2",
                "summary": "SUMMARY_2: Środkowe źródło testowe.",
            },
            {
                "title": "Źródło 3",
                "url": "https://example.com/3",
                "summary": "SUMMARY_TAIL: Późne źródło testowe do regresji.",
            },
        ],
    }


def test_full_report_variant_is_offered_first():
    report = "Pełny raport z badań.\n" + ("Wstęp " * 400) + "REPORT_TAIL_SENTINEL"

    variants = iter_research_context_variants(report, _research_data())

    assert variants[0].kind == "full_report"
    assert variants[0].content == report


def test_structured_variants_preserve_all_facts_and_statistics():
    variants = iter_research_context_variants("Krótki raport", _research_data())
    structured_variants = variants[1:]

    assert structured_variants
    for variant in structured_variants:
        assert "FAKT_ALPHA" in variant.content
        assert "FAKT_OMEGA" in variant.content
        assert "STAT_01" in variant.content
        assert "STAT_TAIL" in variant.content


def test_source_compaction_reduces_sources_before_dropping_core_sections():
    variants = iter_research_context_variants("Krótki raport", _research_data())
    structured_variants = variants[1:]

    assert [variant.source_count for variant in structured_variants] == [3, 2, 1, 0]
    assert "Źródło 3" in structured_variants[0].content
    assert "Źródło 3" not in structured_variants[1].content
    assert "FAKT_ALPHA" in structured_variants[-1].content
    assert "STAT_TAIL" in structured_variants[-1].content


def test_final_fallback_uses_explicit_omission_marker_instead_of_raw_substring():
    report = ("PREFIKS " * 500) + "REPORT_TAIL_SENTINEL"

    final_variant = iter_research_context_variants(report, _research_data())[-1]

    assert final_variant.kind == "structured_core_only"
    assert RESEARCH_CONTEXT_OMISSION_MARKER in final_variant.content
    assert "REPORT_TAIL_SENTINEL" not in final_variant.content
    assert "SUMMARY_TAIL" not in final_variant.content
