# 38-FLASHRANK-RERANKER Podsumowanie: Integracja rerankingu wzorców stylistycznych RAG

**Data ukończenia:** 2026-04-17  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 38 — Writer: FlashRank Reranker Integration  
**Status:** ✅ Zakończone

---

## Cel

Precyzyjniejszy dobór wzorców stylistycznych dla węzła `writer_node` niż przez Cosine Similarity.

- Zamiast zwracać Top-5 fragmentów z ChromaDB bezpośrednio po cosine similarity, pobieramy 15 kandydatów i przepuszczamy przez cross-encoder (FlashRank) — model ocenia parę (zapytanie, fragment) łącznie, a nie jako niezależne wektory.
- Model `ms-marco-MultiBERT-L-12` obsługuje języki wielojęzyczne, w tym polski.

---

## Architektura

```
writer_node(state)
    │
    └─ _fetch_rag_exemplars(topic, n=5)
            │
            ├─ 1. ChromaDB cosine query (fetch_n = min(15, corpus_count))
            │      ├─ Pass 1: source_type="own"  → own_docs
            │      └─ Pass 2 (fallback): all sources → candidates
            │
            ├─ 2. Guard: len(candidates) <= n  → zwróć bez rerankingu
            │
            └─ 3. FlashRank rerank(query=topic, passages=candidates)
                    │
                    ├─ _get_ranker() — singleton Ranker("ms-marco-MultiBERT-L-12")
                    └─ ranked[:5] → list[str]  (posortowane malejąco po score)
```

---

## Zmodyfikowane pliki

### `pyproject.toml`

Dodano zależność:

```toml
"flashrank>=0.0.8",
```

Zainstalowana wersja: `flashrank==0.2.10`.

### `bond/graph/nodes/writer.py`

#### Stałe i singleton (nowe)

```python
_RERANK_FETCH_N = 15  # Candidates fetched before reranking

_ranker = None  # Module-level singleton

def _get_ranker():
    global _ranker
    if _ranker is None:
        from flashrank import Ranker
        _ranker = Ranker(model_name="ms-marco-MultiBERT-L-12", cache_dir="/tmp/flashrank")
    return _ranker

def _rerank(query: str, candidates: list[str], top_n: int) -> list[str]:
    from flashrank import RerankRequest
    passages = [{"id": i, "text": doc} for i, doc in enumerate(candidates)]
    request = RerankRequest(query=query, passages=passages)
    ranked = _get_ranker().rerank(request)
    return [r["text"] for r in ranked[:top_n]]
```

#### `_fetch_rag_exemplars` (zaktualizowane)

Kluczowe zmiany względem poprzedniej wersji:

| Aspekt | Przed | Po |
|--------|-------|----|
| Liczba kandydatów z ChromaDB | `n` (5) | `min(15, corpus_count)` |
| Rerankowanie | brak | FlashRank cross-encoder |
| Model | — | `ms-marco-MultiBERT-L-12` (multilingual) |
| Fallback | — | cosine order przy błędzie reranku |

Guard przed rerankowaniem: jeśli `len(candidates) <= n`, pomijamy rerankowanie (nie ma z czego wybierać).

```python
fetch_n = min(_RERANK_FETCH_N, collection.count())
# ... query ChromaDB with fetch_n ...
if len(candidates) <= n:
    return candidates[:n]
try:
    return _rerank(topic, candidates, top_n=n)
except Exception as exc:
    log.warning("FlashRank reranking failed, using cosine order: %s", exc)
    return candidates[:n]
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| `flashrank` w `pyproject.toml` | ✅ `flashrank>=0.0.8` dodane; zainstalowano `0.2.10` |
| Rerankowanie w `_fetch_rag_exemplars()` | ✅ Fetch 15 → FlashRank → top-5 |
| Obsługa języka polskiego | ✅ Model `ms-marco-MultiBERT-L-12` (multilingual) |
| Singleton — model ładowany raz | ✅ `_ranker` na poziomie modułu, `_get_ranker()` lazy init |
| Graceful fallback | ✅ Wyjątek reranku → `log.warning` + cosine order |

---

## Weryfikacja

Zweryfikowano programatycznie:

```
_RERANK_FETCH_N = 15  ✅

# Reranker poprawnie sortuje polskie dokumenty:
_rerank("jak pisać angażujące treści marketingowe", [...], top_n=2)
→ ['Artykuł o marketingu treści', 'SEO i pozycjonowanie stron']  ✅

# _fetch_rag_exemplars zwraca 5 fragmentów z live corpus (10 artykułów):
exemplars[0] = 'Storytelling w marketingu to potężne narzędzie...'  ✅
exemplars[1] = 'Automatyzacja marketingu kojarzyła się kiedyś...'  ✅
... (5 fragmentów łącznie)  ✅
```

Singleton `_ranker` ładuje model jednokrotnie — brak narzutu na kolejne wywołania `writer_node`.
