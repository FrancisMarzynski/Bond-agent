# 31-TOKEN-COST-TRACKING Podsumowanie: Śledzenie tokenów i kosztów per artykuł

**Data ukończenia:** 2026-04-13  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 31 — Per-article Token & Cost Tracking  
**Status:** ✅ Zakończone

---

## Cel

Implementacja monitorowania zużycia zasobów LLM per artykuł zgodnie z wymaganiem `PROJECT.md` (#15).

- Dodanie pól `tokens_used_research`, `tokens_used_draft` i `estimated_cost_usd` do `BondState`.
- Ekstrakcja `usage_metadata` po każdym wywołaniu `ainvoke()` w węzłach researcher, structure i writer.
- Akumulacja liczników tokenów w stanie grafu przez cały pipeline.
- Persystencja danych do `bond_metadata.db` razem z metadanymi artykułu w `save_metadata_node`.

---

## Architektura

```
researcher_node
    │  llm.ainvoke() → response.usage_metadata
    │  → tokens_used_research += input + output
    │  → estimated_cost_usd += estimate_cost_usd(research_model, ...)
    │
structure_node
    │  llm.ainvoke() → response.usage_metadata
    │  → tokens_used_research += input + output   (akumuluje do istniejącej wartości)
    │  → estimated_cost_usd += estimate_cost_usd(research_model, ...)
    │
writer_node
    │  for attempt in range(3):
    │      llm.ainvoke() → response.usage_metadata
    │      total_draft_input_tokens  += input
    │      total_draft_output_tokens += output
    │  → tokens_used_draft += total_input + total_output
    │  → estimated_cost_usd += estimate_cost_usd(draft_model, ...)
    │
save_metadata_node
    └─ save_article_metadata(
           tokens_used_research=state["tokens_used_research"],
           tokens_used_draft=state["tokens_used_draft"],
           estimated_cost_usd=state["estimated_cost_usd"],
       )
       → INSERT INTO metadata_log (tokens_used_research, tokens_used_draft, estimated_cost_usd)
```

---

## Zmodyfikowane pliki

### `bond/graph/state.py`

Dodano trzy pola `NotRequired` do `BondState`:

```python
# --- Token & cost tracking ---
tokens_used_research: NotRequired[int]   # tokeny zużyte przez researcher + structure
tokens_used_draft: NotRequired[int]      # tokeny zużyte przez writer (wszystkie próby)
estimated_cost_usd: NotRequired[float]   # bieżąca suma szacowanego kosztu w USD
```

Użycie `NotRequired` sprawia, że pola są opcjonalne — istniejące sesje nie wymagają migracji.

### `bond/llm.py`

Dodano tablicę cenową i funkcję pomocniczą `estimate_cost_usd()`:

```python
_MODEL_COSTS_USD_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-opus": (15.00, 75.00),
}

def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    ...
```

Dopasowanie modelu działa przez substring (najdłuższe dopasowanie wygrywa). Fallback: ceny `gpt-4o` (konserwatywne zawyżenie).

### `bond/graph/nodes/researcher.py`

Zmieniono sygnaturę `_format_research_report()` z `-> str` na `-> tuple[str, int, int]`.  
Funkcja teraz zwraca `(report_markdown, input_tokens, output_tokens)`.

W `researcher_node()` po rozpakowaniu krotki:

```python
report, input_tokens, output_tokens = await _format_research_report(...)
call_cost = estimate_cost_usd(settings.research_model, input_tokens, output_tokens)
return {
    ...
    "tokens_used_research": state.get("tokens_used_research", 0) + input_tokens + output_tokens,
    "estimated_cost_usd": state.get("estimated_cost_usd", 0.0) + call_cost,
}
```

### `bond/graph/nodes/structure.py`

Zmieniono `(await llm.ainvoke(prompt)).content.strip()` na przypisanie `response` i odczyt `response.usage_metadata`:

```python
response = await llm.ainvoke(prompt)
heading_structure = response.content.strip()

usage = response.usage_metadata or {}
input_tokens = usage.get("input_tokens", 0)
output_tokens = usage.get("output_tokens", 0)
call_cost = estimate_cost_usd(settings.research_model, input_tokens, output_tokens)

return {
    "heading_structure": heading_structure,
    "tokens_used_research": state.get("tokens_used_research", 0) + input_tokens + output_tokens,
    "estimated_cost_usd": state.get("estimated_cost_usd", 0.0) + call_cost,
}
```

### `bond/graph/nodes/writer.py`

Zamieniono `(await llm.ainvoke(messages)).content` na przypisanie `response` wewnątrz pętli retry. Liczniki tokenów akumulowane po każdej próbie:

```python
total_draft_input_tokens = 0
total_draft_output_tokens = 0
for attempt in range(max_attempts):
    response = await llm.ainvoke(messages)
    draft = _clean_output(response.content)

    usage = response.usage_metadata or {}
    total_draft_input_tokens += usage.get("input_tokens", 0)
    total_draft_output_tokens += usage.get("output_tokens", 0)
    ...

call_cost = estimate_cost_usd(
    settings.draft_model, total_draft_input_tokens, total_draft_output_tokens
)
return {
    ...
    "tokens_used_draft": state.get("tokens_used_draft", 0) + total_draft_input_tokens + total_draft_output_tokens,
    "estimated_cost_usd": state.get("estimated_cost_usd", 0.0) + call_cost,
}
```

### `bond/db/schema.sql`

Dodano trzy kolumny do tabeli `metadata_log`:

```sql
tokens_used_research INTEGER NOT NULL DEFAULT 0,
tokens_used_draft    INTEGER NOT NULL DEFAULT 0,
estimated_cost_usd   REAL    NOT NULL DEFAULT 0.0
```

Kolumny mają wartości domyślne — istniejące wiersze w bazie nie wymagają migracji ręcznej.

### `bond/db/metadata_log.py`

Rozszerzono sygnaturę `save_article_metadata()` o trzy opcjonalne parametry (domyślnie `0`/`0.0`):

```python
async def save_article_metadata(
    thread_id: str,
    topic: str,
    mode: str = "author",
    tokens_used_research: int = 0,
    tokens_used_draft: int = 0,
    estimated_cost_usd: float = 0.0,
) -> int:
```

Zapytanie `INSERT` rozszerzono o nowe kolumny.

### `bond/graph/nodes/save_metadata.py`

Przekazanie wartości tokenów i kosztu do `save_article_metadata()`:

```python
await save_article_metadata(
    thread_id=thread_id,
    topic=topic,
    mode="author",
    tokens_used_research=state.get("tokens_used_research", 0),
    tokens_used_draft=state.get("tokens_used_draft", 0),
    estimated_cost_usd=state.get("estimated_cost_usd", 0.0),
)
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Dodanie pól `tokens_used_research`, `tokens_used_draft`, `estimated_cost_usd` do `BondState` | ✅ Dodane jako `NotRequired` w `bond/graph/state.py` |
| Ekstrakcja `usage_metadata` po każdym `ainvoke()` w `researcher_node` | ✅ `_format_research_report` zwraca `(report, input_tokens, output_tokens)` |
| Ekstrakcja `usage_metadata` po `ainvoke()` w `structure_node` | ✅ `response.usage_metadata` odczytywane i akumulowane |
| Ekstrakcja `usage_metadata` po każdej próbie `ainvoke()` w `writer_node` | ✅ Akumulowane przez wszystkie retry (`total_draft_input/output_tokens`) |
| Persystencja do `bond_metadata.db` | ✅ Schema, `save_article_metadata()` i `save_metadata_node` zaktualizowane |

---

## Uwagi implementacyjne

**Dlaczego `NotRequired` zamiast `Optional`?**  
`Optional[int]` sugeruje możliwość wartości `None`, co komplikuje dodawanie. `NotRequired[int]` oznacza, że klucz może nie istnieć w słowniku — `state.get("tokens_used_research", 0)` zwraca `0` i działa poprawnie.

**Dlaczego `usage_metadata or {}`?**  
`response.usage_metadata` może zwrócić `None` gdy dostawca LLM nie zwraca danych użycia (np. w testach z mockami). Operator `or {}` gwarantuje, że `.get()` nie rzuci `AttributeError`.

**Dlaczego tokeny writer są zliczane osobno od research?**  
`gpt-4o` (draft) i `gpt-4o-mini` (research) mają różne ceny. Osobne liczniki umożliwiają dokładniejsze obliczenie kosztu i późniejsze raportowanie po modelu.

**Fallback ceny w `estimate_cost_usd()`**  
Gdy model nie pasuje do żadnego klucza w `_MODEL_COSTS_USD_PER_1M`, funkcja używa cen `gpt-4o`. Jest to celowe zawyżenie — lepiej przeszacować koszt niż go ukryć.

**Automatyczna migracja schematu**  
`_ensure_schema()` próbuje wykonać `ALTER TABLE metadata_log ADD COLUMN` dla każdej nowej kolumny po wykonaniu DDL z `schema.sql`. SQLite nie obsługuje `ADD COLUMN IF NOT EXISTS`, więc wyjątek `OperationalError` (duplikat kolumny) jest cicho ignorowany. Dzięki temu wywołanie jest idempotentne — działa zarówno na nowej bazie, jak i na istniejącej z poprzedniej wersji bez żadnej interwencji ręcznej.
