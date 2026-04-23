# 50-CORPUS-INGESTION-FORM Podsumowanie: UI — IngestionForm z 4 kanałami korpusu

**Data ukończenia:** 2026-04-23  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** UI — IngestionForm – Obsługa 4 kanałów korpusu  
**Status:** ✅ Zakończone

---

## Cel

Umożliwienie zasilania bazy wiedzy bezpośrednio z interfejsu użytkownika przez cztery kanały ingestion.

- `CorpusAddForm` obsługuje cztery zakładki: **Tekst**, **Link**, **Plik** (PDF/DOCX/TXT) i **Drive** (Google Drive folder).
- Każda zakładka wysyła żądanie do odpowiedniego endpointu `/api/corpus/ingest/*`.
- Progress bar (symulowany) pojawia się natychmiast po kliknięciu "Dodaj/Pobierz/Prześlij/Indeksuj" i znika po 3 sekundach od sukcesu.
- Ujednolicony baner sukcesu zastąpił per-zakładkowe inline teksty — wyświetla kontekstowy komunikat z liczbą zaindeksowanych plików (Drive) lub ogólny status (pozostałe kanały).

---

## Architektura

```
CorpusStatusPanel (Sidebar)
  └─ CorpusAddForm
        ├─ [Tabs] Tekst | Link | Plik | Drive
        ├─ [Progress bar] — widoczny gdy progress > 0 (loading + 3s po sukcesie)
        ├─ [Tab content] — form per zakładka
        ├─ [SuccessBanner] — emerald, 3s auto-clear
        └─ [ErrorBanner]  — destructive, inline

State
  loading: bool                ← true podczas fetch
  progress: number (0–100)    ← symulowany przez useEffect + setInterval
  justSucceeded: bool         ← true przez 3s po sukcesie
  successMsg: string          ← kontekstowy komunikat sukcesu
  error: string | null        ← błąd HTTP lub walidacji

Routing (fetch targets)
  Tekst  → POST /api/corpus/ingest/text  { text, title, source_type }
  Link   → POST /api/corpus/ingest/url   { url, source_type }
  Plik   → POST /api/corpus/ingest/file  multipart/form-data
  Drive  → POST /api/corpus/ingest/drive { folder_id, source_type }
```

---

## Zaimplementowane zmiany — `src/components/CorpusAddForm.tsx`

### 1. Typ zakładek rozszerzony o "drive"

```ts
type Tab = "text" | "link" | "file" | "drive";
```

### 2. Symulowany progress bar (`useEffect` + `setInterval`)

```tsx
useEffect(() => {
  let intervalId, timeoutId;

  if (loading) {
    setProgress(5);                    // natychmiast widoczny
    intervalId = setInterval(() => {
      setProgress(p => Math.min(p + Math.random() * 12 + 3, 85));  // rośnie do 85
    }, 400);
  } else if (justSucceeded) {
    setProgress(100);                  // skok do 100% po sukcesie
  } else {
    timeoutId = setTimeout(() => setProgress(0), 600);  // powolne zniknięcie
  }

  return () => { clearInterval(intervalId); clearTimeout(timeoutId); };
}, [loading, justSucceeded]);
```

Wyświetlanie:
```tsx
{progress > 0 && (
  <Progress value={progress} className="h-0.5 rounded-none" />
)}
```

Pasek renderuje się między nagłówkiem a zakładkami — pełna szerokość, 2px wysokości. Wartość 0 = ukryty (translateX(-100%) w komponencie Progress).

### 3. Ujednolicony baner sukcesu

Poprzednia implementacja: trzy osobne per-zakładkowe `{justSucceeded && <span>Dodano/Pobrano/Wysłano</span>}`.

Nowa implementacja: jeden `SuccessBanner()` na dole panelu:

```tsx
function SuccessBanner() {
  if (!justSucceeded) return null;
  return (
    <div className="flex items-start gap-1.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 px-2 py-1.5">
      <CheckCircle2 className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" />
      <p className="text-xs text-emerald-600 dark:text-emerald-400 leading-snug">{successMsg}</p>
    </div>
  );
}
```

`successMsg` per-kanał:
| Kanał | successMsg |
|-------|-----------|
| Tekst | "Tekst dodany do korpusu" |
| Link  | "Artykuł pobrany i dodany" |
| Plik  | "Plik zaindeksowany" |
| Drive | "Zaindeksowano N plik(ów) · M fragmentów" (z `data.articles_ingested` i `data.total_chunks`) |

### 4. Zakładka Drive (nowa)

Stan:
```ts
const [driveFolder, setDriveFolder] = useState("");
const [driveSource, setDriveSource] = useState<SourceType>("own");
```

Submit handler:
```tsx
async function handleDriveSubmit(e: FormEvent) {
  const trimmed = driveFolder.trim();
  if (!trimmed) { setError("Podaj ID folderu Google Drive."); return; }
  setLoading(true);
  const res = await fetch(`${API_URL}/api/corpus/ingest/drive`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_id: trimmed, source_type: driveSource }),
  });
  // ...
  setSuccessMsg(`Zaindeksowano ${data.articles_ingested} plik(ów) · ${data.total_chunks} fragmentów`);
}
```

