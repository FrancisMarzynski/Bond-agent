# 09-CORPUS-STATUS-PANEL Podsumowanie: Panel statusu bazy wiedzy

**Data ukończenia:** 2026-03-13
**Faza:** 03 — Streaming API i Frontend
**Plan:** 09 — Corpus Status Panel
**Status:** ✅ Zakończone

---

## Cel

Implementacja panelu statusu korpusu dokumentów w bocznym panelu (Sidebar) aplikacji.

- Tabela z listą dokumentów (nazwa, źródło, data dodania) pobierana z `/api/corpus/status`.
- Liczniki artykułów i fragmentów (chunks) wyświetlane na stałe.
- Ostrzeżenie przy małej liczbie danych (gdy backend zwraca `low_corpus_warning`).
- Panel zwijany/rozwijany (chevron toggle) — lista dokumentów widoczna po rozwinięciu.

---

## Architektura

```
Sidebar.tsx
    └─ CorpusStatusPanel.tsx
           │
           └─ GET /api/corpus/status (FastAPI)
                      │
                      ├─ article_count (z corpus_articles)
                      ├─ chunk_count (suma z corpus_articles)
                      ├─ low_corpus_warning (gdy < settings.low_corpus_threshold)
                      └─ documents[] (lista artykułów z corpus_articles)
```

---

## Zmodyfikowane pliki

### `bond/store/article_log.py`

Dodano funkcję `get_articles()` zwracającą listę słowników z danymi artykułów:

```python
def get_articles() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT article_id, title, source_type, source_url, chunk_count, ingested_at "
        "FROM corpus_articles ORDER BY ingested_at DESC"
    ).fetchall()
    conn.close()
    return [
        {
            "article_id": row[0],
            "title": row[1] or row[0],
            "source_type": row[2],
            "source_url": row[3] or "",
            "chunk_count": row[4] or 0,
            "ingested_at": row[5],
        }
        for row in rows
    ]
```

Artykuły są sortowane od najnowszych (`ORDER BY ingested_at DESC`).

### `bond/api/routes/corpus.py`

1. Importowano `get_articles` z `bond.store.article_log`.
2. Dodano model Pydantic `DocumentInfo`:

```python
class DocumentInfo(BaseModel):
    article_id: str
    title: str
    source_type: str
    source_url: str
    chunk_count: int
    ingested_at: str | None = None
```

3. Rozszerzono `CorpusStatus` o pole `documents: list[DocumentInfo] = []`.
4. Zaktualizowano endpoint `GET /api/corpus/status` — pobiera listę artykułów i dołącza do odpowiedzi:

```python
documents = [DocumentInfo(**doc) for doc in get_articles()]

return CorpusStatus(
    article_count=article_count,
    chunk_count=chunk_count,
    low_corpus_warning=warning,
    documents=documents,
)
```

Endpoint pozostaje wstecznie kompatybilny — `documents` domyślnie `[]`.

### `frontend/src/components/CorpusStatusPanel.tsx` (nowy plik)

Nowy komponent React (`"use client"`):

- Używa `useEffect` + `fetch` do jednorazowego pobrania `/api/corpus/status` przy montowaniu (zgodnie z wzorcem w `useSession.ts`).
- Stany: `status`, `loading`, `error`, `expanded`.
- Zmienne `API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"` — zgodnie z wzorcem projektu.
- Formatowanie dat: `toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit", year: "2-digit" })`.
- Etykiety źródeł: `own → "własne"`, `external → "zewn."`.

**Zachowanie UI:**
- Nagłówek "Baza wiedzy" z chevronem toggle.
- Counts zawsze widoczne: ikona BookOpen + liczba artykułów, ikona Layers + liczba fragmentów.
- Ostrzeżenie (amber, ikona AlertTriangle) gdy `low_corpus_warning !== null`.
- Po rozwinięciu: tabela z kolumnami Nazwa / Źródło / Data, maks. 208px wysokości (scroll).
- Tytuły dokumentów obcięte z `truncate` i pełną treścią w `title` (tooltip).

### `frontend/src/components/Sidebar.tsx`

Dodano import `CorpusStatusPanel` i renderowanie na dole sidebar (po `</nav>`):

```tsx
import { CorpusStatusPanel } from "@/components/CorpusStatusPanel";
// ...
<nav className="flex-1 overflow-y-auto p-2 space-y-1">
  {/* ...sesje... */}
</nav>
<CorpusStatusPanel />
```

`CorpusStatusPanel` ma `shrink-0` — nie kompresuje listy sesji.

---

## Schemat odpowiedzi API po zmianach

```json
GET /api/corpus/status

{
  "article_count": 5,
  "chunk_count": 87,
  "low_corpus_warning": "Corpus contains only 5 article(s). Recommend at least 10 articles for reliable style retrieval.",
  "documents": [
    {
      "article_id": "a1b2c3",
      "title": "Przykładowy artykuł",
      "source_type": "own",
      "source_url": "https://example.com/art",
      "chunk_count": 12,
      "ingested_at": "2026-03-10T14:22:00+00:00"
    }
  ]
}
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Tabela z listą dokumentów (nazwa, źródło, data) | ✅ Renderowana w `CorpusStatusPanel` po rozwinięciu |
| Licznik fragmentów pobierany z `/api/corpus/status` | ✅ `chunk_count` wyświetlany z ikoną Layers |
| Licznik artykułów pobierany z `/api/corpus/status` | ✅ `article_count` wyświetlany z ikoną BookOpen |
| Ostrzeżenie przy małej ilości danych | ✅ Amber baner gdy `low_corpus_warning !== null` (próg ustawiany w `settings.low_corpus_threshold`) |
| Panel zintegrowany z istniejącym Sidebar | ✅ Renderowany na dole sidebar, nie kompresuje listy sesji |
| Zgodność z wzorcami pobierania danych w projekcie | ✅ `fetch` + `useState/useEffect` + `NEXT_PUBLIC_API_URL` |

---

## Szczegóły implementacji

### Zabezpieczenia

- Flaga `cancelled` w `useEffect` zapobiega aktualizacji stanu po odmontowaniu komponentu (unikanie memory leaks).
- Obsługa błędów HTTP (`res.ok` check) i wyjątków sieciowych.

### Formatowanie dat

Data `ingested_at` jest w formacie ISO 8601 z UTC. Funkcja `formatDate()` używa `new Date(iso)` + `toLocaleDateString("pl-PL")` → format `DD.MM.RR`.

### Kompatybilność wsteczna API

Pole `documents` ma domyślną wartość `[]` w modelu Pydantic — istniejące klienty API nie są dotknięte zmianą.
