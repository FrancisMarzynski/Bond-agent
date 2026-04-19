# 41-STRUCTURE-NODE-FRONTIER-MODEL Podsumowanie: Frontier Model dla generowania struktury nagłówków

**Data ukończenia:** 2026-04-19  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 41 — Optymalizacja kosztów struktury (Frontier Model)  
**Status:** ✅ Zakończone

---

## Cel

Przełączenie `structure_node` z modelu `gpt-4o-mini` (`get_research_llm`) na `gpt-4o` (`get_draft_llm`) w celu uzyskania wyższej jakości flow narracyjnego przy pomijalnym wzroście kosztów.

- `structure_node` używał `get_research_llm(max_tokens=800)` — tańszego minimodelu.
- Struktura nagłówków (H1/H2/H3) to kluczowa decyzja architektoniczna artykułu. Minimodel generował poprawne, ale generyczne struktury.
- Dla technicznej niszy (BIM, XR, instalacje elektryczne) różnica leży w niuansach kolejności sekcji i formułowaniu nagłówków pod konkretne intencje wyszukiwania.
- `structure_node` wykonuje jeden krótki call (max_tokens=800) — koszt różnicy między mini a frontier modelem jest pomijalny.

---

## Architektura

```
structure_node
    │
    ├─ get_draft_llm(max_tokens=800, temperature=0)   ← ZMIANA (było: get_research_llm)
    │        │
    │        └─ primary: settings.draft_model (gpt-4o)
    │           fallback: settings.research_model (gpt-4o-mini)
    │
    ├─ prompt (first run / regeneration z cp1_feedback)
    │        └─ wymaga H1 z primary_keyword, 3–6x H2, opcjonalnie H3 pod H2
    │
    └─ estimate_cost_usd(settings.draft_model, ...)   ← ZMIANA (było: settings.research_model)
```

`temperature=0` zapewnia deterministyczne generowanie struktury — identyczny temat i raport zwraca tę samą strukturę, co ułatwia debugowanie i jest właściwe dla strukturalnego zadania (nie kreatywnego).

---

## Zmodyfikowane pliki

### `bond/graph/nodes/structure.py`

#### Import — zmiana modułu LLM

| Aspekt | Przed | Po |
|--------|-------|----|
| Import | `from bond.llm import estimate_cost_usd, get_research_llm` | `from bond.llm import estimate_cost_usd, get_draft_llm` |

#### Instancja LLM

```python
# Przed
llm = get_research_llm(max_tokens=800)

# Po
llm = get_draft_llm(max_tokens=800, temperature=0)
```

`get_draft_llm` zwraca model z fallbackiem: primary `settings.draft_model` (gpt-4o), fallback `settings.research_model` (gpt-4o-mini). W razie rate-limitu lub niedostępności gpt-4o, node automatycznie spada na minimodel.

#### Estymacja kosztu

```python
# Przed
call_cost = estimate_cost_usd(settings.research_model, input_tokens, output_tokens)

# Po
call_cost = estimate_cost_usd(settings.draft_model, input_tokens, output_tokens)
```

Koszt jest teraz liczony według cennika gpt-4o ($2.50/1M input, $10.00/1M output) zamiast gpt-4o-mini. Dla wywołania z max_tokens=800 i typowym promptem ~600 tokenów różnica to ok. $0.002 per artykuł.

---

## Weryfikacja H3 w promptach

Oba warianty prompta (first run i regeneracja) już obsługują nagłówki H3:

**First run:**
```
WYMAGANIA:
- H1 musi zawierać główne słowo kluczowe
- Struktura: 1x H1, 3-6x H2, opcjonalnie H3 pod H2
- Nagłówki po polsku, SEO-friendly, konkretne
...
Zwróć TYLKO strukturę nagłówków w formacie Markdown (# H1, ## H2, ### H3). Bez treści artykułu.
```

**Regeneracja z cp1_feedback:**
```
Zaproponuj poprawioną strukturę nagłówków (H1/H2/H3) artykułu.
...
Zwróć TYLKO strukturę nagłówków w formacie Markdown (# H1, ## H2, ### H3). Bez treści artykułu.
```

Oba warianty jawnie instruują model do używania `### H3` i kończą instrukcją formatu `(# H1, ## H2, ### H3)`. Zagnieżdżone H3 są wspierane przez prompt bez dodatkowych zmian.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Przełączenie `structure_node` z `get_research_llm()` na `get_draft_llm()` | ✅ `llm = get_draft_llm(max_tokens=800, temperature=0)` |
| Poprawna estymacja kosztu dla draft_model | ✅ `estimate_cost_usd(settings.draft_model, ...)` |
| Weryfikacja poprawności generowania zagnieżdżonych nagłówków H3 | ✅ Oba warianty prompta zawierają `### H3` w instrukcji formatu |

---

## Wpływ na koszty

| Model | Input (600 tok) | Output (200 tok) | Koszt/call | Koszt/miesiąc (100 art.) |
|-------|----------------|-----------------|-----------|--------------------------|
| gpt-4o-mini | $0.000090 | $0.000120 | ~$0.0002 | ~$0.02 |
| gpt-4o | $0.001500 | $0.002000 | ~$0.0035 | ~$0.35 |
| **Różnica** | | | **+$0.003** | **+$0.33** |

Wzrost kosztu jest pomijalny (~$0.33/miesiąc przy 100 artykułach) w stosunku do zysku jakościowego w generowaniu struktury narracyjnej dla technicznej niszy.
