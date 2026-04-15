# 33-LOGGING-STANDARDIZATION Podsumowanie: Standaryzacja logowania (Logging vs Print)

**Data ukończenia:** 2026-04-15  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 33 — Standaryzacja logowania  
**Status:** ✅ Zakończone

---

## Cel

Zastąpienie wszystkich `print()` w kodzie bibliotecznym i węzłach grafowych wywołaniami modułu `logging`. Dodanie centralnej konfiguracji logowania z timestampami i poziomami, widocznymi w logach kontenera Docker.

---

## Architektura

```
bond/api/main.py
    └─ logging.basicConfig(
           format="%(asctime)s %(levelname)s %(name)s: %(message)s",
           stream=sys.stdout,   ← przechwytywane przez Docker
       )

Każdy moduł:
    log = logging.getLogger(__name__)   ← hierarchia: bond.graph.nodes.writer, itp.
    log.info(...)    ← INFO dla potwierdzeń (metadane zapisane, pliki znalezione)
    log.warning(...) ← WARNING dla pomijanych zasobów i nieudanych walidacji
```

Konfiguracja w `main.py` działa jako root handler — obejmuje wszystkie loggery `bond.*` bez duplikacji konfiguracji w każdym module.

---

## Zmodyfikowane pliki

### `bond/api/main.py`

Dodano centralną konfigurację logowania przed inicjalizacją aplikacji FastAPI:

```python
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
```

`stream=sys.stdout` — Docker domyślnie buforuje stderr; stdout jest line-buffered i od razu widoczny w `docker logs`.

---

### `bond/graph/nodes/writer.py`

Dodano `import logging` i `log = logging.getLogger(__name__)`. Zamieniono 2 wywołania `print()`:

```python
# Przed:
print(f"Writer auto-retry {attempt + 1}/{max_attempts - 1}: failed constraints: {failed}")
print(f"WARNING: Draft failed validation after {max_attempts} attempts. Failed: {failed_constraints}")

# Po:
log.warning("Writer auto-retry %d/%d: failed constraints: %s", attempt + 1, max_attempts - 1, failed)
log.warning("Draft failed validation after %d attempts. Failed: %s", max_attempts, failed_constraints)
```

---

### `bond/graph/nodes/save_metadata.py`

Dodano `import logging` i `log = logging.getLogger(__name__)`. Zamieniono 1 wywołanie `print()`:

```python
# Przed:
print(f"Metadane zapisane: topic='{topic}', thread_id={thread_id}")

# Po:
log.info("Metadane zapisane: topic='%s', thread_id=%s", topic, thread_id)
```

Poziom `INFO` — potwierdzenie poprawnego działania, nie ostrzeżenie.

---

### `bond/corpus/sources/file_source.py`

Dodano `import logging` i `log = logging.getLogger(__name__)`. Zamieniono 5 wywołań `print()`. Zaktualizowano też docstring funkcji `extract_text()`:

```python
# Przed:
print(f"WARN: PDF parse failed: {e} — skipping")
print(f"WARN: DOCX parse failed: {e} — skipping")
print(f"WARN: {filename} exceeds 20MB limit — skipping")
print(f"WARN: Unsupported file type .{ext} in {filename} — skipping")
print(f"WARN: TXT decode failed for {filename}: {e} — skipping")

# Po:
log.warning("PDF parse failed: %s — skipping", e)
log.warning("DOCX parse failed: %s — skipping", e)
log.warning("%s exceeds 20MB limit — skipping", filename)
log.warning("Unsupported file type .%s in %s — skipping", ext, filename)
log.warning("TXT decode failed for %s: %s — skipping", filename, e)
```

---

### `bond/corpus/sources/drive_source.py`

Dodano `import logging` i `log = logging.getLogger(__name__)` (przed innymi importami). Zamieniono 3 wywołania `print()`:

```python
# Przed:
print(f"WARN: Download failed for file {file_id}: {e} — skipping")
print(f"WARN: {warning_msg}")
print(f"INFO: Found {len(files)} supported files in Drive folder {folder_id}")

# Po:
log.warning("Download failed for file %s: %s — skipping", file_id, e)
log.warning("%s", warning_msg)
log.info("Found %d supported files in Drive folder %s", len(files), folder_id)
```

