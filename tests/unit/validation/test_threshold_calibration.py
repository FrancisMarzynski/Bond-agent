# ruff: noqa: E402

import sys

sys.modules.pop("bond.store.chroma", None)

from bond.validation.threshold_calibration import (
    LowCorpusMetric,
    SimilarityPair,
    recommend_duplicate_threshold,
    recommend_low_corpus_threshold,
)


def test_recommend_low_corpus_keeps_default_when_headroom_is_too_small():
    recommendation = recommend_low_corpus_threshold(
        current_threshold=10,
        total_articles=12,
        metrics=[
            LowCorpusMetric(
                article_count=8,
                query_family="topic_like",
                query_count=5,
                mean_coverage_ratio=1.0,
                mean_overlap_at_k=0.9,
                median_overlap_at_k=0.9,
                top1_match_rate=0.8,
                mean_top1_similarity=0.61,
            ),
            LowCorpusMetric(
                article_count=10,
                query_family="topic_like",
                query_count=5,
                mean_coverage_ratio=1.0,
                mean_overlap_at_k=0.95,
                median_overlap_at_k=1.0,
                top1_match_rate=1.0,
                mean_top1_similarity=0.64,
            ),
        ],
    )

    assert recommendation.recommended == 10
    assert recommendation.change_default is False
    assert "Lokalny korpus ma tylko 12 artykułów" in recommendation.rationale[0]


def test_recommend_low_corpus_keeps_default_when_no_stable_prefix_exists():
    recommendation = recommend_low_corpus_threshold(
        current_threshold=10,
        total_articles=18,
        metrics=[
            LowCorpusMetric(
                article_count=8,
                query_family="topic_like",
                query_count=5,
                mean_coverage_ratio=1.0,
                mean_overlap_at_k=0.65,
                median_overlap_at_k=0.6,
                top1_match_rate=0.6,
                mean_top1_similarity=0.52,
            ),
            LowCorpusMetric(
                article_count=10,
                query_family="topic_like",
                query_count=5,
                mean_coverage_ratio=1.0,
                mean_overlap_at_k=0.72,
                median_overlap_at_k=0.7,
                top1_match_rate=0.7,
                mean_top1_similarity=0.55,
            ),
        ],
    )

    assert recommendation.recommended == 10
    assert recommendation.change_default is False
    assert any("nie pojawił się wcześniejszy prefix" in item for item in recommendation.rationale)


def test_recommend_duplicate_keeps_default_when_sample_is_too_small():
    recommendation = recommend_duplicate_threshold(
        current_threshold=0.85,
        chroma_topic_count=3,
        extended_topic_count=16,
        pairs=[
            SimilarityPair(
                left_label="Temat A",
                left_origin="metadata_sqlite",
                right_label="Temat B",
                right_origin="corpus_title",
                similarity=0.64,
            ),
            SimilarityPair(
                left_label="Temat C",
                left_origin="corpus_title",
                right_label="Temat D",
                right_origin="corpus_title",
                similarity=0.58,
            ),
        ],
    )

    assert recommendation.recommended == 0.85
    assert recommendation.change_default is False
    assert recommendation.confidence == "niska"
    assert any("Kolekcja duplicate w Chroma ma tylko 3 temat" in item for item in recommendation.rationale)
