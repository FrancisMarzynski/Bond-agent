# 18-TWO-PASS-RETRIEVAL Podsumowanie: Priorytetyzacja własnego stylu w retrievalu

**Data ukończenia:** 2026-03-24
**Faza:** 03 — Streaming API i Frontend
**Plan:** 18 — Two-pass Retrieval
**Status:** ✅ Zakończone

---

## Cel

Priorytetyzacja własnego stylu autora (`own_text`) nad blogami zewnętrznymi (`external_blogger`)
w logice retrievalu Shadow Mode (Phase 1 Success Criteria 5).

---

## Architektura

```
shadow_analyze_node
    │
    └─► _retrieve_corpus_fragments(query, n)
            │
            └─► two_pass_retrieve(query, n)   ← bond/corpus/retriever.py
                    │
                    ├─ Pass 1: ChromaDB query (source_type='own')
                    │       ┌── 0 wyników → Pass 2 (fallback)
                    │       ├── 1..n-1 wyników → fill z external + rerank
                    │       └── n wyników → zwróć own_text bez external
                    │
                    ├─ Pass 2 (fallback): ChromaDB query (source_type='external')
                    │
                    └─► rerank(fragments)
                            │
                            own_text zawsze przed external_blogger
                            (stabilny sort, kolejność wewnątrz grupy zachowana)
```

---

## Zmienione pliki

### Nowy plik: `bond/corpus/retriever.py`

Dedykowany moduł retrieval — punkt jednej prawdy dla logiki dwuprzebiegowej.

**Eksportowane funkcje:**

#### `two_pass_retrieve(query, n=None) → list[dict]`

| Scenariusz | Zachowanie |
|---|---|
| 0 own_text w korpusie | Zwraca `n` external_blogger (czysty fallback) |
| 1..n-1 own_text | Uzupełnia brakujące miejsca z external, wywołuje `rerank` |
| ≥ n own_text | Zwraca tylko `n` own_text (bez external) |

#### `rerank(fragments) → list[dict]`

Stabilny re-ranker: all `source_type='own'` przed `source_type!='own'`.
Kolejność wewnątrz każdej grupy (relevance score) jest zachowana.

#### `_query_collection(query, n, source_type=None) → list[dict]`

Niskopoziomowy helper ChromaDB. Zwraca dicts z kluczami `text`, `score`
i polami metadanych (`source_type`, `article_title`, `source_url`, …).

---

### Zmodyfikowany: `bond/graph/nodes/shadow_analyze.py`

**Przed:**
- Wbudowana logika two-pass bezpośrednio w węźle.
- Próg `_MIN_OWN_FRAGMENTS = 3` — jeśli < 3 own, fallback do **wszystkich typów** jednocześnie.
- Brak gwarancji kolejności przy mieszanych wynikach.

**Po:**
- `_retrieve_corpus_fragments` deleguje do `bond.corpus.retriever.two_pass_retrieve`.
- Próg zmieniony na 0 (fallback wyłącznie gdy **brak** own_text).
- Re-ranker gwarantuje own_text zawsze na początku promptu.
- Usunięto import `get_or_create_corpus_collection` (zarządzany przez retriever).

---

### Zmodyfikowany: `bond/corpus/smoke_test.py`

**Przed:**
- Własna implementacja two-pass z osobnymi funkcjami `_query`.
- Sort by score descending — mógł przeplatać own_text z external_blogger.

**Po:**
- Deleguje do `two_pass_retrieve` — smoke test i produkcja używają tej samej ścieżki.
- Kolejność w wyniku odzwierciedla dokładnie to, co trafia do promptu LLM.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Retrieval próbuje najpierw 5 fragmentów z `own_text` | ✅ Pass 1 w `two_pass_retrieve` odpytuje ChromaDB z `where={"source_type": "own"}` |
| Fallback do `external_blogger` gdy brak own_text | ✅ Pass 2 uruchamiany wyłącznie gdy `len(own_fragments) == 0` |
| Re-ranker zapewnia own_text zawsze pierwszy w prompcie | ✅ `rerank()` grupuje `source_type=='own'` przed pozostałymi, stabilny sort |
| Własna ścieżka kodu (nie inline w węźle) | ✅ `bond/corpus/retriever.py` — niezależny moduł |
| Smoke test weryfikuje tę samą ścieżkę co produkcja | ✅ `smoke_test.py` importuje `two_pass_retrieve` wprost |

---

## Szczegóły implementacji: decyzje projektowe

### Dlaczego próg zmieniony z 3 na 0?

Poprzedni próg `_MIN_OWN_FRAGMENTS = 3` oznaczał: "wróć do mieszanego zbioru gdy masz < 3 own_text".
To mogło powodować, że fragmenty external_blogger pojawiały się przed own_text w prompcie
(sort by score ignorował typ źródła).

Nowy próg 0 + re-ranker daje mocniejszą gwarancję: nawet 1 fragment own_text zawsze
trafia do promptu jako pierwszy.

### Dlaczego fill zamiast czystego albo-albo?

Gdy korpus zawiera 2 own_text i brak dalszych, wypełnienie 3 slotami external zapewnia
LLM wystarczający kontekst stylistyczny — przy zachowaniu priorytetu own_text.

### Dlaczego osobny moduł?

`shadow_analyze.py`, `smoke_test.py` i potencjalnie przyszłe węzły (np. writer z RAG)
wszystkie potrzebują tej samej logiki. Centralizacja w `bond/corpus/retriever.py` eliminuje
powielanie i zapewnia spójność.

---

## Weryfikacja

```bash
uv run python -c "
from bond.corpus.retriever import two_pass_retrieve, rerank; print('retriever OK')
from bond.graph.nodes.shadow_analyze import shadow_analyze_node; print('shadow_analyze OK')
from bond.corpus.smoke_test import run_smoke_test; print('smoke_test OK')
"
# → retriever OK
# → shadow_analyze OK
# → smoke_test OK
```

Wszystkie trzy moduły importują się bez błędów. Logika two-pass i re-rankera
zweryfikowana przez inspekcję kodu.
