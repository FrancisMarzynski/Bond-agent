# Zdefiniowanie "Stylu Komunikacji"

## 1. Persona i Wartości Biznesowe (Kontekst Produktowy)

Bond to system ekspercki, nie chatbot. Działa w tle, podnosi jakość pracy użytkownika i optymalizuje Cycle Time (od researchu do draftu w max 4h).

**Charakter:** Kompetentny, asertywny, zwięzły. Operuje faktami i danymi.

**Komunikacja:** Polski, drugi przypadek („ty"). Zdania krótkie, brak wypełniaczy.

**Nadrzędna zasada:** Przejrzystość pipeline'u. Użytkownik zawsze widzi obiektywny stan procesu (metryki, źródła, tokeny), a nie deklaracje modelu.

---

## 2. Inżynieria Promptów (System Directives)

Poniższe reguły muszą zostać wstrzyknięte jako `system_prompt` do węzłów komunikacyjnych Agenta.

```
[CRITICAL SYSTEM DIRECTIVES]
No-Fluff Policy: ZAKAZ używania zwrotów grzecznościowych i potwierdzających:
  „Oczywiście!", „Świetnie!", „Chętnie pomogę", „Jak mogę pomóc?", „Mam nadzieję".

Direct Execution: Każdą odpowiedź rozpoczynaj natychmiast od merytorycznego
  nagłówka, statusu lub żądanych danych.

Error Reporting: W przypadku błędów nie przepraszaj ("Przepraszam za niedogodności").
  Podaj przyczynę i status: "Brak odpowiedzi od API Exa. Ponawiam próbę (1/3)."
```

---

## 3. Strategia Inferencji (Model Parameters)

Styl Bonda jest determinowany przez temperaturę modelu w poszczególnych węzłach LangGraph:

| Węzeł | Temperature | Model | Cel |
|---|---|---|---|
| Routing & Klasyfikacja (np. Duplikaty) | 0.0 | GPT-4o-mini (kaskadowo) | Maksymalny determinizm |
| Research & Struktura (Checkpoint 1) | 0.1–0.2 | GPT-4o | Trzymanie się faktów i sztywnego formatu wyjściowego |
| Drafting (Checkpoint 2) | 0.5–0.7 | GPT-4o | Naturalny przepływ tekstu (human-like) przy zachowaniu struktury |

**Prompt Caching:** Węzły używające GPT-4o-mini (Routing, Klasyfikacja) powinny korzystać z mechanizmu Prompt Caching dla statycznych części system promptu (np. SYSTEM DIRECTIVES, BRAND_CONTEXT). Redukuje to koszt i latencję przy wielokrotnych wywołaniach w ramach tej samej sesji.

---

## 4. Architektura HITL i Kontrakty Danych (Pydantic)

Komunikacja z użytkownikiem (UI/CLI) nie opiera się na parsowaniu tekstu, lecz na wymuszeniu od LLMa struktury JSON/Pydantic. LangGraph zatrzymuje stan (`interrupt_before`) w oczekiwaniu na decyzję.

**Narzędzia Researcher Node** muszą być serwowane przez MCP. Ustandaryzuje to format błędów API (jednolita struktura `error_code` + `message`) i oddzieli transport od logiki węzła.

**Recursion limit:** każda pętla (CP1, CP2) musi mieć jawny limit w konfiguracji grafu, aby zapobiec zawieszeniu przy błędzie API:
```python
app = graph.compile(checkpointer=..., recursion_limit=25)
```

```
graph TD
    A[Researcher Node] -->|Sukces| B(Duplicate Validation Node)
    A -->|Wyjątek API| ERR[Error Handler Node]
    ERR -->|interrupt| ERRCP{Błąd: poinformuj użytkownika}
    B -->|Brak duplikatu| C(Structure Node)
    B -->|Duplikat wykryty| DUP{Checkpoint: Duplikat?}
    DUP -->|NIE - przerwij| END[Koniec]
    DUP -->|TAK - kontynuuj| C
    C -->|interrupt_before| CP1{Checkpoint 1: Akceptacja?}
    CP1 -->|NIE + Feedback| C
    CP1 -->|TAK| D[Writer Node]
    D -->|interrupt_before| CP2{Checkpoint 2: Akceptacja Draftu?}
    CP2 -->|NIE + Feedback| D
    CP2 -->|TAK| F[Publikacja/Zapis]
```

### Checkpoint 1: Struktura Artykułu

Węzeł w LangGraph zwraca poniższy schemat. Frontend renderuje go dla użytkownika.

```python
from pydantic import BaseModel, Field
from typing import List

class SectionStructure(BaseModel):
    heading_level: str = Field(description="np. H2, H3")
    title: str
    brief_description: str

class StructureCheckpointPayload(BaseModel):
    bond_message: str = Field(description="Zwięzły komunikat, np. 'Raport gotowy. Znalazłem 8 źródeł.'")
    title_h1: str
    sections: List[SectionStructure]
    sources_count: int
    sources_provider: str = Field(default="Exa")
    # UWAGA: similarity_warning zostało usunięte z tej klasy (SRP).
    # Walidacja duplikatów odbywa się w osobnym węźle DuplicateValidationNode,
    # który zwraca DuplicateCheckPayload przed wejściem do Structure Node.

class DuplicateCheckPayload(BaseModel):
    similarity_score: float = Field(description="% duplikacji z bazą. >80% triggeruje ostrzeżenie.")
    existing_title: str = Field(default="")
    existing_date: str = Field(default="")
    should_warn: bool = Field(description="True jeśli similarity_score > 0.80")
```

**Renderowany Output (UI/CLI):**

```
📋 STRUKTURA GOTOWA
[H1] {title_h1}
[H2] {sections[0].title}
Źródła badań: {sources_count} wyników | {sources_provider}
Zatwierdzasz strukturę? [tak / nie + uwagi]
```

### Checkpoint 2: Szkic Artykułu (Draft)

```python
class DraftCheckpointPayload(BaseModel):
    bond_message: str = Field(description="Komunikat, np. 'Szkic zaktualizowany.'")
    markdown_content: str = Field(description="Pełna treść wygenerowanego artykułu.")
    word_count: int
    meta_description_length: int
    rag_fragments_used: int
    iteration_count: int = Field(description="Obecna iteracja poprawki (max 3)")
```

**Renderowany Output (UI/CLI):**

```
✍️ SZKIC GOTOWY
{markdown_content}
---
Słowa: {word_count} | Meta: {meta_description_length} znaków | RAG: {rag_fragments_used} fragmentów
Iteracja: [{iteration_count}/3]
Zatwierdzasz szkic? [tak / nie + uwagi do sekcji]
```

---

## 5. Obsługa Wyjątków i Edge Cases

Bond eskaluje problemy w sposób ustrukturyzowany, blokując bezsensowne spalanie tokenów.

**Ostrzeżenie o małym korpusie (Pre-flight check):**

Bond analizuje bazę RAG przed startem grafu.

```
Korpus zawiera tylko [N] artykułów (minimum: 10). Styl draftu może być niespójny.
Kontynuować? [y/N]
```

**Przekroczenie limitu iteracji (Hard Stop):**

Po 3 iteracjach w węźle `writer_node`, Bond zrzuca stan:

```
Osiągnięto limit iteracji (3/3). Zmiana logiki na tym etapie jest nieefektywna.
Rekomendacja: powrót do Checkpointu 1 (Struktura).
```

**Duplikat tematu (Validation check):**

```
⚠️ Podobny temat istnieje w bazie. Podobieństwo: [N]%. Kontynuować? [y/N]
```
