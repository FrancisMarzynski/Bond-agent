# 44 — Checkpoint 1: Widok Raportu Badawczego

## Co zostało zmienione

`CheckpointPanel.tsx` otrzymał zwijającą się sekcję „Raport Badawczy", widoczną wyłącznie przy Checkpoint 1. Raport trafia z backendu przez payload eventu `hitl_pause` — pola `research_report` dodano do schematu Zod oraz typu `HitlPause`.

---

## Problem

Po zakończeniu `researcher_node` raport trafiał do stanu LangGraph (`research_report`), ale frontend go nie wyświetlał.  
Użytkownik widział jedynie komunikat postępu w `StageProgress`, a następnie od razu Checkpoint 1 z prośbą o zatwierdzenie struktury nagłówków.  
Zatwierdził strukturę bez możliwości przeczytania badań, na których była ona oparta — co podważało sens etapu human-in-the-loop.

---

## Zmiany

### `bond/graph/nodes/checkpoint_1.py`

Brak zmian — `research_report` był już obecny w payloadzie `interrupt()` (linia 56):

```python
user_response = interrupt({
    "checkpoint": "checkpoint_1",
    ...
    "research_report": state.get("research_report", ""),
    ...
})
```

### `frontend/src/store/chatStore.ts`

Dodano pola do typu `HitlPause`:

```ts
research_report?: string;
heading_structure?: string;
```

### `frontend/src/hooks/useStream.ts`

Dodano pola do `HitlPauseSchema` (Zod) oraz do wywołania `store.setHitlPause(...)`:

```ts
const HitlPauseSchema = z.object({
    ...
    research_report: z.string().optional(),
    heading_structure: z.string().optional(),
    ...
});

store.setHitlPause({
    ...
    research_report: result.data.research_report,
    heading_structure: result.data.heading_structure,
    ...
});
```

### `frontend/src/components/CheckpointPanel.tsx`

| Aspekt | Przed | Po |
|---|---|---|
| Sekcja raportu | Brak | Renderowana gdy `isCheckpoint1 && researchReport` |
| Stan zwinięcia | — | `researchOpen` (domyślnie `true`) |
| Ikony nagłówka | — | `ChevronDown` / `ChevronRight` + `ScrollText` z lucide-react |
| Prezentacja tekstu | — | `<pre>` z `whitespace-pre-wrap`, `max-h-60`, `overflow-y-auto` |

**Warunek widoczności** (sprawdzany bezpośrednio przez `checkpoint_id`, nie przez negację pozostałych stanów):
```tsx
const isCheckpoint1 = hitlPause.checkpoint_id === "checkpoint_1";

{isCheckpoint1 && researchReport && (
  <div className="flex flex-col gap-1.5">
    <button onClick={() => setResearchOpen((o) => !o)} ...>
      {researchOpen ? <ChevronDown /> : <ChevronRight />}
      <ScrollText />
      Raport Badawczy
    </button>
    {researchOpen && (
      <pre className="text-xs ... max-h-60 overflow-y-auto ...">
        {researchReport}
      </pre>
    )}
  </div>
)}
```

---

## Decyzje projektowe

- Sekcja jest domyślnie otwarta (`useState(true)`) — użytkownik powinien zobaczyć raport bez dodatkowego kliknięcia.
- Widoczna tylko przy `checkpoint_1` — przy `checkpoint_2` raport badawczy nie jest potrzebny (użytkownik ocenia już gotowy draft).
- `<pre>` z `font-sans` i `whitespace-pre-wrap` zachowuje formatowanie Markdown raportu (nagłówki, listy, numery źródeł) bez potrzeby renderowania HTML.
- Scroll ograniczony do `max-h-60` (240 px) — raport może mieć 6000–12 000 znaków, sekcja nie może dominować nad panelem akcji.
- Zod domyślnie stripuje nieznane pola — stąd konieczność jawnego dodania `research_report` do schematu i destrukturyzacji w `setHitlPause`.

---

## Kryteria akceptacji

- [x] `research_report` przekazywany w payloadzie eventu `hitl_pause` dla `checkpoint_1`
- [x] Zwijana sekcja „Raport Badawczy" w `CheckpointPanel.tsx`
- [x] Sekcja domyślnie otwarta
- [x] Sekcja niewidoczna przy `checkpoint_2` i `duplicate_check`
- [x] Typ `HitlPause` i schema Zod zaktualizowane

---

## Zmodyfikowane pliki

- `frontend/src/store/chatStore.ts`
- `frontend/src/hooks/useStream.ts`
- `frontend/src/components/CheckpointPanel.tsx`