---

### `bond/corpus/sources/url_source.py`

Dodano `import logging` i `log = logging.getLogger(__name__)`. Zamieniono 7 wywołań `print()`:

```python
# Przed:
print(f"WARN: Found {len(urls)} posts at {url}; limiting to {max_posts} (MAX_BLOG_POSTS)")
print(f"INFO: Scraping {len(urls)} posts from {url}")
print(f"WARN: Could not fetch {post_url} — skipping")
print(f"WARN: No article content found at {post_url} — skipping")
print(f"WARN: Empty text extracted from {post_url} — skipping")
print(f"WARN: {post_url} failed ({type(e).__name__}: {e}) — skipping")
print(f"WARN: No articles extracted from {url}")

# Po:
log.warning("Found %d posts at %s; limiting to %d (MAX_BLOG_POSTS)", len(urls), url, max_posts)
log.info("Scraping %d posts from %s", len(urls), url)
log.warning("Could not fetch %s — skipping", post_url)
log.warning("No article content found at %s — skipping", post_url)
log.warning("Empty text extracted from %s — skipping", post_url)
log.warning("%s failed (%s: %s) — skipping", post_url, type(e).__name__, e)
log.warning("No articles extracted from %s", url)
```

---

### `bond/corpus/smoke_test.py`

Dodano `import logging` i `log = logging.getLogger(__name__)`. Zamieniono 1 wywołanie `print()`:

```python
# Przed:
print("WARN: Corpus is empty — smoke test returned no results")

# Po:
log.warning("Corpus is empty — smoke test returned no results")
```

---

## Pliki niezmienione

### `bond/harness.py`

`harness.py` to lokalny CLI do testowania pipeline'u — nie jest wdrażany w Docker. Jego `print()` jest celowym outputem UI dla developera. Zamiana na `logging` ukryłaby ten output przed interaktywnym użyciem bez dodatkowej konfiguracji handlera.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Konfiguracja modułu `logging` w `writer_node` | ✅ `import logging` + `log = logging.getLogger(__name__)` dodane do `writer.py` |
| Zamiana wszystkich `print()` na `log.warning()` lub `log.info()` | ✅ 16 wywołań `print()` w 6 modułach bibliotecznych zastąpionych |
| Dodanie timestampów i poziomów logowania do outputu kontenera | ✅ `logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: ...")` w `main.py` |

---

## Uwagi implementacyjne

**Dlaczego `%`-formatowanie zamiast f-stringów w `log.*()` ?**  
Python's logging wykonuje interpolację leniwie — tylko gdy wiadomość faktycznie zostanie wyemitowana. F-string jest obliczany zawsze, nawet gdy poziom logowania jest wyłączony. Przy intensywnym logowaniu w pętlach (np. iteracja po URL-ach) `%`-formatowanie jest tańsze.

**Dlaczego `stream=sys.stdout` zamiast domyślnego `stderr`?**  
Uvicorn loguje własne komunikaty na stdout. Spójność źródła sprawia, że `docker logs` pokazuje wszystko w jednym strumieniu i zachowuje chronologię. Stderr w Docker jest dostępne, ale logi aplikacji i frameworka powinny być razem.

**Dlaczego centralna konfiguracja w `main.py`?**  
`main.py` jest entry pointem kontenera (`uvicorn bond.api.main:app`). Konfiguracja w jednym miejscu obejmuje wszystkie loggery `bond.*` przez hierarchię Pythonowego modułu `logging`. Alternatywna konfiguracja per-moduł prowadziłaby do duplikacji handlerów.

**Poziomy logowania — dobór**  
- `log.info()` — zdarzenia potwierdzające poprawne działanie (metadane zapisane, pliki znalezione)  
- `log.warning()` — zdarzenia wymagające uwagi, ale obsługiwane (pominięcie pliku, nieudana walidacja draftu, retry writera)

Brak `log.error()` lub `log.critical()` — te poziomy są zarezerwowane dla nieobsługiwanych wyjątków i awarii krytycznych, których w tym zestawie zmian nie było.
