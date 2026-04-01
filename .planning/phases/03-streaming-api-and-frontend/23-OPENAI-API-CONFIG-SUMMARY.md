# 23-OPENAI-API-CONFIG Podsumowanie: Konfiguracja i optymalizacja OpenAI API

**Data ukończenia:** 2026-04-01
**Faza:** 03 — Streaming API i Frontend
**Plan:** 23 — Konfiguracja i optymalizacja OpenAI API
**Status:** ✅ Zakończone

---

## Cel

Scentralizowanie konfiguracji OpenAI API oraz eliminacja rozproszonych, niekonfigurowalnych instancji `ChatOpenAI` / `ChatAnthropic` w węzłach grafu.

**Problemy przed zmianą:**
- 5 węzłów (`researcher`, `structure`, `writer`, `shadow_analyze`, `shadow_annotate`) tworzyło własne instancje LLM z hardkodowanymi parametrami.
- Brak konfiguracji `timeout` — zapytania mogły wisieć w nieskończoność.
- Brak konfiguracji `max_retries` — chwilowe błędy API nie były ponawiane automatycznie.
- Duplikacja logiki `if "claude" in model.lower()` w każdym pliku.

---

## Architektura

```
bond/config.py
    └── Settings
            ├── research_model: str          (RESEARCH_MODEL env)
            ├── draft_model: str             (DRAFT_MODEL env)
            ├── openai_timeout: int = 120    (OPENAI_TIMEOUT env)
            └── openai_max_retries: int = 3  (OPENAI_MAX_RETRIES env)

bond/llm.py
    ├── get_research_llm(max_tokens?, temperature?) → BaseChatModel
    └── get_draft_llm(max_tokens?, temperature?)    → BaseChatModel
            │
            ├── "claude" in model → ChatAnthropic(timeout, max_retries, ...)
            └── else              → ChatOpenAI(timeout, max_retries, ...)

bond/graph/nodes/
    ├── researcher.py    → get_research_llm(max_tokens=2500)
    ├── structure.py     → get_research_llm(max_tokens=800)
    ├── writer.py        → get_draft_llm(max_tokens=4096, temperature=0.7)
    ├── shadow_analyze.py → get_research_llm(max_tokens=2000)
    └── shadow_annotate.py → get_draft_llm(max_tokens=4096, temperature=0)
```

---

## Zmodyfikowane pliki

### `bond/config.py`

Dodano dwa nowe pola konfiguracyjne:

```python
# OpenAI API configuration
openai_timeout: int = 120
openai_max_retries: int = 3
```

Sterowane przez zmienne środowiskowe `OPENAI_TIMEOUT` i `OPENAI_MAX_RETRIES`.

---

### `bond/llm.py` (nowy plik)

Fabryka LLM eksportująca dwie funkcje publiczne:

```python
def get_research_llm(
    max_tokens: int | None = None,   # default: 2500
    temperature: float = 0,
) -> BaseChatModel: ...

def get_draft_llm(
    max_tokens: int | None = None,   # default: 4096
    temperature: float = 0.7,
) -> BaseChatModel: ...
```

Obie funkcje:
- Odczytują model z `settings.research_model` / `settings.draft_model`.
- Stosują `timeout` i `max_retries` z ustawień globalnych.
- Rozgałęziają na `ChatAnthropic` lub `ChatOpenAI` w zależności od nazwy modelu.
- Akceptują opcjonalne nadpisanie `max_tokens` i `temperature` — zachowana kompatybilność z obecnymi wywołaniami.

---

### `bond/graph/nodes/researcher.py`

- Usunięto: `from langchain_anthropic import ChatAnthropic`, `from langchain_openai import ChatOpenAI`, `from bond.config import settings`
- Dodano: `from bond.llm import get_research_llm`
- Zastąpiono blok `if "claude"` wywołaniem `get_research_llm(max_tokens=2500)`

---

### `bond/graph/nodes/structure.py`

- Usunięto: `from langchain_anthropic import ChatAnthropic`, `from langchain_openai import ChatOpenAI`, `from bond.config import settings`, lokalną funkcję `_get_research_llm()`
- Dodano: `from bond.llm import get_research_llm`
- Zastąpiono `llm = _get_research_llm()` wywołaniem `get_research_llm(max_tokens=800)`

---

### `bond/graph/nodes/writer.py`

- Usunięto: `from langchain_anthropic import ChatAnthropic`, `from langchain_openai import ChatOpenAI`
- Dodano: `from bond.llm import get_draft_llm`
- Zastąpiono blok `if "claude"` wywołaniem `get_draft_llm(max_tokens=4096, temperature=0.7)`

---

### `bond/graph/nodes/shadow_analyze.py`

- Usunięto: `from langchain_anthropic import ChatAnthropic`, `from langchain_openai import ChatOpenAI`
- Dodano: `from bond.llm import get_research_llm`
- Zastąpiono blok `if "claude"` wywołaniem `get_research_llm(max_tokens=2000)`

---

### `bond/graph/nodes/shadow_annotate.py`

- Usunięto: `from langchain_anthropic import ChatAnthropic`, `from langchain_openai import ChatOpenAI`, `from bond.config import settings`
- Dodano: `from bond.llm import get_draft_llm`
- Zastąpiono blok `if "claude"` wywołaniem `get_draft_llm(max_tokens=4096, temperature=0)`

---

## Konfiguracja środowiskowa

Nowe opcjonalne zmienne w `.env` (wartości domyślne są bezpieczne na produkcji):

```env
# OpenAI API configuration
OPENAI_TIMEOUT=120      # sekundy; zapobiega wiszeniu zapytań
OPENAI_MAX_RETRIES=3    # automatyczne ponawianie przy błędach przejściowych
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Brak bezpośrednich instancji `ChatOpenAI`/`ChatAnthropic` w węzłach grafu | ✅ Grep po `bond/graph/nodes/*.py` zwraca pusty wynik |
| Timeout konfigurowalny przez `.env` | ✅ `OPENAI_TIMEOUT` → `settings.openai_timeout` → przekazany do fabryki |
| Max retries konfigurowalny przez `.env` | ✅ `OPENAI_MAX_RETRIES` → `settings.openai_max_retries` → przekazany do fabryki |
| Obsługa zarówno OpenAI jak i Anthropic | ✅ Logika `if "claude"` w jednym miejscu (`bond/llm.py`) |
| Istniejące testy przechodzą | ✅ `11 passed in 0.72s` |
| Token budget per węzeł zachowany | ✅ Każdy węzeł przekazuje własny `max_tokens` przez kwarg fabryki |

---

## Domyślne budżety tokenów

| Węzeł | Funkcja | max_tokens | temperature |
|-------|---------|-----------|-------------|
| `researcher` | `get_research_llm` | 2500 | 0 |
| `structure` | `get_research_llm` | 800 | 0 |
| `shadow_analyze` | `get_research_llm` | 2000 | 0 |
| `writer` | `get_draft_llm` | 4096 | 0.7 |
| `shadow_annotate` | `get_draft_llm` | 4096 | 0 |

---

## Weryfikacja

```
PYTHONPATH=. uv run python -c "
from dotenv import load_dotenv; load_dotenv()
from bond.llm import get_research_llm, get_draft_llm
r = get_research_llm()
d = get_draft_llm()
print(type(r).__name__, r.model_name, r.max_tokens)   # ChatOpenAI gpt-4o-mini 2500
print(type(d).__name__, d.model_name, d.max_tokens)   # ChatOpenAI gpt-4o 4096
"
```

Testy jednostkowe:

```
PYTHONPATH=. uv run pytest tests/ -q
11 passed in 0.72s
```
