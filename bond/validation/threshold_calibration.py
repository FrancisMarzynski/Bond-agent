from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from bond.config import settings
from bond.store.article_log import get_article_count, get_articles, get_chunk_count
from bond.store.chroma import get_or_create_corpus_collection, get_or_create_metadata_collection

_EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
_DEFAULT_TOP_K = 5
_LOW_CORPUS_STABLE_OVERLAP = 0.8
_LOW_CORPUS_STABLE_TOP1 = 0.8
_DUPLICATE_BORDERLINE_MARGIN = 0.1
_DEFAULT_SMOKE_QUERY = "styl pisania storytelling angażujące treści"


@dataclass(frozen=True)
class ArticleRecord:
    article_id: str
    title: str
    source_type: str
    chunk_count_sqlite: int
    chunk_count_chroma: int
    ingested_at: str | None
    texts: tuple[str, ...]


@dataclass(frozen=True)
class QuerySample:
    label: str
    text: str
    family: str


@dataclass(frozen=True)
class LowCorpusMetric:
    article_count: int
    query_family: str
    query_count: int
    mean_coverage_ratio: float
    mean_overlap_at_k: float
    median_overlap_at_k: float
    top1_match_rate: float
    mean_top1_similarity: float


@dataclass(frozen=True)
class SimilarityPair:
    left_label: str
    left_origin: str
    right_label: str
    right_origin: str
    similarity: float


@dataclass(frozen=True)
class ThresholdRecommendation:
    current: float | int
    recommended: float | int
    change_default: bool
    confidence: str
    rationale: list[str]


@dataclass(frozen=True)
class LowCorpusAnalysis:
    current_threshold: int
    recommended_threshold: int
    change_default: bool
    confidence: str
    article_count: int
    chunk_count_sqlite: int
    chunk_count_chroma: int
    query_sets: dict[str, int]
    metrics: list[LowCorpusMetric]
    rationale: list[str]


@dataclass(frozen=True)
class DuplicateAnalysis:
    current_threshold: float
    recommended_threshold: float
    change_default: bool
    confidence: str
    sqlite_topic_count: int
    chroma_topic_count: int
    extended_topic_count: int
    nearest_neighbor_min: float
    nearest_neighbor_median: float
    nearest_neighbor_p90: float
    nearest_neighbor_max: float
    pairs_at_or_above: dict[str, int]
    borderline_band: list[SimilarityPair]
    top_pairs: list[SimilarityPair]
    rationale: list[str]


@dataclass(frozen=True)
class CalibrationReport:
    generated_at: str
    overall_status: str
    artifact_slug: str
    warnings: list[str]
    low_corpus: LowCorpusAnalysis
    duplicate_threshold: DuplicateAnalysis


def _timestamp_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _round(value: float) -> float:
    return round(float(value), 4)


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return _round(sum(values) / len(values))


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return _round(statistics.median(values))


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return _round(ordered[0])
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    interpolated = ordered[lower] * (1 - weight) + ordered[upper] * weight
    return _round(interpolated)


def _safe_split_chunk_id(chunk_id: str) -> tuple[str, int]:
    prefix, _, suffix = chunk_id.rpartition("_")
    if not prefix:
        return chunk_id, 0
    try:
        return prefix, int(suffix)
    except ValueError:
        return chunk_id, 0


@lru_cache(maxsize=1)
def _get_embedding_function() -> SentenceTransformerEmbeddingFunction:
    return SentenceTransformerEmbeddingFunction(
        model_name=_EMBEDDING_MODEL,
        device="cpu",
    )


def _normalized_embeddings(texts: Sequence[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 0), dtype=float)
    embeddings = np.asarray(_get_embedding_function()(list(texts)), dtype=float)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings / np.clip(norms, 1e-12, None)


def _load_sqlite_metadata_topics() -> list[str]:
    db_path = Path(settings.metadata_db_path)
    if not db_path.exists():
        return []

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT topic FROM metadata_log ORDER BY published_date ASC"
        ).fetchall()
    return [row[0] for row in rows if row and row[0]]


def _load_chroma_metadata_topics() -> list[str]:
    collection = get_or_create_metadata_collection()
    if collection.count() == 0:
        return []
    items = collection.get(include=["documents"])
    return [doc for doc in items.get("documents", []) if isinstance(doc, str) and doc]


