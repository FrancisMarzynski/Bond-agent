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
| Walidacja rozmiaru pliku (max 50 MB) | ✅ |
| Komunikaty sukcesu i błędu | ✅ |
| Automatyczne odświeżenie statusu bazy po dodaniu | ✅ |
| Przycisk "+" w nagłówku CorpusStatusPanel | ✅ |
| Centralizacja stałych konfiguracyjnych w `src/config.ts` | ✅ |

---

## Nowe pliki

### `frontend/src/config.ts`

Centralny plik stałych konfiguracyjnych aplikacji frontendowej.

```ts
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024; // 50 MB
```

Wszystkie komponenty i hooki importują `API_URL` wyłącznie z tego pliku — brak duplikacji fallbacku `localhost:8000` w kodzie źródłowym.

---

### `frontend/src/components/CorpusAddForm.tsx`

Samodzielny komponent formularza z trzema zakładkami.

**Struktura:**

```
CorpusAddForm
├── Header: "Dodaj treść" + przycisk zamknięcia (X)
├── Tabs: Tekst | Link | Plik
├── Tab content (warunkowe):
│   ├── Tekst: tytuł (opt.) + textarea + SourceTypeToggle + [✓ Dodano] + "Dodaj"
│   ├── Link: input[url] + hint + SourceTypeToggle + [✓ Pobrano] + "Pobierz"
│   └── Plik: DropZone (klik lub drag) + tytuł (opt.) + SourceTypeToggle + [✓ Wysłano] + "Prześlij"
└── ErrorBanner
```

**Pomocniczy komponent `SourceTypeToggle`:**
- Segmented toggle button z opcjami `własne` / `zewn.`
- Różne wartości domyślne per zakładka: Tekst/Plik → `own`, Link → `external`

**Zakładka Plik — DropZone:**
- Obsługuje `onDragOver` / `onDragLeave` / `onDrop` (wizualne podświetlenie obramowania)
- Kliknięcie wywołuje ukryty `<input type="file" accept=".pdf,.docx,.txt">`
- Walidacja kolejności: **rozmiar → MIME type + rozszerzenie** (PDF, DOCX, TXT)
- Limit rozmiaru: **50 MB** (`MAX_FILE_SIZE_BYTES` z `config.ts`); błąd zawiera faktyczny rozmiar pliku i limit
- Po wyborze pliku: wyświetla nazwę, rozmiar (KB), input na tytuł
- Przesyłanie przez `FormData` (multipart/form-data)

**Przepływ po sukcesie:**
1. Pola formularza są natychmiast resetowane
2. `onSuccess()` wywoływany od razu — rodzic odświeża liczniki bazy wiedzy
3. Przy przycisku pojawia się inline wskaźnik (`✓ Dodano / Pobrano / Wysłano`)
4. Po 2 s wskaźnik znika (`useEffect` + `setTimeout`)
5. **Formularz pozostaje otwarty** — użytkownik może od razu dodać kolejny element

**Obsługa błędów:**
- Walidacja lokalna (puste pola, zbyt duży plik) — komunikat natychmiastowy
- Błąd HTTP — parsuje `detail` z odpowiedzi lub fallback na `HTTP {status}`
- `ErrorBanner` z ikoną `AlertCircle` i czerwonym tłem

---

## Zmodyfikowane pliki

### `frontend/src/components/CorpusStatusPanel.tsx`

Zmiany:
1. **Przycisk "+"** po prawej stronie nagłówka — toggleuje `showAddForm`
2. **Stan `showAddForm`** — kontroluje widoczność `CorpusAddForm`
3. **Funkcja `fetchStatus`** wyekstrahowana poza `useEffect` (z `useCallback`) — umożliwia ponowne wywołanie po dodaniu dokumentu
4. **`handleAddSuccess`** — wywołuje wyłącznie `fetchStatus()`; formularz **nie jest zamykany automatycznie** — użytkownik decyduje samodzielnie
5. Układ nagłówka zmieniony z `<button>` na `<div>` z dwoma przyciskami (expand + add)
6. Import `API_URL` z `@/config`

### `frontend/src/hooks/useStream.ts`

- Usunięto lokalne `const API_URL = ...`
- Import `API_URL` z `@/config`

### `frontend/src/hooks/useSession.ts`

- Usunięto lokalne `const API_URL = ...` wewnątrz funkcji `loadSessionHistory`
- Import `API_URL` z `@/config`

---

## Integracje backendowe

| Zakładka | Endpoint | Content-Type | Body |
|---|---|---|---|
| Tekst | `POST /api/corpus/ingest/text` | `application/json` | `{ text, title, source_type }` |
| Link | `POST /api/corpus/ingest/url` | `application/json` | `{ url, source_type }` |
| Plik | `POST /api/corpus/ingest/file` | `multipart/form-data` | `file`, `source_type`, `title` |

---

## Decyzje projektowe

- **Inline w sidebarze (nie modal)** — mniej przełączeń kontekstu, spójna z resztą panelu bocznego
- **Reset stanu przy zmianie zakładki** — `resetState()` czyści error/justSucceeded, unika fałszywych komunikatów
- **Formularz nie zamyka się po sukcesie** — użytkownik może dodawać kolejne elementy bez ponownego otwierania; zamknięcie przez X lub przycisk „+"
- **`justSucceeded` zamiast `success` state** — lekki boolean zamiast przechowywania całej odpowiedzi API; auto-reset po 2 s przez `useEffect`
- **Walidacja rozmiaru po stronie klienta** — zapobiega zamrożeniu przeglądarki przy parsowaniu dużych plików i eliminuje niejasne błędy 413 z serwera
- **Stałe w `src/config.ts`** — jeden punkt do zmiany URL API i limitów; brak duplikacji fallbacku w komponentach i hookach
- **Brak globalnego store** — formularz jest lokalny, tylko wywołuje callback do rodzica
- **Natywny `fetch` zamiast biblioteki** — projekt nie używa axios/react-query, spójność z resztą kodu

---

## Struktura komponentów po zmianach

```
Sidebar
└── CorpusStatusPanel
    ├── [+] button → showAddForm toggle
    ├── CorpusAddForm (gdy showAddForm=true)
    │   ├── Tab: Tekst  → [✓ Dodano] po sukcesie
    │   ├── Tab: Link   → [✓ Pobrano] po sukcesie
    │   └── Tab: Plik (DropZone) → [✓ Wysłano] po sukcesie
    ├── [expand/collapse] → tabela dokumentów
    └── status: article_count, chunk_count, warning
```
