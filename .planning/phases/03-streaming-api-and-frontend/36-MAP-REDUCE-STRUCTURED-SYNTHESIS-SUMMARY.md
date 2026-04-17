# 36-MAP-REDUCE-STRUCTURED-SYNTHESIS Podsumowanie: Strukturyzowana synteza danych badawczych

**Data ukończenia:** 2026-04-17
**Faza:** 03 — Streaming API i Frontend
**Status:** ✅ Zakończone

---

## Cel

Zastąpienie syntezy wolnotekstowej (narażonej na obcinanie przy >20 źródłach) podejściem Map-Reduce z wymuszonym wyjściem strukturalnym (`with_structured_output`). Researcher zwraca teraz dane jako Pydantic `ResearchData` (Fakty / Statystyki / Źródła) zamiast surowego bloku Markdown.

---

## Architektura

```
researcher_node
    │
    └─ _synthesize_structured(raw_results, topic, keywords, context_block)
            │
            ├─ LLM.with_structured_output(ResearchData, include_raw=True)
            │       → {"parsed": ResearchData, "raw": AIMessage, "parsing_error": ...}
            │
            ├─ ResearchData(
            │       fakty:      list[str]        ← 5-10 twierdzeń merytorycznych
            │       statystyki: list[str]        ← 5-10 danych liczbowych
            │       zrodla:     list[SourceItem] ← wszystkie unikalne źródła
            │   )
            │
            ├─ len(data.zrodla) >= _MIN_SOURCES  ← walidacja (dokładna, nie regex)
            │
            ├─ data.to_markdown(topic)  → research_report: str  (dla downstream compat)
            │
            └─ data.model_dump()        → research_data: dict  (nowe pole w BondState)
```

---

## Zmodyfikowane pliki

### `bond/graph/nodes/researcher.py`

#### Nowe modele Pydantic

```python
class SourceItem(BaseModel):
    title: str
    url: str      # @field_validator: strip + rstrip(".,;")
    summary: str

class ResearchData(BaseModel):
    fakty:      list[str]         # @field_validator: strip + filter empty
    statystyki: list[str]         # @field_validator: strip + filter empty
    zrodla:     list[SourceItem]

    def to_markdown(self, topic: str) -> str:
        # renders ## Raport, ### Fakty, ### Statystyki, ### Źródła
```

#### Nowa funkcja `_synthesize_structured` (zastępuje `_format_research_report`)

```python
async def _synthesize_structured(
    raw_results, topic, keywords, context_block=""
) -> tuple[ResearchData, int, int]:
    llm = get_research_llm(max_tokens=3000)
    structured_llm = llm.with_structured_output(ResearchData, include_raw=True)
    raw_output = await structured_llm.ainvoke(prompt)

    data = raw_output.get("parsed")
    if data is None:
        raise ValueError(f"Structured synthesis failed: {raw_output.get('parsing_error')}")

    # Token usage extracted from raw AIMessage (include_raw=True)
    usage = raw_output["raw"].usage_metadata or {}
    return data, usage["input_tokens"], usage["output_tokens"]
```

Kluczowe zmiany względem starego `_format_research_report`:
- `max_tokens` zwiększone z 2500 → 3000 (więcej miejsca na listy)
- Prompt nie prosi o wolny tekst narracyjny — prosi o 3 konkretne listy
- Wyjście LLM jest schematem JSON wymuszonym przez `with_structured_output`
- `include_raw=True` pozwala wyekstraktować token usage z `AIMessage` mimo structured output

#### Aktualizacja `researcher_node`

```python
research_data, input_tokens, output_tokens = await _synthesize_structured(...)
source_count = len(research_data.zrodla)  # dokładna liczba, nie regex heurystyka
report = research_data.to_markdown(topic)

return {
    "research_report": research_data.to_markdown(topic),  # str — compat z structure/writer
    "research_data":   research_data.model_dump(),        # dict — nowe pole stanu
    ...
}
```

Usunięte:
- `_format_research_report` — zastąpione przez `_synthesize_structured`
- `_count_sources` — zastąpione przez `len(research_data.zrodla)` (dokładne)

### `bond/graph/state.py`

```python
research_data: NotRequired[Optional[dict]]  # structured: {fakty, statystyki, zrodla}
```

Dodanie `NotRequired` zapewnia wsteczną kompatybilność — istniejące węzły (structure, writer, checkpoint_1) nie dotykają tego pola.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Refaktor promptu syntezy: podział na Fakty, Statystyki i Źródła | ✅ Nowy prompt w `_synthesize_structured` wymaga list `fakty`, `statystyki`, `zrodla` |
| Researcher zwraca dane w formacie ustrukturyzowanym (JSON/Dict) | ✅ `researcher_node` zwraca `research_data: research_data.model_dump()` w stanie |

---

## Backward compatibility

| Odbiorca | Pole | Zmiana |
|----------|------|--------|
| `structure_node` | `research_report[:2000]` | Nadal string; teraz zawiera sekcje Fakty/Statystyki/Źródła zamiast narracji |
| `writer_node` | `research_report[:3000]` | Nadal string; bardziej gęsty informacyjnie (listy, nie akapity) |
| `checkpoint_1` | `research_report` | Nadal string; sekcje wyraźnie czytelne dla użytkownika |
| `harness.py` | `research_report[:500]` | Nadal string |

---

## Dlaczego structured output rozwiązuje problem obcinania

Poprzednio:
```
LLM → 2500 tokenów wolnego tekstu
      → narażone na ucięcie w połowie listy źródeł
```

Teraz:
```
LLM → JSON: {"fakty": [...], "statystyki": [...], "zrodla": [...]}
      → każda lista jest niezależna
      → LLM wypełnia pola po kolei; nie "gubi" źródeł na końcu
      → 3000 tokenów podzielone logicznie między sekcje
```

Ponadto: `len(data.zrodla)` daje DOKŁADNĄ liczbę źródeł bez regex heurystyki `^\d+\.`.

---

## Weryfikacja

Testy lokalne (`uv run python`):

```
Test 1 passed: SourceItem url cleaned
Test 2 passed: ResearchData strips empty items
Test 3 passed: to_markdown renders all sections
Test 4 passed: model_dump is JSON-serialisable
Test 5 passed: research_data in BondState
Test 6 passed: empty zrodla returns 0 count

All tests passed
```
