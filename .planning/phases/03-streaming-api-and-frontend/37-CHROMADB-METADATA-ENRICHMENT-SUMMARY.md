# 37-CHROMADB-METADATA-ENRICHMENT Podsumowanie: Wzbogacenie metadanych fragmentów RAG

**Data ukończenia:** 2026-04-17  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 37 — Ingestion: ChromaDB Metadata Update  
**Status:** ✅ Zakończone

---

## Cel

Wzbogacenie bazy RAG (ChromaDB) o kontekst pozycyjny fragmentów artykułów.

- Każdy chunk przechowywany w kolekcji `bond_style_corpus_v1` zawiera teraz pole `section_type` (`"wstęp"` / `"rozwinięcie"`) wskazujące, z której części artykułu pochodzi.
- Dodano pole `article_type` (wartość analogiczna do `source_type`) dla jednoznacznej klasyfikacji artykułu na poziomie metadanych.
- Przeprowadzono migrację wszystkich istniejących chunków (10 sztuk w korpusie testowym) — bez przebudowy embeddingów.

---

## Architektura

```
CorpusIngestor.ingest(text, title, source_type, source_url)
    │
    ├─ chunk_article(text) → [chunk_0, chunk_1, ..., chunk_n]
    │
    └─ dla każdego chunk_i:
           section_type = "wstęp"        jeśli i == 0
                        = "rozwinięcie"  jeśli i >= 1
           article_type = source_type    ("own" | "external")
           → ChromaDB.add(document, metadata, id="{article_id}_{i}")

scripts/reindex_corpus.py  (migracja jednorazowa)
    │
    ├─ collection.get(include=["metadatas", "documents"]) → wszystkie chunki
    ├─ dla każdego chunk_id: parsuj indeks z sufiksu "_N"
    ├─ setdefault("section_type", ...) + setdefault("article_type", ...)
    └─ collection.update(ids, metadatas)  — aktualizuje bez re-embeddingu
```

---

## Zmodyfikowane pliki

### `bond/corpus/ingestor.py`

Dodano funkcję pomocniczą `_section_type(chunk_index: int) -> str` oraz dwa nowe pola metadanych w każdym chunku:

```python
def _section_type(chunk_index: int) -> str:
    return "wstęp" if chunk_index == 0 else "rozwinięcie"

metadatas = [
    {
        "source_type": source_type,
        "article_type": source_type,      # ← NOWE
        "article_id": article_id,
        "article_title": title,
        "source_url": source_url,
        "ingested_at": now,
        "section_type": _section_type(i), # ← NOWE
    }
    for i, _ in enumerate(chunks)
]
```

Zmiana w pętli generującej metadane: `for _ in chunks` → `for i, _ in enumerate(chunks)` — indeks `i` jest potrzebny do wyznaczenia `section_type`.

---

## Nowe pliki

### `scripts/reindex_corpus.py`

Skrypt migracyjny do jednorazowego uzupełnienia metadanych w istniejącej kolekcji ChromaDB.

**Tryb dry-run (domyślny):**
```bash
uv run python scripts/reindex_corpus.py
```
Wyświetla statystyki: ile chunków wymaga aktualizacji, rozkład `section_type`.

**Tryb apply:**
```bash
uv run python scripts/reindex_corpus.py --apply
```
Aktualizuje metadane w batachach po 500 chunków. Nie modyfikuje embeddingów — tylko pola `metadata` w ChromaDB.

**Logika określania sekcji z ID chunku:**
```python
def _parse_chunk_index(chunk_id: str) -> int:
    # format: "{uuid}_{i}" → rsplit("_", 1) → index
    return int(chunk_id.rsplit("_", 1)[-1])
```

> ⚠️ **KONTRAKT-KRYTYCZNE:** `_parse_chunk_index` opiera się na sufixie `_N` w ID chunku. Format ID w `ingestor.py` (`{uuid}_{index}`) jest umową między ingestorem a skryptem migracyjnym. Zmiana formatu ID w `ingestor.py` bez aktualizacji tego skryptu spowoduje jego błędne działanie.

Skrypt jest idempotentny: chunki z już ustawionymi polami `section_type` i `article_type` są pomijane.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Pole `section_type` w metadanych każdego nowego chunku | ✅ Dodane w `ingestor.py`; wartości: `"wstęp"` (chunk 0) / `"rozwinięcie"` (chunk 1+) |
| Pole `article_type` w metadanych każdego nowego chunku | ✅ Dodane w `ingestor.py`; wartość równa `source_type` (`"own"` / `"external"`) |
| Skrypt migracyjny dla istniejącego korpusu | ✅ `scripts/reindex_corpus.py` — tryb dry-run + `--apply`; idempotentny |
| Ponowne zindeksowanie korpusu testowego | ✅ 10 istniejących chunków zaktualizowanych bez przebudowy embeddingów |
| Retriever zwraca nowe pola | ✅ Bez zmian w `retriever.py` — `entry.update(meta)` automatycznie propaguje nowe pola |

---

## Schemat metadanych chunku (po migracji)

```json
{
  "source_type":   "own" | "external",
  "article_type":  "own" | "external",
  "article_id":    "<uuid>",
  "article_title": "<tytuł artykułu>",
  "source_url":    "<url lub pusty string>",
  "ingested_at":   "<ISO8601>",
  "section_type":  "wstęp" | "rozwinięcie"
}
```

---

## Weryfikacja

Przeprowadzono weryfikację programatyczną:

```
_section_type(0) == "wstęp"       ✅
_section_type(1) == "rozwinięcie"  ✅
_section_type(5) == "rozwinięcie"  ✅
```

Zweryfikowano poprawność migracji (sample z ChromaDB):

```
8a5772e5-..._0 → section_type=wstęp  article_type=own  ✅
6c3628f1-..._0 → section_type=wstęp  article_type=own  ✅
acdea4a4-..._0 → section_type=wstęp  article_type=own  ✅
```

Korpus testowy (10 artykułów jednochunkowych) w pełni zmigrowany.  
Nowe ingestowanie artykułów wielochunkowych produkuje prawidłowy rozkład `wstęp/rozwinięcie` (zweryfikowane na artykule 20-chunkowym).
