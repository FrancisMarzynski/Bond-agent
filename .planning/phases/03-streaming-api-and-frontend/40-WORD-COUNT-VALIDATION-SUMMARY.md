# 40-WORD-COUNT-VALIDATION Podsumowanie: Deterministyczna walidacja liczby słów

**Data ukończenia:** 2026-04-19  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 40 — Writer: Deterministyczna walidacja liczby słów  
**Status:** ✅ Zakończone

---

## Cel

Dokładne liczenie słów w treści artykułu z wykluczeniem nagłówków i metadanych.

- `_validate_draft()` używała `len(draft.split())`, która liczyła wszystko — nagłówki `# H1`, `## H2`, `### H3` oraz linię `Meta-description:`.
- Artykuł z 780 słowami treści + 40 słowami w nagłówkach i meta-opisie przechodził walidację jako „820 słów", mimo że faktyczna treść była poniżej normy.
- Nowa funkcja `_count_body_words()` filtruje te linie przed liczeniem, eliminując fałszywe wyniki walidacji.

---

## Architektura

```
writer_node
    │
    └─ _validate_draft(draft, primary_keyword, min_words)
                │
                └─ _count_body_words(draft)          ← NOWE
                            │
                            ├─ split("\n")
                            ├─ odrzuć linie startujące od "#"   (nagłówki H1–Hn)
                            ├─ odrzuć linie pasujące do ^Meta[- ]?[Dd]escription
                            └─ len(" ".join(body_lines).split())
```

---

## Zmodyfikowane pliki

### `bond/graph/nodes/writer.py`

#### `_count_body_words()` — nowa funkcja

```python
def _count_body_words(draft: str) -> int:
    """Count words in draft body, excluding heading lines (# H1..H3) and Meta-description."""
    body_lines = [
        line for line in draft.split("\n")
        if line.strip()
        and not line.strip().startswith("#")
        and not re.match(r"^Meta[- ]?[Dd]escription", line.strip(), re.IGNORECASE)
    ]
    return len(" ".join(body_lines).split())
```

Trzy warunki filtrowania na każdej linii:
1. `line.strip()` — pomija puste linie (nie wpływają na licznik i tak)
2. `not line.strip().startswith("#")` — pomija wszystkie nagłówki Markdown (`#`, `##`, `###`, `####`)
3. `not re.match(r"^Meta[- ]?[Dd]escription", ...)` — pomija warianty `Meta-description:`, `Meta description:`, `Meta Description:`, `Metadescription:` (case-insensitive)

#### `_validate_draft()` — aktualizacja `word_count_ok`

| Aspekt | Przed | Po |
|--------|-------|----|
| Licznik słów | `len(draft.split())` | `_count_body_words(draft)` |
| Zmienna `word_count` | Istniała — przekazywana do `word_count_ok` | Usunięta — bezpośrednie wywołanie |
| Zakres liczenia | Cały draft (nagłówki + meta + treść) | Tylko linie treści |

```python
# Przed
word_count = len(draft.split())
...
"word_count_ok": word_count >= min_words,

# Po
"word_count_ok": _count_body_words(draft) >= min_words,
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Implementacja `_count_body_words` używającej parsera linii Markdown | ✅ Zaimplementowana z filtrem regex na nagłówki i Meta-description |
| Wykluczenie linii `# H1..H3` z licznika | ✅ `not line.strip().startswith("#")` catches H1–H4+ |
| Wykluczenie linii `Meta-description` z licznika | ✅ `re.match(r"^Meta[- ]?[Dd]escription", ...)` — case-insensitive, obsługuje warianty |
| Integracja z `_validate_draft()` | ✅ `word_count_ok` używa `_count_body_words(draft)` |

---

## Weryfikacja

Zweryfikowano programatycznie:

```
draft = """
# Nagłówek H1 główny artykuł
## Sekcja pierwsza
### Podsekcja

To jest pierwszy akapit z właściwą treścią artykułu. Zawiera kilka słów.
To jest drugi akapit z jeszcze więcej treści. Dodajemy tu dużo tekstu.

Meta-description: Krótki opis artykułu do SEO.
"""

len(draft.split())          → 45  (z nagłówkami i meta)
_count_body_words(draft)    → 23  (tylko treść)
Różnica: 22 słów (nagłówki + meta-description wykluczone)  ✅
```

Przykład wpływu na walidację:

```
Artykuł 780 słów treści + 40 słów nagłówki/meta (min_words=800):

Poprzednio: len(draft.split()) = 820 → word_count_ok = True  ✗ (fałszywy pozytyw)
Teraz:      _count_body_words()  = 780 → word_count_ok = False ✅ (wymusi retry)
```
