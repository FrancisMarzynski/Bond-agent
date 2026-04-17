# 35-PARALLEL-EXA-SEARCH-DEDUP Podsumowanie: Równoległe wyszukiwanie Exa i deduplikacja wyników

**Data ukończenia:** 2026-04-17
**Faza:** 03 — Streaming API i Frontend
**Status:** ✅ Zakończone

---

## Cel

Efektywne pobieranie danych z wielu źródeł równolegle oraz eliminacja duplikatów URL z połączonych wyników 3 sub-zapytań, z twardym limitem 20 unikalnych źródeł.

---

## Architektura

```
researcher_node — Layer 3 (live search)
    │
    ├─ _generate_sub_queries(topic, keywords)
    │       └─ ResearchQueries(general, stats, case_study)
    │
    ├─ asyncio.gather(                         ← równolegle
    │       _call_exa_mcp(general_query, num_results=8),
    │       _call_exa_mcp(stats_query,   num_results=8),
    │       _call_exa_mcp(case_study_query, num_results=8)
    │   )   → list[str]  (max 24 surowych wyników)
    │
    └─ _deduplicate_sections(labeled_sections)
            │
            ├─ split każdej sekcji na bloki ^\d+\.
            ├─ ekstraktuj primary URL z każdego bloku (_URL_RE)
            ├─ seen_urls: set — odrzuć duplikaty
            ├─ stop przy len(seen_urls) >= _MAX_UNIQUE_SOURCES (20)
            └─ → (combined_string, unique_count)
                        │
                        └─ → save_cached_result → _format_research_report
```

---

## Zmodyfikowane pliki

### `bond/graph/nodes/researcher.py`

#### Nowe stałe

```python
_MAX_UNIQUE_SOURCES = 20
_URL_RE = re.compile(r"https?://[^\s\])\">'\,]+")
```

`_URL_RE` dopasowuje URL http/https zatrzymując się na białych znakach i typowej interpunkcji zamykającej.

#### Nowa funkcja — `_deduplicate_sections`

```python
def _deduplicate_sections(
    labeled_sections: list[tuple[str, str]]
) -> tuple[str, int]:
```

- Iteruje przez `(label, raw_exa_string)` zachowując oryginalną kolejność sekcji (General → Stats → Case Study).
- Każdą sekcję dzieli na bloki wyników regexem `(?m)^(?=\d+\.)` (split przed każdym numerowanym wpisem).
- Dla każdego bloku: ekstraktuje pierwszą URL jako klucz deduplicacji; bloki bez URL (preambuła) są zachowywane.
- Odrzuca blok gdy jego URL już był widziany (`seen_urls`).
- Odrzuca blok gdy `len(seen_urls) >= _MAX_UNIQUE_SOURCES`.
- Zwraca `(combined_markdown, unique_count)`.

#### Aktualizacja `researcher_node` — Layer 3

Poprzednio (sekwencyjne):
```python
for label, query in zip(labels, queries):
    section = await _call_exa_mcp(query, keywords, num_results=6)
    parts.append(f"### {label}\n{section}")
raw_results = "\n\n".join(parts)
```

Teraz (równoległe + deduplikacja):
```python
sections: list[str] = await asyncio.gather(
    *[_call_exa_mcp(q, keywords, num_results=8) for q in queries]
)
labeled = list(zip(labels, sections))
raw_results, unique_count = _deduplicate_sections(labeled)
```

`num_results` zwiększone z 6 do 8 na zapytanie (wejście do deduplicacji: max 24 wyniki → wyjście: max 20 unikalnych).

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| `asyncio.gather` dla wywołań Exa MCP | ✅ Trzy wywołania `_call_exa_mcp` uruchamiane równolegle jednym `asyncio.gather` |
| Deduplikacja wyników po URL | ✅ `_deduplicate_sections` ekstraktuje primary URL z każdego bloku i śledzi `seen_urls: set` |
| Limit 15–20 unikalnych źródeł | ✅ `_MAX_UNIQUE_SOURCES = 20`; bloki ponad limit są pomijane przed zapisem do cache |

---

## Wpływ na wydajność

| Metryka | Przed | Po |
|---------|-------|----|
| Czas Exa (3 zapytania) | ~3 × T | ~max(T) — równolegle |
| Wyniki wejściowe | 3 × 6 = 18 | 3 × 8 = 24 (surowe) |
| Wyniki po deduplicacji | brak filtrowania | ≤ 20 unikalnych URL |
| Możliwe duplikaty w raporcie | tak | nie |

Równoległe wykonanie redukuje czas oczekiwania z ~3T do ~T (gdzie T to czas pojedynczego zapytania Exa, typowo 1–3 s).

---

## Weryfikacja

Testy lokalne (`uv run python`):

```
Test 1 passed: dedup across sections        # URL z sekcji Stats pominięty gdy już w General
Test 2 passed: cap at 20 unique sources     # 30 wyników → 20 po cięciu
Test 3 passed: preamble text preserved      # bloki bez URL (tekst wstępny) zachowane
Test 4 passed: asyncio.gather works         # import + uruchomienie gather bez błędów
All tests passed
```
