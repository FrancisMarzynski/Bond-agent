# 11-SHADOW-MODE-INFRASTRUCTURE Podsumowanie: Rozszerzenie BondState i routing grafu

**Data ukończenia:** 2026-03-19
**Faza:** 04 — Shadow Mode
**Plan:** 01 — Infrastruktura grafu
**Status:** ✅ Zakończone

---

## Cel

Przygotowanie infrastruktury pod nową gałąź logiczną Shadow Mode. Rozszerzenie stanu grafu o pola dedykowane trybowi Shadow, implementacja funkcji routingowej `route_mode` decydującej o wyborze gałęzi Author lub Shadow, oraz utworzenie węzłów-stubów (`shadow_analyze`, `shadow_annotate`) gotowych do pełnej implementacji w kolejnym planie.

---

## Zmodyfikowane/Utworzone pliki

### `bond/graph/state.py`
- Przemianowano klasę `AuthorState` na `BondState` (zachowując alias `AuthorState = BondState` dla wstecznej kompatybilności z węzłami Phase 2).
- Dodano nowy typ `Annotation` (TypedDict) z polami:
  - `id: str` — stabilne unikalne ID (np. `"ann_001"`)
  - `original_span: str` — dosłowny fragment tekstu do zastąpienia
  - `replacement: str` — tekst poprawiony
  - `reason: str` — krótkie uzasadnienie odwołujące się do stylu autora
- Dodano pole `mode: NotRequired[Literal["author", "shadow"]]` — determinuje routing przy START; pominięcie pola jest bezpieczne (fallback do Author branch).
- Dodano opcjonalne pola Shadow Mode:
  - `original_text: Optional[str]` — tekst przesłany do analizy stylistycznej
  - `annotations: Optional[list[Annotation]]` — lista poprawek wyprodukowanych przez `shadow_annotate_node`
- Zmieniono `topic` i `keywords` na `Optional` (nie są wymagane w trybie Shadow).

### `bond/graph/graph.py`
- Zaktualizowano import z `AuthorState` na `BondState`.
- Dodano import `Literal` z `typing`.
- Dodano importy stubów: `shadow_analyze_node`, `shadow_annotate_node`.
- Dodano `route_mode(state) -> Literal["duplicate_check", "shadow_analyze"]` — funkcja routingowa czytająca `state["mode"]`.
- Zastąpiono `builder.add_edge(START, "duplicate_check")` przez:
  ```python
  builder.add_conditional_edges(
      START,
      route_mode,
      {"duplicate_check": "duplicate_check", "shadow_analyze": "shadow_analyze"},
  )
  ```
- Dodano węzły Shadow do rejestru: `shadow_analyze`, `shadow_annotate`.
- Dodano krawędzie Shadow branch: `shadow_analyze → shadow_annotate → END`.
- Dodano alias `build_bond_graph = build_author_graph`.
- Zaktualizowano `StateGraph(AuthorState)` → `StateGraph(BondState)`.

### `bond/graph/nodes/shadow_analyze.py` *(nowy plik)*
- Stub węzła odpowiedzialnego za pobieranie fragmentów korpusu stylistycznego.
- Zwraca `{"shadow_corpus_fragments": []}` i loguje `WARNING` — węzeł nie crashuje, graf Shadow mode jest testowalny end-to-end.
- Pełna implementacja w Plan 04-01 (dwuprzejściowe zapytanie ChromaDB: własne teksty → uzupełnienie zewnętrznymi).

### `bond/graph/nodes/shadow_annotate.py` *(nowy plik)*
- Stub węzła odpowiedzialnego za generowanie adnotacji i złożenie poprawionego tekstu.
- Zwraca `{"annotations": [], "shadow_corrected_text": original_text}` i loguje `WARNING` — tekst wraca niezmieniony, adnotacje puste.
- Pełna implementacja w Plan 04-01 (LLM z `with_structured_output(AnnotationResult)`, śledzenie statusu adnotacji).

### `bond/graph/nodes/__init__.py`
- Dodano komentarz informujący o Shadow nodes i planie pełnej implementacji.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| BondState zawiera opcjonalne pola `original_text` i `annotations: list[Annotation]` | ✅ Oba pola dodane, `Annotation` zdefiniowany jako TypedDict z polami `id`, `original_span`, `replacement`, `reason` |
| Implementacja funkcji `route_mode` decydującej o przejściu do gałęzi Author lub Shadow | ✅ `route_mode(state)` sprawdza `state["mode"]`; zwraca `"shadow_analyze"` lub `"duplicate_check"` |
| Utworzenie pustych węzłów (stubs) dla `shadow_analyze` i `shadow_annotate` | ✅ Oba pliki utworzone; stubs zwracają puste wyniki z logiem WARNING (nie crashują) — Shadow mode testowalny end-to-end |

---

## Strategia wstecznej kompatybilności

Alias `AuthorState = BondState` zapewnia, że wszystkie istniejące węzły Phase 2 (`researcher`, `structure`, `writer`, `checkpoint_1`, `checkpoint_2`, `duplicate_check`, `save_metadata`) kontynuują działanie bez żadnych modyfikacji. Typ zmienny jest identyczny — alias to ta sama klasa pod inną nazwą.

---

## Topologia grafu po zmianach

```
[START]
  ↓ route_mode(state["mode"])
  ├─ "author" → duplicate_check ──────────┐
  │              ├─ override=False → [END] │
  │              └─ else → researcher      │
  │                         ↓             │
  │                      structure         │
  │                         ↓             │
  │                     checkpoint_1       │
  │                  ├─ approved → writer  │
  │                  └─ else → structure   │
  │                              ↓         │
  │                           writer        │
  │                              ↓         │
  │                         checkpoint_2   │
  │                  ├─ approved → save_metadata → [END]
  │                  └─ else → writer      │
  │                                        │
  └─ "shadow" → shadow_analyze (stub)     │
                    ↓                      │
               shadow_annotate (stub)      │
                    ↓                      │
                  [END]                    │
```

---

## Uwagi deweloperskie

- `mode` jest `NotRequired` — pominięcie pola w `ainvoke()` jest bezpieczne; `route_mode` używa `state.get("mode")`, co przy braku klucza daje `None` → routing do Author branch.
- Stubs zwracają puste wyniki i logują `WARNING` zamiast crashować — całą ścieżkę Shadow można przetestować end-to-end (routing → shadow_analyze → shadow_annotate → END) bez pełnej implementacji.
- Pełna implementacja `shadow_analyze_node` i `shadow_annotate_node` zaplanowana w Plan 04-01 (ChromaDB two-pass retrieval + LLM structured output).