def _load_corpus_articles() -> tuple[list[ArticleRecord], list[str]]:
    warnings: list[str] = []
    article_rows = sorted(
        get_articles(),
        key=lambda row: (row.get("ingested_at") or "", row.get("article_id") or ""),
    )

    collection = get_or_create_corpus_collection()
    items = collection.get(include=["documents", "metadatas"])

    grouped_chunks: dict[str, list[tuple[int, str]]] = defaultdict(list)
    known_article_ids = {row["article_id"] for row in article_rows}
    for chunk_id, text in zip(items.get("ids", []), items.get("documents", [])):
        if not isinstance(chunk_id, str) or not isinstance(text, str):
            continue
        article_id, chunk_index = _safe_split_chunk_id(chunk_id)
        grouped_chunks[article_id].append((chunk_index, text))
        if article_id not in known_article_ids:
            warnings.append(
                f"Chroma zawiera chunk dla nieznanego article_id `{article_id}`."
            )

    articles: list[ArticleRecord] = []
    for row in article_rows:
        article_id = row["article_id"]
        ordered_chunks = tuple(
            text for _, text in sorted(grouped_chunks.get(article_id, []), key=lambda pair: pair[0])
        )
        if not ordered_chunks:
            warnings.append(
                f"SQLite article log zawiera `{article_id}`, ale brak chunków w Chroma."
            )
        articles.append(
            ArticleRecord(
                article_id=article_id,
                title=row["title"],
                source_type=row["source_type"],
                chunk_count_sqlite=int(row["chunk_count"]),
                chunk_count_chroma=len(ordered_chunks),
                ingested_at=row.get("ingested_at"),
                texts=ordered_chunks,
            )
        )

    return articles, warnings


def _build_query_sets(
    articles: Sequence[ArticleRecord],
    metadata_topics: Sequence[str],
) -> dict[str, list[QuerySample]]:
    topic_like: list[QuerySample] = []
    seen_topic_like: set[str] = set()
    for index, topic in enumerate(metadata_topics, start=1):
        stripped = topic.strip()
        if not stripped or stripped in seen_topic_like:
            continue
        seen_topic_like.add(stripped)
        topic_like.append(
            QuerySample(
                label=f"published-topic-{index}",
                text=stripped,
                family="topic_like",
            )
        )

    if _DEFAULT_SMOKE_QUERY not in seen_topic_like:
        topic_like.append(
            QuerySample(
                label="smoke-default",
                text=_DEFAULT_SMOKE_QUERY,
                family="topic_like",
            )
        )

    title_like = [
        QuerySample(
            label=f"article-title-{index}",
            text=article.title,
            family="title_like",
        )
        for index, article in enumerate(articles, start=1)
        if article.title.strip()
    ]

    return {
        "topic_like": topic_like,
        "title_like": title_like,
    }


def _build_article_chunk_embeddings(
    articles: Sequence[ArticleRecord],
) -> dict[str, np.ndarray]:
    chunk_vectors: dict[str, np.ndarray] = {}
    for article in articles:
        if not article.texts:
            chunk_vectors[article.article_id] = np.zeros((0, 0), dtype=float)
            continue
        chunk_vectors[article.article_id] = _normalized_embeddings(article.texts)
    return chunk_vectors


def _rank_articles_for_query(
    query_embedding: np.ndarray,
    articles: Sequence[ArticleRecord],
    chunk_vectors: dict[str, np.ndarray],
    *,
    top_k: int,
) -> list[tuple[str, float]]:
    ranked: list[tuple[str, float]] = []
    for article in articles:
        article_matrix = chunk_vectors.get(article.article_id)
        if article_matrix is None or article_matrix.size == 0:
            continue
        similarity = float(np.max(article_matrix @ query_embedding))
        ranked.append((article.article_id, similarity))

    ranked.sort(key=lambda pair: (-pair[1], pair[0]))
    return ranked[:top_k]


def _compute_overlap(
    full_rank: Sequence[str],
    prefix_rank: Sequence[str],
) -> tuple[float, float]:
    if not full_rank or not prefix_rank:
        return 0.0, 0.0
    denominator = max(1, min(len(full_rank), len(prefix_rank)))
    overlap = len(set(full_rank) & set(prefix_rank)) / denominator
    coverage = len(prefix_rank) / max(1, len(full_rank))
    return _round(overlap), _round(coverage)


