# 08-CHECKPOINT-DECISION-PANEL Podsumowanie: Panel decyzji w punkcie kontrolnym

**Data ukończenia:** 2026-03-13
**Faza:** 03 — Streaming API i Frontend
**Plan:** 08 — Checkpoint Decision Panel
**Status:** ✅ Zakończone

---

## Cel

Rozbudowa panelu decyzyjnego HITL (`CheckpointPanel`) o:
- Pole tekstowe feedbacku widoczne dopiero po kliknięciu "Odrzuć" (zamiast natychmiastowego wysłania bez treści),
- Przycisk "Zapisz do bazy" jako główną akcję zatwierdzenia przy checkpoint_2 (po wygenerowaniu finalnej wersji draftu),
- Poprawkę błędu akcji `approve_save` — backend `CheckpointResponse` nie obsługiwał tej wartości (tylko `approve | reject | abort`).

---

## Zmodyfikowane pliki

### `frontend/src/components/CheckpointPanel.tsx`

#### Poprzedni stan

- Trzy przyciski: "Zatwierdź", "Zatwierdź i Zapisz" (tylko CP2), "Odrzuć"
- "Odrzuć" natychmiast wywoływał `resumeStream(threadId, "reject", null)` bez zbierania feedbacku
- "Zatwierdź i Zapisz" wysyłał akcję `approve_save` — nieobsługiwaną przez backend (powodowało `ValidationError` w `CheckpointResponse`)

#### Nowy stan

- **Checkpoint 1**: "Zatwierdź" + "Odrzuć"
- **Checkpoint 2**: "Zapisz do bazy" (= `approve`) + "Odrzuć"
- **Pole feedbacku**: po kliknięciu "Odrzuć" przycisk zamienia się w "Anuluj", a pod wierszem z przyciskami pojawia się:
  - `<label>` — "Opisz, co należy poprawić:"
  - `<Textarea>` z placeholderem i `autoFocus`
  - Przycisk "Wyślij poprawki" (variant=destructive), który wywołuje `resumeStream(threadId, "reject", feedbackText.trim() || null)`

#### Lokalne stany React

```tsx
const [showFeedbackField, setShowFeedbackField] = useState(false);
const [feedbackText, setFeedbackText] = useState("");
```

Stan jest czyszczony po każdej akcji (approve, reject submit, cancel) — panel wraca do stanu wyjściowego po każdym wznowieniu.

---

## Architektura przepływu

```
Użytkownik widzi CheckpointPanel (hitlPause !== null && !isStreaming)
    │
    ├─ Kliknięcie "Zatwierdź" / "Zapisz do bazy"
    │       └─ resumeStream(threadId, "approve", null)
    │               └─ POST /api/chat/resume {action: "approve"}
    │                       └─ LangGraph: checkpoint_1 → writer → checkpoint_2
    │                                             lub: checkpoint_2 → save_metadata → done
    │
    └─ Kliknięcie "Odrzuć"
            └─ setShowFeedbackField(true) [lokalny stan]
                    │
                    ├─ Anuluj → setShowFeedbackField(false) [powrót do widoku przycisków]
                    │
                    └─ Wyślij poprawki (z feedbackiem lub bez)
                            └─ resumeStream(threadId, "reject", feedbackText)
                                    └─ POST /api/chat/resume {action: "reject", feedback: "..."}
                                            └─ LangGraph: checkpoint_1 → structure (pętla)
                                                              lub: checkpoint_2 → writer (pętla)
```

---

## Poprawka błędu: `approve_save`

**Problem:** Poprzedni przycisk "Zatwierdź i Zapisz" wywoływał `resumeStream(threadId, "approve_save", null)`. Backend budował `resume_value = {"action": "approve_save"}` i przekazywał go do `Command(resume=...)`. Węzeł `checkpoint_2_node` próbował `CheckpointResponse(**{"action": "approve_save"})`, co rzucało `ValidationError` ponieważ `CheckpointResponse.action: Literal["approve", "reject", "abort"]` nie zawiera `"approve_save"`.

**Rozwiązanie:** Przycisk "Zapisz do bazy" wysyła akcję `approve`. Zapis do bazy jest i tak zawsze gwarantowany przez graph routing — zatwierdzenie checkpoint_2 zawsze kieruje do węzła `save_metadata` → END.

```python
# graph.py — _route_after_cp2
def _route_after_cp2(state: AuthorState) -> str:
    if state.get("cp2_approved"):
        return "save_metadata"   # Zapis zawsze następuje po approve
    return "writer"
```

---

## UX: Dlaczego jeden przycisk zatwierdzający dla CP2?

Przy checkpoint_2 nie istnieje ścieżka "zatwierdź bez zapisu" — `_route_after_cp2` zawsze kieruje do `save_metadata` po `approve`. Dwa przyciski zatwierdzające tworzyłyby fałszywą dwuznaczność. Przycisk "Zapisz do bazy" z ikoną `Database` komunikuje wprost, co się stanie.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Przyciski "Zatwierdź" / "Odrzuć" widoczne po zatrzymaniu strumienia | ✅ Panel renderuje się gdy `hitlPause !== null && !isStreaming` |
| Pole tekstowe widoczne wyłącznie po kliknięciu "Odrzuć" | ✅ `showFeedbackField` kontroluje widoczność `<Textarea>` |
| Feedback przekazywany do backendu przy odrzuceniu | ✅ `resumeStream(threadId, "reject", feedbackText.trim() || null)` |
| Przycisk "Zapisz do bazy" przy finalnej wersji (CP2) | ✅ Renderowany gdy `isCheckpoint2 === true`; wysyła `approve` |
| Poprawka błędu `approve_save` | ✅ Usunięto — akcja `approve` jest poprawna i wystarczająca |
| Możliwość anulowania odrzucenia bez wysyłania | ✅ Przycisk "Anuluj" chowa pole i wraca do widoku przycisków |
| Czyszczenie stanu po każdej akcji | ✅ `setShowFeedbackField(false); setFeedbackText("")` we wszystkich handlerach |
| TypeScript — brak błędów kompilacji | ✅ `npx tsc --noEmit` bez błędów |

---

## Weryfikacja

```bash
cd frontend && npx tsc --noEmit
# Brak błędów
```

Ręczna weryfikacja komponentu obejmuje:
- Checkpoint_1: widoczny "Zatwierdź" + "Odrzuć" → po kliknięciu "Odrzuć" pojawia się textarea → "Wyślij poprawki" wywołuje reject z feedbackiem
- Checkpoint_2: widoczny "Zapisz do bazy" (zielony) + "Odrzuć" z licznikiem iteracji → przepływ feedbacku identyczny jak CP1
- Kliknięcie "Zatwierdź"/"Zapisz do bazy" czyści stan pola feedbacku
- Panel znika natychmiast po wywołaniu `resumeStream` (store ustawia `isStreaming=true` → `hitlPause=null`)
