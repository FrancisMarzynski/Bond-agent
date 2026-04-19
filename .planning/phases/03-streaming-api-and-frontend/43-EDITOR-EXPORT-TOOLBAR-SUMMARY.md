# 43 — Pasek narzędziowy eksportu edytora

## Co zostało zmienione

`frontend/src/components/EditorPane.tsx` otrzymał pasek narzędziowy z przyciskami **„Kopiuj MD"** i **„Pobierz .md"**, które pojawiają się nad edytorem markdown po zakończeniu strumieniowania i gdy draft jest niepusty.

---

## Problem

`EditorPane.tsx` nie miał żadnych kontrolek eksportu ani kopiowania.  
Po wygenerowaniu draftu użytkownik musiał ręcznie zaznaczyć cały tekst i skopiować go — uciążliwe i podatne na błędy przy artykułach 1000–2000 słów.  
Nie istniała też żadna możliwość zapisania draftu jako pliku lokalnego bez opuszczania aplikacji.

---

## Zmiany

### `frontend/src/components/EditorPane.tsx`

| Aspekt | Przed | Po |
|---|---|---|
| Pasek eksportu | Brak | Renderowany gdy `draft && !isStreaming` |
| Kopiowanie do schowka | Niedostępne | `navigator.clipboard.writeText(draft)` |
| Pobieranie pliku | Niedostępne | `Blob` → `URL.createObjectURL` → `<a download="draft.md">` |
| Informacja zwrotna przycisku kopiowania | Brak | Etykieta zmienia się na „Skopiowano!" na 2 s, następnie reset |

**Warunek widoczności paska:**
```tsx
{draft && !isStreaming && (
  <div className="flex items-center gap-2 px-3 py-2 border-b bg-background shrink-0">
    <Button variant="outline" size="sm" onClick={handleCopyMd}>
      {copyLabel}
    </Button>
    <Button variant="outline" size="sm" onClick={handleDownloadMd}>
      Pobierz .md
    </Button>
  </div>
)}
```

**Handler kopiowania:**
```ts
function handleCopyMd() {
  navigator.clipboard.writeText(draft).then(() => {
    setCopyLabel("Skopiowano!");
    setTimeout(() => setCopyLabel("Kopiuj MD"), 2000);
  });
}
```

**Handler pobierania:**
```ts
function handleDownloadMd() {
  const blob = new Blob([draft], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "draft.md";
  a.click();
  URL.revokeObjectURL(url);
}
```

---

## Decyzje projektowe

- Pasek jest ukryty podczas strumieniowania — przyciski mają sens dopiero gdy pełny draft jest dostępny.
- Pasek jest ukryty gdy `draft` jest pusty — unika wyświetlania przycisków na ekranie startowym.
- Stan `copyLabel` zapewnia przejściową informację „Skopiowano!" bez potrzeby dodawania biblioteki toast.
- Nazwa pobieranego pliku jest stała (`draft.md`); dostosowanie jej do tytułu artykułu odłożono na później.
- „Kopiuj HTML" (konwersja markdown → HTML) jest wymienione jako opcjonalne w IMPROVEMENTS.md i odłożono — wymagałoby dodania zależności `marked` lub `remark`.

---

## Kryteria akceptacji

- [x] Przycisk „Kopiuj MD" widoczny nad edytorem gdy `draft` jest niepusty i nie trwa strumieniowanie
- [x] Przycisk „Pobierz .md" widoczny nad edytorem gdy `draft` jest niepusty i nie trwa strumieniowanie
- [x] `navigator.clipboard.writeText(draft)` zaimplementowane dla kopiowania do schowka
- [x] Blob + `<a download>` zaimplementowane dla pobierania pliku
- [ ] „Kopiuj HTML" — odłożono (wymaga zależności markdown → HTML)

---

## Zmodyfikowane pliki

- `frontend/src/components/EditorPane.tsx`
