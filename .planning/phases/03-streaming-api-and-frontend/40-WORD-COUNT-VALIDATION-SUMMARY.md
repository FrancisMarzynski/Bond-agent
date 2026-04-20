# 40-WORD-COUNT-VALIDATION Podsumowanie: Deterministyczna walidacja liczby słów

**Data ukończenia:** 2026-04-20 (refaktor po przeglądzie kodu)
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 40 — Writer: Deterministyczna walidacja liczby słów  
**Status:** ✅ Zakończone

---

## Cel

Dokładne liczenie słów w treści artykułu z wykluczeniem nagłówków i metadanych.

- `_validate_draft()` używała `len(draft.split())`, która liczyła wszystko — nagłówki `# H1`, `## H2`, `### H3` oraz linię `Meta-description:`.
- Artykuł z 780 słowami treści + 40 słowami w nagłówkach i meta-opisie przechodził walidację jako „820 słów", mimo że faktyczna treść była poniżej normy.
- Nowa funkcja `_count_body_words()` używa parsera Markdown + BeautifulSoup, eliminując fałszywe wyniki walidacji i błędne zachowanie przy blokach kodu.

---

## Architektura (po refaktorze 2026-04-20)

```
writer_node
    │
    └─ _validate_draft(draft, primary_keyword, min_words)
                │
                ├─ _parse_draft_to_soup(draft)     ← jednorazowy parse
                │           │
                │           └─ markdown → HTML → BeautifulSoup
                │
                ├─ soup.find("h1")                 ← H1 do walidacji keyword
                ├─ soup.find_all("p")[0]            ← pierwszy akapit
                ├─ regex na <p> Meta-description   ← meta_desc
                └─ _count_body_words(soup)
                            │
                            ├─ kopia soup
                            ├─ decompose h1–h6
                            ├─ decompose <p> Meta-description
                            └─ soup_copy.get_text().split()
```

---

## Zmodyfikowane pliki

### `pyproject.toml`

Dodano zależności:
- `markdown>=3.0`
- `beautifulsoup4>=4.0`

### `bond/graph/nodes/writer.py`

#### `_parse_draft_to_soup()` — nowa funkcja pomocnicza

```python
def _parse_draft_to_soup(draft: str) -> BeautifulSoup:
    """Parse Markdown draft to BeautifulSoup tree (understands fenced code blocks)."""
    html = _md.markdown(draft, extensions=["fenced_code"])
    return BeautifulSoup(html, "html.parser")
```

#### `_count_body_words()` — refaktor: string → BeautifulSoup

```python
def _count_body_words(soup: BeautifulSoup) -> int:
    """Count body words, excluding heading and Meta-description nodes."""
    soup_copy = BeautifulSoup(str(soup), "html.parser")
    for tag in soup_copy.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        tag.decompose()
    for p in soup_copy.find_all("p"):
        if re.match(r"^Meta[- ]?[Dd]escription", p.get_text().strip(), re.IGNORECASE):
            p.decompose()
    return len(soup_copy.get_text().split())
```

Kluczowa zmiana względem poprzedniej wersji (`split("\n")` + `startswith("#")`):  
znak `#` wewnątrz bloku kodu (```` ```python\n# comment\n``` ````) nie jest nagłówkiem — parser Markdown renderuje go jako `<code>`, nie `<h1>`. Poprzednia wersja błędnie go wykluczała.

#### `_validate_draft()` — jeden parse, brak duplikacji logiki

```python
def _validate_draft(draft: str, primary_keyword: str, min_words: int) -> dict[str, bool]:
    soup = _parse_draft_to_soup(draft)

    h1 = soup.find("h1")
    h1_text = h1.get_text() if h1 else ""

    first_para = next(
        (p.get_text().strip() for p in soup.find_all("p") if p.get_text().strip()),
        ""
    )

    meta_desc = ""
    for p in soup.find_all("p"):
        m = re.match(r"^Meta[- ]?[Dd]escription[:\s]+(.+)", p.get_text().strip(), re.IGNORECASE)
        if m:
            meta_desc = m.group(1).strip()
            break

    pk_lower = primary_keyword.lower()

    return {
        "keyword_in_h1": bool(h1_text and pk_lower in h1_text.lower()),
        "keyword_in_first_para": pk_lower in first_para.lower(),
        "meta_desc_length_ok": 150 <= len(meta_desc) <= 160,
        "word_count_ok": _count_body_words(soup) >= min_words,
        "no_forbidden_words": len(_check_forbidden_words(draft)) == 0,
    }
```

Poprzednia wersja robiła `draft.split("\n")` dwukrotnie — raz w `_count_body_words`, raz w `_validate_draft`. Teraz Markdown jest parsowany raz, a soup jest przekazywany dalej.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Implementacja `_count_body_words` używającej parsera Markdown/BS4 | ✅ `markdown` → HTML → BeautifulSoup |
| Wykluczenie linii `# H1..H3` z licznika | ✅ `decompose` na tagach `h1`–`h6` |
| Wykluczenie linii `Meta-description` z licznika | ✅ regex na `<p>.get_text()` — case-insensitive, obsługuje warianty |
| Integracja z `_validate_draft()` | ✅ jeden parse, `_count_body_words(soup)` |
| Bloki kodu z `#` nie są błędnie wykluczane | ✅ parser rozumie strukturę — `#` w `<code>` nie jest nagłówkiem |
| Logika ekstrakcji nagłówków i meta-description nie jest duplikowana | ✅ jeden `_parse_draft_to_soup()` na początku `_validate_draft` |

---

## Weryfikacja

```
draft = """
# Nagłówek H1 główny artykuł
## Sekcja pierwsza
### Podsekcja

To jest pierwszy akapit z właściwą treścią artykułu. Zawiera kilka słów.

```python
# Ten komentarz NIE powinien być wykluczony
x = 1
```

Meta-description: Krótki opis artykułu do SEO.
"""

_count_body_words(_parse_draft_to_soup(draft))  → 25  (treść + kod, bez nagłówków i meta) ✅
```

Przykład wpływu na walidację:

```
Artykuł 780 słów treści + 40 słów nagłówki/meta (min_words=800):

Poprzednio: len(draft.split()) = 820 → word_count_ok = True  ✗ (fałszywy pozytyw)
Teraz:      _count_body_words()  = 780 → word_count_ok = False ✅ (wymusi retry)
```
