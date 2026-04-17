# 39-FEW-SHOT-LABELS Podsumowanie: Prompt Engineering — etykiety metadanych RAG

**Data ukończenia:** 2026-04-17  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 39 — Writer: Prompt Engineering (Few-Shot labels)  
**Status:** ✅ Zakończone

---

## Cel

Nauczenie modelu korzystania z metadanych RAG przy generowaniu draftu.

- Każdy fragment few-shot w sekcji `WZORCE STYLISTYCZNE` jest teraz opatrzony etykietą `[Typ: X | Sekcja: Y]`.
- Model wie, które fragmenty pochodzą od autora (`own`), a które z zewnątrz (`external`), oraz z której części artykułu pochodzi wzorzec (`wstęp` / `rozwinięcie`).
- Nagłówek sekcji zawiera objaśnienie semantyki etykiet.

---

## Architektura

```
writer_node
    │
    └─ _fetch_rag_exemplars(topic, n=5)
            │                                  ← zwraca list[dict] od fazy 38
            └─ {text, article_type, section_type}
                        │
                        ▼
       _build_writer_user_prompt(exemplars=list[dict], ...)
                        │
                        └─ _format_exemplar(ex)
                                │
                                └─ "[Typ: own | Sekcja: wstęp]\n<text>"
                                   "[Typ: own | Sekcja: rozwinięcie]\n<text>"
                                   "[Typ: external | Sekcja: wstęp]\n<text>"
```

---

## Zmodyfikowane pliki

### `bond/graph/nodes/writer.py`

#### `_rerank()` — zmiana sygnatury

Poprzednia wersja operowała na `list[str]` i zwracała `list[str]`. Obecna wersja:

```python
# Przed
def _rerank(query: str, candidates: list[str], top_n: int) -> list[str]:
    ...
    return [r["text"] for r in ranked[:top_n]]

# Po
def _rerank(query: str, candidates: list[dict], top_n: int) -> list[dict]:
    passages = [{"id": i, "text": c["text"]} for i, c in enumerate(candidates)]
    ranked = _get_ranker().rerank(request)
    return [candidates[r["id"]] for r in ranked[:top_n]]  # odwzorowanie przez oryginalny indeks
```

Mapowanie przez `r["id"]` (oryginalny indeks kandydata) gwarantuje, że metadane zostają przy właściwym tekście po rerankowaniu.

#### `_fetch_rag_exemplars()` — metadane w zapytaniach

Zmiana `include=["documents"]` → `include=["documents", "metadatas"]` w obu ścieżkach zapytań (own + fallback). Wewnętrzna funkcja `_to_dicts()` buduje ustrukturyzowane dykty:

```python
def _to_dicts(docs, metas):
    return [
        {
            "text": doc,
            "article_type": meta.get("article_type", meta.get("source_type", "")),
            "section_type": meta.get("section_type", ""),
        }
        for doc, meta in zip(docs, metas)
    ]
```

Fallback `meta.get("article_type", meta.get("source_type", ""))` zapewnia wsteczną kompatybilność z chunkami sprzed migracji fazy 37.

#### `_format_exemplar()` — nowa funkcja pomocnicza

```python
def _format_exemplar(ex: dict) -> str:
    label = f"[Typ: {ex.get('article_type') or '?'} | Sekcja: {ex.get('section_type') or '?'}]"
    return f"{label}\n{ex['text']}"
```

Gdy metadane są puste (stary chunk bez migracji), wyświetla `?` zamiast pustego stringu.

#### `_build_writer_user_prompt()` — refaktor sekcji WZORCE STYLISTYCZNE

Zmiana sygnatury: `exemplars: list[str]` → `exemplars: list[dict]`.

| Aspekt | Przed | Po |
|--------|-------|----|
| Sygnatura | `list[str]` | `list[dict]` |
| Format fragmentu | surowy tekst | `[Typ: X \| Sekcja: Y]\n<tekst>` |
| Nagłówek sekcji | „Pisz w podobnym tonie i stylu" | Objaśnienie semantyki etykiet + priorytet `own` |

Nowy nagłówek sekcji:

```
## WZORCE STYLISTYCZNE (Few-Shot)
Poniższe fragmenty pochodzą z korpusu stylistycznego. Każdy opatrzony jest etykietą [Typ: X | Sekcja: Y]:
- **Typ**: "own" = artykuły autora (priorytet stylistyczny), "external" = artykuły zewnętrzne (wzorzec uzupełniający)
- **Sekcja**: "wstęp" = fragment otwierający artykuł, "rozwinięcie" = fragment głównej części

Przejmij ton, rytm zdań i sposób argumentacji — szczególnie z fragmentów "own". Nie kopiuj treści, adaptuj styl.
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Refaktor sekcji WZORCE STYLISTYCZNE w prompcie | ✅ Nowy nagłówek z objaśnieniem etykiet, priorytet "own" |
| Dynamiczne wstrzykiwanie `[Typ: X \| Sekcja: Y]` | ✅ `_format_exemplar()` dodaje etykietę do każdego fragmentu |
| Wsteczna kompatybilność (chunki bez metadanych) | ✅ Fallback `?` gdy pola puste; `article_type` ← `source_type` |
| Metadane przepływają przez reranker | ✅ `_rerank()` mapuje przez `r["id"]`, metadane niezmienione |

---

## Weryfikacja

Zweryfikowano programatycznie:

```
_format_exemplar({'text': '...', 'article_type': 'own', 'section_type': 'wstęp'})
→ '[Typ: own | Sekcja: wstęp]\n...'  ✅

_format_exemplar({'text': 'Fragment bez metadanych'})
→ '[Typ: ? | Sekcja: ?]\n...'  ✅ (fallback)

_fetch_rag_exemplars('marketing treści i SEO', n=5)
→ 5 x dict z kluczami: text, article_type, section_type  ✅

_build_writer_user_prompt(..., exemplars=exemplars[:2], ...)
→ '[Typ: X | Sekcja: Y]' obecne w prompcie  ✅
→ nagłówek z objaśnieniem etykiet obecny  ✅
```

Przykład renderowanej sekcji w prompcie (live corpus):

```
## WZORCE STYLISTYCZNE (Few-Shot)
...
[Typ: own | Sekcja: wstęp]
Search Generative Experience (SGE) zmieniło sposób, w jaki podchodzimy...

---

[Typ: own | Sekcja: wstęp]
W ciągu ostatnich lat sztuczna inteligencja przeszła długą drogę...
```
