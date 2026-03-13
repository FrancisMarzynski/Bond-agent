# 10 — Corpus Add Form: Formularze dodawania treści (Tekst / Link / Plik)

## Cel

Intuicyjne zasilanie systemu RAG przez sidebar aplikacji. Użytkownik może dodawać artykuły do bazy wiedzy w trzech trybach: przez wklejenie tekstu, podanie adresu URL lub przesłanie pliku (PDF / DOCX / TXT) metodą drag & drop.

---

## Zrealizowane wymagania

| Wymaganie | Status |
|---|---|
| Zakładki (Tabs) dla Tekst / Link / Plik | ✅ |
| Integracja z `POST /api/corpus/ingest/text` | ✅ |
| Integracja z `POST /api/corpus/ingest/url` | ✅ |
| Integracja z `POST /api/corpus/ingest/file` | ✅ |
| Drag & Drop dla PDF / DOCX / TXT | ✅ |
| Wybór źródła (własne / zewn.) per zakładka | ✅ |
| Komunikaty sukcesu i błędu | ✅ |
| Automatyczne odświeżenie statusu bazy po dodaniu | ✅ |
| Przycisk "+" w nagłówku CorpusStatusPanel | ✅ |

---

## Nowe pliki

### `frontend/src/components/CorpusAddForm.tsx`

Samodzielny komponent formularza z trzema zakładkami.

**Struktura:**

```
CorpusAddForm
├── Header: "Dodaj treść" + przycisk zamknięcia (X)
├── Tabs: Tekst | Link | Plik
├── Tab content (warunkowe):
│   ├── Tekst: tytuł (opt.) + textarea + SourceTypeToggle + "Dodaj"
│   ├── Link: input[url] + hint + SourceTypeToggle + "Pobierz"
│   └── Plik: DropZone (klik lub drag) + tytuł (opt.) + SourceTypeToggle + "Prześlij"
└── Feedback banners: SuccessBanner | ErrorBanner
```

**Pomocniczy komponent `SourceTypeToggle`:**
- Segmented toggle button z opcjami `własne` / `zewn.`
- Różne wartości domyślne per zakładka: Tekst/Plik → `own`, Link → `external`

**Zakładka Plik — DropZone:**
- Obsługuje `onDragOver` / `onDragLeave` / `onDrop` (wizualne podświetlenie obramowania)
- Kliknięcie wywołuje ukryty `<input type="file" accept=".pdf,.docx,.txt">`
- Walidacja MIME type + rozszerzenia (PDF, DOCX, TXT)
- Po wyborze pliku: wyświetla nazwę, rozmiar (KB), input na tytuł
- Przesyłanie przez `FormData` (multipart/form-data)

**Przepływ po sukcesie:**
1. Wyświetla `SuccessBanner` z liczbą dodanych fragmentów
2. Po 1,5 s wywołuje `onSuccess()` → zamknięcie formularza + odświeżenie statusu

**Obsługa błędów:**
- Walidacja lokalna (puste pola) — komunikat natychmiastowy
- Błąd HTTP — parsuje `detail` z odpowiedzi lub fallback na `HTTP {status}`
- `ErrorBanner` z ikoną `AlertCircle` i czerwonym tłem

---

## Zmodyfikowane pliki

### `frontend/src/components/CorpusStatusPanel.tsx`

Zmiany:
1. **Przycisk "+"** po prawej stronie nagłówka — toggleuje `showAddForm`
2. **Stan `showAddForm`** — kontroluje widoczność `CorpusAddForm`
3. **Funkcja `fetchStatus`** wyekstrahowana poza `useEffect` (z `useCallback`) — umożliwia ponowne wywołanie po dodaniu dokumentu
4. **`handleAddSuccess`** — zamyka formularz i wywołuje `fetchStatus()`
5. Układ nagłówka zmieniony z `<button>` na `<div>` z dwoma przyciskami (expand + add)

---

## Integracje backendowe

| Zakładka | Endpoint | Content-Type | Body |
|---|---|---|---|
| Tekst | `POST /api/corpus/ingest/text` | `application/json` | `{ text, title, source_type }` |
| Link | `POST /api/corpus/ingest/url` | `application/json` | `{ url, source_type }` |
| Plik | `POST /api/corpus/ingest/file` | `multipart/form-data` | `file`, `source_type`, `title` |

Odpowiedzi:
- Tekst/Plik → `IngestResult { article_id, title, chunks_added, source_type, warnings }`
- Link → `BatchIngestResult { articles_ingested, total_chunks, source_type, warnings }`

---

## Decyzje projektowe

- **Inline w sidebarze (nie modal)** — mniej przełączeń kontekstu, spójna z resztą panelu bocznego
- **Reset stanu przy zmianie zakładki** — `resetState()` czyści error/success, unika fałszywych komunikatów
- **`setTimeout(onSuccess, 1500)`** — użytkownik widzi potwierdzenie przed zamknięciem formularza
- **Brak globalnego store** — formularz jest lokalny, tylko wywołuje callback do rodzica
- **Natywny `fetch` zamiast biblioteki** — projekt nie używa axios/react-query, spójność z resztą kodu

---

## Struktura komponentów po zmianach

```
Sidebar
└── CorpusStatusPanel
    ├── [+] button → showAddForm toggle
    ├── CorpusAddForm (gdy showAddForm=true)
    │   ├── Tab: Tekst
    │   ├── Tab: Link
    │   └── Tab: Plik (DropZone)
    ├── [expand/collapse] → tabela dokumentów
    └── status: article_count, chunk_count, warning
```
