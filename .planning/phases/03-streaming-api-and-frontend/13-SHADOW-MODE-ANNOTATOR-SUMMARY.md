# 13-SHADOW-MODE-ANNOTATOR Podsumowanie: Węzeł Annotator (Structured Output)

**Data ukończenia:** 2026-03-19
**Faza:** 04 — Shadow Mode
**Plan:** 04-01 — Infrastruktura Shadow Mode
**Status:** ✅ Zakończone

---

## Cel

Pełna implementacja węzła `shadow_annotate_node` odpowiedzialnego za generowanie precyzyjnych adnotacji stylistycznych w formacie JSON/Pydantic. Węzeł wywołuje model DRAFT_MODEL przez `with_structured_output`, waliduje indeksy znakowe każdej adnotacji względem długości tekstu oryginalnego i składa `shadow_corrected_text` przez aplikację poprawek.

---

## Zmodyfikowane/Utworzone pliki

### `bond/graph/nodes/shadow_annotate.py`

Całkowita zamiana stubu na pełną implementację zawierającą:

- **Pydantic modele structured output**: `AnnotationItem` i `AnnotationResult` z pełnymi opisami pól dla JSON schema LLM.
- **`AnnotationItem`** — pola: `id`, `original_span`, `replacement`, `reason`, `start_index`, `end_index`.
  Pola indeksów zawierają precyzyjne instrukcje dla LLM (warunek: `text[start_index:end_index] == original_span`).
- **`AnnotationResult`** — `annotations: list[AnnotationItem]` + opcjonalne `alignment_summary` (wymagane tylko przy > 5 adnotacjach).
- **`_validate_and_fix_annotation()`** — trójprzebiegowa walidacja każdej adnotacji:
  1. Akceptacja gdy indeksy są prawidłowe I `text[start:end] == original_span`.
  2. Auto-korekcja indeksów przez `str.find(original_span)` gdy indeksy są błędne, ale span istnieje w tekście.
  3. Odrzucenie z ostrzeżeniem w logu gdy span nie zostanie znaleziony nigdzie w tekście.
- **`_apply_annotations()`** — aplikacja poprawek w odwrotnej kolejności indeksów (`start_index` malejąco), co zapobiega przesunięciom pozycji przy zastępowaniu fragmentów o różnych długościach.
- **`shadow_annotate_node()`** — węzeł LangGraph: wybór LLM (Claude/OpenAI przez `settings.draft_model`), wywołanie `with_structured_output(AnnotationResult)`, walidacja, składanie `shadow_corrected_text`.

### `bond/graph/state.py`

- Rozszerzono `Annotation` TypedDict o pola `start_index: int` i `end_index: int`.
- Dodano do `BondState` pole `shadow_corrected_text: Optional[str]` — tekst oryginalny ze wszystkimi zastosowanymi poprawkami.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Węzeł `shadow_annotate` zwraca listę obiektów `Annotation` | ✅ Węzeł zwraca `{"annotations": list[Annotation], "shadow_corrected_text": str}`. Każdy obiekt jest TypedDict z pełnym zestawem pól. |
| Wykorzystanie `with_structured_output` dla zapewnienia determinizmu | ✅ `llm.with_structured_output(AnnotationResult)` z `temperature=0` — deterministyczny JSON schema narzucony przez Pydantic. |
| Walidacja, czy `start_index` i `end_index` mieszczą się w długości tekstu | ✅ Trójprzebiegowa walidacja: sprawdzenie granic (`0 <= start < text_len`, `end <= text_len`), próba auto-korekcji, odrzucenie gdy niemożliwe. Logowane przez `logger.warning`. |

---

## Szczegóły implementacji

### Architektura walidacji indeksów

Walidacja jest celowo trójfazowa, by obsłużyć typowy scenariusz halucynacji indeksów przez LLM:

```
Pass 1: Indeksy OK + text[s:e] == span  →  akceptacja bez zmian
Pass 2: Span znaleziony przez find()    →  auto-korekcja indeksów + ostrzeżenie
Pass 3: Span nie istnieje w tekście    →  odrzucenie + ostrzeżenie w logu
```

Dzięki temu pipeline nie failu przy błędnych indeksach LLM — zamiast tego reaguje degradacją graceful (annotation odrzucona, tekst oryginalny bez zmiany w tym miejscu).

### Budowanie corrected_text

```python
sorted_anns = sorted(annotations, key=lambda a: a["start_index"], reverse=True)
result = original
for ann in sorted_anns:
    result = result[:ann["start_index"]] + ann["replacement"] + result[ann["end_index"]:]
```

Sortowanie malejące po `start_index` gwarantuje, że każda podmiana operuje na indeksach tekstu oryginalnego, nie przesuniętego przez poprzednie zamiany.

### Wybór modelu

Węzeł używa `settings.draft_model` (default: `gpt-4o`) z `temperature=0` — maksymalny determinizm structured output. Claude i OpenAI obsługiwane przez ten sam warunek `"claude" in model.lower()`.

### Prompty

System prompt w języku polskim definiuje trzy obszary analizy: ton, rytm zdań, słownictwo. User prompt formatuje tekst oryginalny i fragmenty korpusu w bloki oddzielone separatorem `---`. LLM otrzymuje pełne instrukcje dotyczące precyzji `original_span` i formatu indeksów.

---

## Odchylenia od planu

| Obszar | Plan (04-01-PLAN.md) | Implementacja |
|--------|----------------------|---------------|
| Pole ID w modelu | `annotation_id` | `id` — zachowuje spójność z istniejącym `Annotation` TypedDict w `state.py` |
| Pola `start_index`/`end_index` | Brak w planie (plan używa `original_span` + `str.replace`) | Dodane do `AnnotationItem` i `Annotation` TypedDict zgodnie z AC zadania |
| Shadow state fields | `shadow_annotations`, `shadow_input_text` | `annotations`, `original_text` — zgodnie z aktualnym `state.py` (już wdrożonym przez poprzedni plan) |
| Status tracking | `shadow_previous_annotations`, `status: new/modified/unchanged` | Pominięte — nie wchodzi w zakres AC bieżącego zadania; shadow checkpoint (Plan 04-02) może to dodać |
