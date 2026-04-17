# 34-MULTI-QUERY-PROMPT-GENERATION Podsumowanie: Generowanie zróżnicowanych zapytań dla Exa API

**Data ukończenia:** 2026-04-17
**Faza:** 03 — Streaming API i Frontend
**Status:** ✅ Zakończone

---

## Cel

Zastąpienie pojedynczego zapytania Exa trzema wyspecjalizowanymi sub-zapytaniami (General, Stats, Case Study), co zwiększa różnorodność i głębię zebranego materiału badawczego.

---

## Architektura

```
researcher_node
    │
    ├─ Layer 1: state cache hit? → skip generation
    │
    ├─ Layer 2: SQLite cache hit? → skip generation
    │
    └─ Layer 3 (live):
            │
            ├─ _generate_sub_queries(topic, keywords)
            │       └─ LLM.with_structured_output(ResearchQueries)
            │              → ResearchQueries(general=..., stats=..., case_study=...)
            │
            ├─ _call_exa_mcp(general_query, num_results=6)  → "### General\n..."
            ├─ _call_exa_mcp(stats_query,   num_results=6)  → "### Stats\n..."
            └─ _call_exa_mcp(case_study_query, num_results=6) → "### Case Study\n..."
                    │
                    └─ raw_results = join(parts)  → save_cached_result → _format_research_report
```

---

## Zmodyfikowane pliki

### `bond/graph/nodes/researcher.py`

#### Nowy model Pydantic — `ResearchQueries`

```python
class ResearchQueries(BaseModel):
    general: str
    stats: str
    case_study: str

    @field_validator("general", "stats", "case_study")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("query must not be empty")
        return v.strip()

    def as_list(self) -> list[str]:
        return [self.general, self.stats, self.case_study]
```

- Trzy pola wymuszają dokładnie 3 łańcuchy (jeden per kąt tematu).
- `field_validator` odrzuca puste wartości i usuwa zbędne białe znaki.
- `as_list()` udostępnia ordered iteration dla pętli w węźle.

#### Nowa funkcja — `_generate_sub_queries`

```python
async def _generate_sub_queries(topic, keywords) -> ResearchQueries:
    llm = get_research_llm(max_tokens=300, temperature=0)
    structured_llm = llm.with_structured_output(ResearchQueries)
    return await structured_llm.ainvoke(prompt)
```

- Używa `llm.with_structured_output(ResearchQueries)` — LangChain wymusza format JSON zgodny z modelem Pydantic.
- Temperature=0 zapewnia determinizm; max_tokens=300 wystarczy na 3 krótkie zapytania.
- Wynik jest logowany na poziomie INFO (widoczny w standardowym logu aplikacji).

#### Aktualizacja `researcher_node` — Layer 3

Poprzednio: jedno wywołanie `_call_exa_mcp(topic, keywords, num_results=8)`.

Teraz:
```python
sub_queries = await _generate_sub_queries(topic, keywords)
parts = []
for label, query in zip(["General", "Stats", "Case Study"], sub_queries.as_list()):
    section = await _call_exa_mcp(query, keywords, num_results=6)
    parts.append(f"### {label}\n{section}")
raw_results = "\n\n".join(parts)
```

- `num_results` zredukowane z 8 do 6 na zapytanie (łącznie 18 wyników zamiast 8 — większa pokrywalność bez przeciążenia kontekstu LLM).
- Struktura sekcyjna (`### General`, `### Stats`, `### Case Study`) przekazywana do `_format_research_report` poprawia jakość syntezy, bo LLM widzi wyraźne granice tematyczne.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Nowy prompt generujący 3 sub-tematy (General, Stats, Case Study) | ✅ `_generate_sub_queries` wywołuje LLM z poleceniem pokrycia 3 kątów |
| Pydantic BaseModel wymuszający listę 3 stringów w outputcie | ✅ `ResearchQueries` z `field_validator` + `llm.with_structured_output` |
| Integracja z istniejącą logiką cache (Layer 1–3) | ✅ Generowanie sub-zapytań następuje tylko w Layer 3 (brak cache hit) |
| Zachowanie minimalnej liczby źródeł (`_MIN_SOURCES = 3`) | ✅ Brak zmian w `_count_sources` i warunku walidacji |

---

## Wpływ na wydajność

| Metryka | Przed | Po |
|---------|-------|----|
| Wywołania Exa per run (Layer 3) | 1 (8 wyników) | 3 × 6 = 18 wyników |
| Wywołania LLM per run (Layer 3) | 0 (zapytanie = topic) | +1 (sub-query generation, ~300 tokens) |
| Cache hit path | bez zmian | bez zmian (Layer 1/2 pomijają generowanie) |

Dodatkowe wywołanie LLM (~300 tokenów, ~$0.0001 przy gpt-4o-mini) jest pomijalne wobec zysku z 18 vs 8 zróżnicowanych wyników.

---

## Weryfikacja

```python
# Poprawna inicjalizacja modelu
q = ResearchQueries(general="BIM electrical design Poland", stats="BIM adoption rate statistics 2024", case_study="BIM electrical installation case study hospital")
assert q.as_list() == ["BIM electrical design Poland", "BIM adoption rate statistics 2024", "BIM electrical installation case study hospital"]

# Walidacja pustego stringa
ResearchQueries(general="", stats="b", case_study="c")
# → ValidationError: query must not be empty
```

Oba scenariusze zweryfikowane lokalnie (`uv run python`).