def evaluate_low_corpus_metrics(
    articles: Sequence[ArticleRecord],
    query_sets: dict[str, list[QuerySample]],
    *,
    top_k: int = _DEFAULT_TOP_K,
) -> list[LowCorpusMetric]:
    if not articles:
        return []

    chunk_vectors = _build_article_chunk_embeddings(articles)
    all_queries = [query for queries in query_sets.values() for query in queries]
    query_embeddings = _normalized_embeddings([query.text for query in all_queries])
    query_vectors = {
        query.label: query_embeddings[index]
        for index, query in enumerate(all_queries)
    }

    metrics: list[LowCorpusMetric] = []
    for prefix_size in range(3, len(articles) + 1):
        prefix_articles = articles[:prefix_size]
        for family, queries in query_sets.items():
            overlaps: list[float] = []
            coverages: list[float] = []
            top1_matches: list[float] = []
            top1_scores: list[float] = []

            for query in queries:
                query_vector = query_vectors[query.label]
                full_rank = _rank_articles_for_query(
                    query_vector,
                    articles,
                    chunk_vectors,
                    top_k=top_k,
                )
                prefix_rank = _rank_articles_for_query(
                    query_vector,
                    prefix_articles,
                    chunk_vectors,
                    top_k=top_k,
                )
                full_ids = [article_id for article_id, _ in full_rank]
                prefix_ids = [article_id for article_id, _ in prefix_rank]
                overlap, coverage = _compute_overlap(full_ids, prefix_ids)
                overlaps.append(overlap)
                coverages.append(coverage)
                top1_matches.append(
                    1.0 if full_ids and prefix_ids and full_ids[0] == prefix_ids[0] else 0.0
                )
                top1_scores.append(prefix_rank[0][1] if prefix_rank else 0.0)

            metrics.append(
                LowCorpusMetric(
                    article_count=prefix_size,
                    query_family=family,
                    query_count=len(queries),
                    mean_coverage_ratio=_mean(coverages),
                    mean_overlap_at_k=_mean(overlaps),
                    median_overlap_at_k=_median(overlaps),
                    top1_match_rate=_mean(top1_matches),
                    mean_top1_similarity=_mean(top1_scores),
                )
            )

    return metrics


def recommend_low_corpus_threshold(
    *,
    current_threshold: int,
    total_articles: int,
    metrics: Sequence[LowCorpusMetric],
) -> ThresholdRecommendation:
    rationale: list[str] = []
    topic_like_metrics = sorted(
        (metric for metric in metrics if metric.query_family == "topic_like"),
        key=lambda metric: metric.article_count,
    )

    stable_prefix = None
    for metric in topic_like_metrics:
        if (
            metric.mean_coverage_ratio >= 1.0
            and metric.mean_overlap_at_k >= _LOW_CORPUS_STABLE_OVERLAP
            and metric.top1_match_rate >= _LOW_CORPUS_STABLE_TOP1
        ):
            stable_prefix = metric.article_count
            break

    if total_articles <= current_threshold + 2:
        rationale.append(
            f"Lokalny korpus ma tylko {total_articles} artykułów, czyli zaledwie o "
            f"{total_articles - current_threshold} więcej niż obecny próg {current_threshold}."
        )

    if stable_prefix is None:
        rationale.append(
            "W dostępnej próbie nie pojawił się wcześniejszy prefix, który stabilnie "
            "odtwarza top-5 sąsiedztwo pełnego korpusu dla zapytań topic-like."
        )
    else:
        rationale.append(
            f"Zapytania topic-like osiągają stabilne pokrycie i zgodność top-1 dopiero "
            f"przy około {stable_prefix} artykułach."
        )

    if stable_prefix is None or stable_prefix >= current_threshold or total_articles <= current_threshold + 2:
        return ThresholdRecommendation(
            current=current_threshold,
            recommended=current_threshold,
            change_default=False,
            confidence="umiarkowana",
            rationale=rationale
            + [
                "Obniżenie progu na podstawie obecnych danych byłoby zbyt agresywne; "
                "zostawiam domyślną wartość bez zmian."
            ],
        )

    return ThresholdRecommendation(
        current=current_threshold,
        recommended=stable_prefix,
        change_default=stable_prefix != current_threshold,
        confidence="niska",
        rationale=rationale
        + [
            "Próba wskazuje możliwy niższy próg, ale rekomendacja zmiany powinna być "
            "potwierdzona na większym korpusie niż obecne lokalne 12 artykułów."
        ],
    )


