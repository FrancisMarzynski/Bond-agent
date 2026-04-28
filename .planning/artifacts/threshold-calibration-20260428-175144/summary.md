# Threshold Calibration

Wygenerowano: 2026-04-28T15:51:51.987934+00:00

## Snapshot danych

| Miara | Wartość |
|------|---------|
| `articles.db` article_count | `12` |
| `articles.db` chunk_count | `12` |
| Chroma corpus chunk_count | `12` |
| SQLite metadata topics | `4` |
| Chroma duplicate topics | `3` |
| Extended local topic/title pool | `16` |

## Rekomendacje

- `low_corpus_threshold`: `10` -> `10` (`change_default=false`, confidence=umiarkowana)
- `duplicate_threshold`: `0.85` -> `0.85` (`change_default=false`, confidence=niska)

## Low Corpus

Zapytania użyte do oceny: topic-like=`5`, title-like=`12`.

| Articles | Family | Coverage | Overlap@5 | Median overlap | Top1 match | Mean top1 sim |
|----------|--------|----------|-----------|----------------|------------|---------------|
| `3` | `topic_like` | `0.6000` | `0.4667` | `0.3333` | `0.6000` | `0.4767` |
| `3` | `title_like` | `0.6000` | `0.4445` | `0.6667` | `0.2500` | `0.3881` |
| `4` | `topic_like` | `0.8000` | `0.4500` | `0.5000` | `0.6000` | `0.4767` |
| `4` | `title_like` | `0.8000` | `0.4583` | `0.5000` | `0.3333` | `0.4956` |
| `5` | `topic_like` | `1.0000` | `0.4800` | `0.6000` | `0.6000` | `0.5011` |
| `5` | `title_like` | `1.0000` | `0.4667` | `0.5000` | `0.5000` | `0.5067` |
| `6` | `topic_like` | `1.0000` | `0.5200` | `0.6000` | `0.6000` | `0.5011` |
| `6` | `title_like` | `1.0000` | `0.5667` | `0.6000` | `0.5833` | `0.5181` |
| `7` | `topic_like` | `1.0000` | `0.5200` | `0.6000` | `0.6000` | `0.5011` |
| `7` | `title_like` | `1.0000` | `0.6500` | `0.6000` | `0.6667` | `0.5430` |
| `8` | `topic_like` | `1.0000` | `0.6000` | `0.6000` | `0.6000` | `0.5074` |
| `8` | `title_like` | `1.0000` | `0.7000` | `0.7000` | `0.7500` | `0.5550` |
| `9` | `topic_like` | `1.0000` | `0.8000` | `0.8000` | `0.8000` | `0.5094` |
| `9` | `title_like` | `1.0000` | `0.7667` | `0.8000` | `0.7500` | `0.5550` |
| `10` | `topic_like` | `1.0000` | `0.8000` | `0.8000` | `0.8000` | `0.5094` |
| `10` | `title_like` | `1.0000` | `0.8667` | `1.0000` | `0.8333` | `0.5650` |
| `11` | `topic_like` | `1.0000` | `0.9200` | `1.0000` | `1.0000` | `0.5215` |
| `11` | `title_like` | `1.0000` | `0.9500` | `1.0000` | `0.9167` | `0.6011` |
| `12` | `topic_like` | `1.0000` | `1.0000` | `1.0000` | `1.0000` | `0.5215` |
| `12` | `title_like` | `1.0000` | `1.0000` | `1.0000` | `1.0000` | `0.6364` |

Wnioski:
- Lokalny korpus ma tylko 12 artykułów, czyli zaledwie o 2 więcej niż obecny próg 10.
- Zapytania topic-like osiągają stabilne pokrycie i zgodność top-1 dopiero przy około 9 artykułach.
- Obniżenie progu na podstawie obecnych danych byłoby zbyt agresywne; zostawiam domyślną wartość bez zmian.

## Duplicate Threshold

| Statystyka | Wartość |
|------------|---------|
| nearest-neighbor min | `0.3023` |
| nearest-neighbor median | `0.5591` |
| nearest-neighbor p90 | `0.8550` |
| nearest-neighbor max | `0.9244` |
| pairs >= 0.70 | `3` |
| pairs >= 0.75 | `2` |
| pairs >= 0.80 | `1` |
| pairs >= 0.85 | `1` |
| pairs >= 0.90 | `1` |

Najwyższe pary podobieństwa:
- `0.9244` — Testowy temat artykułu [metadata_sqlite] <> Test Article [corpus_title]
- `0.7856` — Test Article [corpus_title] <> test_article.txt [corpus_title]
- `0.7475` — Marketing Automation: Personalizacja to Nowy Standard [corpus_title] <> Budowanie Personal Brandingu w Świecie Zdominowanym przez Algorytmy [corpus_title]
- `0.6912` — Testowy temat artykułu [metadata_sqlite] <> test_article.txt [corpus_title]
- `0.6883` — Testowy temat artykułu [metadata_sqlite] <> Test topic dla weryfikacji zapisu metadanych [metadata_sqlite]
- `0.6270` — Test topic dla weryfikacji zapisu metadanych [metadata_sqlite] <> Test Article [corpus_title]
- `0.5649` — Podstawy copywritingu [corpus_title] <> Przyszłość AI w Copywritingu: Jak Modele Językowe Zmieniają Grę [corpus_title]
- `0.5533` — Jak pisać angażujące treści [corpus_title] <> Strategia Contentowa: Dlaczego Jakość Zawsze Wygra z Ilością [corpus_title]
- `0.5521` — Storytelling w marketingu [corpus_title] <> Strategia Contentowa: Dlaczego Jakość Zawsze Wygra z Ilością [corpus_title]
- `0.5456` — Storytelling w marketingu [corpus_title] <> Marketing Automation: Personalizacja to Nowy Standard [corpus_title]

Wnioski:
- Kolekcja duplicate w Chroma ma tylko 3 temat(y), więc realna próba produkcyjna jest za mała do przesuwania progu.
- W rozszerzonej lokalnej puli (16 tematów/tytułów) jest tylko 1 para(y) w paśmie 0.75-0.90 wokół bieżącego progu 0.85.
- Brak oznaczonych ręcznie duplikatów i brak gęstości punktów granicznych oznacza, że zmiana defaultu byłaby zgadywaniem.

## Ostrzeżenia

- SQLite metadata_log ma 4 temat(y), a kolekcja Chroma duplicate ma 3 embeddingów.
