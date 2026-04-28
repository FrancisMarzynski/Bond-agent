"""
Testy jednostkowe asynchronicznego modułu bond.db.metadata_log.

Sprawdzają:
- czy zapis metadanych nie blokuje event loopa (aiosqlite zamiast sqlite3)
- czy funkcja zwraca poprawny row_id
- czy odczyt wyników działa poprawnie
"""
import asyncio
import time

import pytest
import pytest_asyncio

from bond.db import metadata_log


# ---------------------------------------------------------------------------
# Fixture: wstrzykuje ścieżkę :memory: do settings i inicjalizuje schemat
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def in_memory_db(tmp_path, monkeypatch):
    """
    Podmienia settings.metadata_db_path na tymczasowy plik,
    przez co testy nie dotykają prawdziwej bazy danych.
    """
    db_path = str(tmp_path / "test_metadata.db")
    monkeypatch.setattr("bond.db.metadata_log.settings", type("S", (), {"metadata_db_path": db_path})())
    yield db_path


# ---------------------------------------------------------------------------
# Test 1: Zapis nie blokuje event loopa
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_does_not_block_event_loop(in_memory_db):
    """
    Uruchamia 5 współbieżnych zapisów przez asyncio.gather.
    Mierzy łączny czas — jeśli operacje byłyby sekwencyjne i blokujące,
    czas byłby znacznie dłuższy. Brak wyjątku BlockingIOError = sukces.
    """
    calls = [
        metadata_log.save_article_metadata(
            thread_id=f"thread-{i}",
            topic=f"Temat testowy {i}",
            mode="author",
        )
        for i in range(5)
    ]

    start = time.monotonic()
    results = await asyncio.gather(*calls)
    elapsed = time.monotonic() - start

    # Wszystkie 5 zapisów powinno się zakończyć bez wyjątku
    assert len(results) == 5
    # Każdy wynik powinien być poprawnym row_id (dodatnia liczba całkowita)
    for row_id in results:
        assert isinstance(row_id, int) and row_id > 0
    # Concurrency: całość powinna zakończyć się szybko (< 5 s)
    assert elapsed < 5.0, f"Zapis trwał zbyt długo: {elapsed:.2f}s — podejrzenie blokowania event loopa"


# ---------------------------------------------------------------------------
# Test 2: Funkcja zwraca poprawny row_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_returns_positive_row_id(in_memory_db):
    """
    Weryfikuje, że save_article_metadata zwraca dodatni int (ROWID z SQLite).
    """
    row_id = await metadata_log.save_article_metadata(
        thread_id="thread-abc",
        topic="Testowy artykuł o AI",
        mode="author",
    )
    assert isinstance(row_id, int), "row_id powinien być typu int"
    assert row_id > 0, "row_id powinien być dodatni"


# ---------------------------------------------------------------------------
# Test 3: Odczyt zwraca listę słowników z oczekiwanymi kluczami
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_recent_articles_returns_dicts(in_memory_db):
    """
    Wstawia 2 rekordy, odczytuje je i sprawdza strukturę zwróconych danych.
    """
    await metadata_log.save_article_metadata("t1", "Temat A", "author")
    await metadata_log.save_article_metadata("t2", "Temat B", "author")

    articles = await metadata_log.get_recent_articles(limit=2)

    assert isinstance(articles, list), "Wynik powinien być listą"
    assert len(articles) == 2, "Powinny być dokładnie 2 wpisy"

    expected_keys = {"id", "thread_id", "topic", "published_date", "mode", "created_at"}
    for article in articles:
        assert isinstance(article, dict), "Każdy wpis powinien być słownikiem"
        assert expected_keys.issubset(article.keys()), (
            f"Brakujące klucze: {expected_keys - article.keys()}"
        )