def _extended_topic_pool(
    sqlite_topics: Sequence[str],
    corpus_titles: Sequence[str],
) -> list[tuple[str, str]]:
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for topic in sqlite_topics:
        stripped = topic.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        ordered.append((stripped, "metadata_sqlite"))
    for title in corpus_titles:
        stripped = title.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        ordered.append((stripped, "corpus_title"))
    return ordered


def compute_similarity_pairs(topic_pool: Sequence[tuple[str, str]]) -> list[SimilarityPair]:
    if len(topic_pool) < 2:
        return []

    labels = [label for label, _ in topic_pool]
    origins = [origin for _, origin in topic_pool]
    vectors = _normalized_embeddings(labels)

    pairs: list[SimilarityPair] = []
    for left_index in range(len(labels)):
        for right_index in range(left_index + 1, len(labels)):
            similarity = float(vectors[left_index] @ vectors[right_index])
            pairs.append(
                SimilarityPair(
                    left_label=labels[left_index],
                    left_origin=origins[left_index],
                    right_label=labels[right_index],
                    right_origin=origins[right_index],
                    similarity=_round(similarity),
                )
            )

    pairs.sort(key=lambda pair: (-pair.similarity, pair.left_label, pair.right_label))
    return pairs


def recommend_duplicate_threshold(
    *,
    current_threshold: float,
    chroma_topic_count: int,
    extended_topic_count: int,
    pairs: Sequence[SimilarityPair],
) -> ThresholdRecommendation:
    rationale: list[str] = []
    lower_bound = max(0.0, current_threshold - _DUPLICATE_BORDERLINE_MARGIN)
    upper_bound = min(1.0, current_threshold + 0.05)
    borderline_pairs = [
        pair
        for pair in pairs
        if lower_bound <= pair.similarity <= upper_bound
    ]

    if chroma_topic_count < 8:
        rationale.append(
            f"Kolekcja duplicate w Chroma ma tylko {chroma_topic_count} temat(y), "
            "więc realna próba produkcyjna jest za mała do przesuwania progu."
        )
    if borderline_pairs:
        rationale.append(
            f"W rozszerzonej lokalnej puli ({extended_topic_count} tematów/tytułów) jest tylko "
            f"{len(borderline_pairs)} para(y) w paśmie {lower_bound:.2f}-{upper_bound:.2f} "
            f"wokół bieżącego progu {current_threshold:.2f}."
        )
    else:
        rationale.append(
            f"W rozszerzonej lokalnej puli ({extended_topic_count} tematów/tytułów) nie ma "
            f"par podobieństw w paśmie {lower_bound:.2f}-{upper_bound:.2f} wokół bieżącego "
            f"progu {current_threshold:.2f}."
        )

    return ThresholdRecommendation(
        current=current_threshold,
        recommended=current_threshold,
        change_default=False,
        confidence="niska" if chroma_topic_count < 8 else "umiarkowana",
        rationale=rationale
        + [
            "Brak oznaczonych ręcznie duplikatów i brak gęstości punktów granicznych oznacza, "
            "że zmiana defaultu byłaby zgadywaniem."
        ],
    )


def _nearest_neighbor_stats(
    topic_pool: Sequence[tuple[str, str]],
    pairs: Sequence[SimilarityPair],
) -> tuple[float, float, float, float]:
    if len(topic_pool) < 2 or not pairs:
        return 0.0, 0.0, 0.0, 0.0

    best_by_label: dict[str, float] = {label: 0.0 for label, _ in topic_pool}
    for pair in pairs:
        best_by_label[pair.left_label] = max(best_by_label[pair.left_label], pair.similarity)
        best_by_label[pair.right_label] = max(best_by_label[pair.right_label], pair.similarity)

    values = list(best_by_label.values())
    return (
        _round(min(values)),
        _median(values),
        _percentile(values, 0.9),
        _round(max(values)),
    )