UI zakładki Drive:
```
┌─────────────────────────────────┐
│ [ID_FOLDERU_DRIVE   ] (mono)   │
│  ID z URL: …/folders/ID        │
│  [własne|zewn.]    [Indeksuj]  │
└─────────────────────────────────┘
```

### 5. Zaktualizowana lista zakładek

```tsx
const tabs = [
  { id: "text",  label: "Tekst",  icon: <FileText  className="h-3 w-3" /> },
  { id: "link",  label: "Link",   icon: <Link2     className="h-3 w-3" /> },
  { id: "file",  label: "Plik",   icon: <Upload    className="h-3 w-3" /> },
  { id: "drive", label: "Drive",  icon: <HardDrive className="h-3 w-3" /> },
];
```

---

## Backend endpoints (bez zmian)

| Endpoint | Metoda | Payload | Response |
|----------|--------|---------|----------|
| `/api/corpus/ingest/text` | POST | `{ text, title, source_type }` | `IngestResult` |
| `/api/corpus/ingest/url`  | POST | `{ url, source_type }` | `BatchIngestResult` |
| `/api/corpus/ingest/file` | POST | multipart: `file, source_type, title` | `IngestResult` |
| `/api/corpus/ingest/drive`| POST | `{ folder_id, source_type }` | `BatchIngestResult` |

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Obsługa czterech modułów: Tekst, Plik (PDF/DOCX), Link do bloga, Google Drive | ✅ Cztery zakładki — każda z osobnym formularzem i handlerem; Drive POST do `/api/corpus/ingest/drive` |
| Wyświetlanie statusu operacji (Progress Bar/Toast) po wysłaniu danych | ✅ Progress bar (`<Progress />`) symulowany 5→85% podczas loading, skok do 100% na sukces; ujednolicony `SuccessBanner` z kontekstowym komunikatem; auto-clear po 3s |

---

## Decyzje projektowe

| Decyzja | Uzasadnienie |
|---------|--------------|
| Symulowany progress (setInterval) zamiast prawdziwego upload progress | `fetch()` z JSON/FormData nie daje natywnego `upload.onprogress` dostępnego bez `XMLHttpRequest`; symulacja jest standardowym UX pattern dla API calls z nieznanym czasem trwania |
| Progress bar między nagłówkiem a zakładkami | Pełna szerokość bez dodatkowych marginesów; h-0.5 (2px) nie zakłóca layoutu |
| Ujednolicony `SuccessBanner` zamiast per-zakładkowych inline tekstów | Jeden punkt utrzymania; Drive wymaga wielowierszowego komunikatu z liczbami (artykuły + fragmenty) |
| `justSucceeded` trwa 3s (poprzednio 2s) | Dodatkowa sekunda na przeczytanie komunikatu Drive (dłuższy tekst) |
| `resetState()` czyści `successMsg` przy zmianie zakładki | Unika sytuacji gdy wiadomość o sukcesie z Tekstu pojawia się po przejściu do Drive |
| Domyślny `source_type` Drive = "own" | Pliki z Drive użytkownika są najczęściej własnymi tekstami; zmniejsza friction |
| Input `font-mono` dla folder_id | ID folderu Drive to ciąg znaków (33 znaki alfanum) — monospace ułatwia weryfikację |
| Walidacja pliku (MIME + rozszerzenie) po stronie frontendu | Natychmiastowy feedback bez round-trip do serwera; backend i tak waliduje po swojej stronie |

---

## Weryfikacja

TypeScript — brak błędów kompilacji:

```bash
cd frontend && npx tsc --noEmit
# (brak outputu = sukces)
```

Manualne ścieżki weryfikacji:

**Tab Tekst:**
- Pusty textarea → błąd "Wpisz treść artykułu." ✅
- Wypełniony → progress bar pojawia się (5% → ~85%), po zakończeniu skacze do 100%, baner "Tekst dodany do korpusu" przez 3s ✅

**Tab Link:**
- Pusty URL → błąd "Podaj adres URL." ✅
- Nieprawidłowy HTTP → baner błędu z `detail` z API ✅
- Poprawny URL → progress bar, baner "Artykuł pobrany i dodany" ✅

**Tab Plik:**
- Bez pliku → przycisk zablokowany ✅
- Za duży plik (>50 MB) → błąd z rozmiarem ✅
- Zły format → błąd "Obsługiwane formaty: PDF, DOCX, TXT" ✅
- Drag & drop → akceptacja pliku, tytuł auto-uzupełniony ✅
- Prześlij → progress bar, baner "Plik zaindeksowany" ✅

**Tab Drive:**
- Pusty folder_id → błąd "Podaj ID folderu Google Drive." ✅
- Nieprawidłowy folder_id → baner błędu z `detail` z API (502 gdy Drive auth failed) ✅
- Poprawny folder_id → progress bar, baner "Zaindeksowano N plik(ów) · M fragmentów" ✅

**Zmiana zakładki:**
- `successMsg` i `error` czyszczone przy zmianie zakładki ✅
- Progress bar znika po zmianie zakładki (progress resetuje do 0 gdy !loading && !justSucceeded) ✅