def _pairs_at_or_above(pairs: Sequence[SimilarityPair]) -> dict[str, int]:
    thresholds = (0.7, 0.75, 0.8, 0.85, 0.9)
    return {
        f"{threshold:.2f}": sum(1 for pair in pairs if pair.similarity >= threshold)
        for threshold in thresholds
    }


def build_report() -> CalibrationReport:
    artifact_slug = f"threshold-calibration-{_timestamp_slug()}"
    warnings: list[str] = []

    articles, article_warnings = _load_corpus_articles()
    warnings.extend(article_warnings)

    sqlite_topics = _load_sqlite_metadata_topics()
    chroma_topics = _load_chroma_metadata_topics()
    if len(sqlite_topics) != len(chroma_topics):
        warnings.append(
            f"SQLite metadata_log ma {len(sqlite_topics)} temat(y), a kolekcja Chroma duplicate "
            f"ma {len(chroma_topics)} embeddingów."
        )

    query_sets = _build_query_sets(articles, sqlite_topics or chroma_topics)
    low_corpus_metrics = evaluate_low_corpus_metrics(articles, query_sets)
    low_corpus_recommendation = recommend_low_corpus_threshold(
        current_threshold=settings.low_corpus_threshold,
        total_articles=len(articles),
        metrics=low_corpus_metrics,
    )

    extended_topics = _extended_topic_pool(
        sqlite_topics=sqlite_topics,
        corpus_titles=[article.title for article in articles],
    )
    similarity_pairs = compute_similarity_pairs(extended_topics)
    duplicate_recommendation = recommend_duplicate_threshold(
        current_threshold=settings.duplicate_threshold,
        chroma_topic_count=len(chroma_topics),
        extended_topic_count=len(extended_topics),
        pairs=similarity_pairs,
    )
    nn_min, nn_median, nn_p90, nn_max = _nearest_neighbor_stats(
        extended_topics,
        similarity_pairs,
    )

    low_corpus = LowCorpusAnalysis(
        current_threshold=settings.low_corpus_threshold,
        recommended_threshold=int(low_corpus_recommendation.recommended),
        change_default=low_corpus_recommendation.change_default,
        confidence=low_corpus_recommendation.confidence,
        article_count=get_article_count(),
        chunk_count_sqlite=get_chunk_count(),
        chunk_count_chroma=sum(article.chunk_count_chroma for article in articles),
        query_sets={family: len(queries) for family, queries in query_sets.items()},
        metrics=low_corpus_metrics,
        rationale=low_corpus_recommendation.rationale,
    )

    lower_bound = max(0.0, settings.duplicate_threshold - _DUPLICATE_BORDERLINE_MARGIN)
    upper_bound = min(1.0, settings.duplicate_threshold + 0.05)
    duplicate = DuplicateAnalysis(
        current_threshold=settings.duplicate_threshold,
        recommended_threshold=float(duplicate_recommendation.recommended),
        change_default=duplicate_recommendation.change_default,
        confidence=duplicate_recommendation.confidence,
        sqlite_topic_count=len(sqlite_topics),
        chroma_topic_count=len(chroma_topics),
        extended_topic_count=len(extended_topics),
        nearest_neighbor_min=nn_min,
        nearest_neighbor_median=nn_median,
        nearest_neighbor_p90=nn_p90,
        nearest_neighbor_max=nn_max,
        pairs_at_or_above=_pairs_at_or_above(similarity_pairs),
        borderline_band=[
            pair for pair in similarity_pairs if lower_bound <= pair.similarity <= upper_bound
        ][:10],
        top_pairs=list(similarity_pairs[:10]),
        rationale=duplicate_recommendation.rationale,
    )

    return CalibrationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        overall_status="pass",
        artifact_slug=artifact_slug,
        warnings=warnings,
        low_corpus=low_corpus,
        duplicate_threshold=duplicate,
    )


def render_markdown(report: CalibrationReport) -> str:
    lines = [
        "# Threshold Calibration",
        "",
        f"Wygenerowano: {report.generated_at}",
        "",
        "## Snapshot danych",
        "",
        "| Miara | Wartość |",
        "|------|---------|",
        f"| `articles.db` article_count | `{report.low_corpus.article_count}` |",
        f"| `articles.db` chunk_count | `{report.low_corpus.chunk_count_sqlite}` |",
        f"| Chroma corpus chunk_count | `{report.low_corpus.chunk_count_chroma}` |",
        f"| SQLite metadata topics | `{report.duplicate_threshold.sqlite_topic_count}` |",
        f"| Chroma duplicate topics | `{report.duplicate_threshold.chroma_topic_count}` |",
        f"| Extended local topic/title pool | `{report.duplicate_threshold.extended_topic_count}` |",
        "",
        "## Rekomendacje",
        "",
        f"- `low_corpus_threshold`: `{report.low_corpus.current_threshold}` -> "
        f"`{report.low_corpus.recommended_threshold}` "
        f"(`change_default={str(report.low_corpus.change_default).lower()}`, "
        f"confidence={report.low_corpus.confidence})",
        f"- `duplicate_threshold`: `{report.duplicate_threshold.current_threshold:.2f}` -> "
        f"`{report.duplicate_threshold.recommended_threshold:.2f}` "
        f"(`change_default={str(report.duplicate_threshold.change_default).lower()}`, "
        f"confidence={report.duplicate_threshold.confidence})",
        "",
        "## Low Corpus",
        "",
        f"Zapytania użyte do oceny: topic-like=`{report.low_corpus.query_sets.get('topic_like', 0)}`, "
        f"title-like=`{report.low_corpus.query_sets.get('title_like', 0)}`.",
        "",
        "| Articles | Family | Coverage | Overlap@5 | Median overlap | Top1 match | Mean top1 sim |",
        "|----------|--------|----------|-----------|----------------|------------|---------------|",
    ]

    for metric in report.low_corpus.metrics:
        lines.append(
            f"| `{metric.article_count}` | `{metric.query_family}` | "
            f"`{metric.mean_coverage_ratio:.4f}` | `{metric.mean_overlap_at_k:.4f}` | "
            f"`{metric.median_overlap_at_k:.4f}` | `{metric.top1_match_rate:.4f}` | "
            f"`{metric.mean_top1_similarity:.4f}` |"
        )

    lines.extend(
        [
            "",
            "Wnioski:",
            *[f"- {item}" for item in report.low_corpus.rationale],
            "",
            "## Duplicate Threshold",
            "",
            "| Statystyka | Wartość |",
            "|------------|---------|",
            f"| nearest-neighbor min | `{report.duplicate_threshold.nearest_neighbor_min:.4f}` |",
            f"| nearest-neighbor median | `{report.duplicate_threshold.nearest_neighbor_median:.4f}` |",
            f"| nearest-neighbor p90 | `{report.duplicate_threshold.nearest_neighbor_p90:.4f}` |",
            f"| nearest-neighbor max | `{report.duplicate_threshold.nearest_neighbor_max:.4f}` |",
        ]
    )

    for threshold, count in report.duplicate_threshold.pairs_at_or_above.items():
        lines.append(f"| pairs >= {threshold} | `{count}` |")

    lines.extend(
        [
            "",
            "Najwyższe pary podobieństwa:",
            *[
                f"- `{pair.similarity:.4f}` — {pair.left_label} [{pair.left_origin}] <> "
                f"{pair.right_label} [{pair.right_origin}]"
                for pair in report.duplicate_threshold.top_pairs
            ],
            "",
            "Wnioski:",
            *[f"- {item}" for item in report.duplicate_threshold.rationale],
        ]
    )

    if report.warnings:
        lines.extend(
            [
                "",
                "## Ostrzeżenia",
                "",
                *[f"- {warning}" for warning in report.warnings],
            ]
        )

    return "\n".join(lines) + "\n"


def write_artifacts(
    report: CalibrationReport,
    *,
    artifact_root: Path,
) -> tuple[Path, Path]:
    artifact_dir = artifact_root / report.artifact_slug
    artifact_dir.mkdir(parents=True, exist_ok=True)

    json_path = artifact_dir / "summary.json"
    markdown_path = artifact_dir / "summary.md"

    json_path.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Skalibruj progi low corpus i duplicate similarity na lokalnych danych repo.",
    )
    parser.add_argument(
        "--artifact-root",
        default=".planning/artifacts",
        help="Katalog bazowy na artefakty kalibracji.",
    )
    args = parser.parse_args(argv)

    report = build_report()
    json_path, markdown_path = write_artifacts(
        report,
        artifact_root=Path(args.artifact_root),
    )
    print(json_path)
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
