# Author Quality Evaluation

| Case | Status | draft_validated | attempts | first_passed | final_failures |
|------|--------|-----------------|----------|--------------|----------------|
| `labeled-brief-e2e-shape` | `pass_with_warnings` | `False` | `3` | `False` | `word_count_ok `|
| `plain-topic-only` | `pass_with_warnings` | `False` | `3` | `False` | `keyword_in_first_para, word_count_ok `|
| `explicit-keywords-api-fields` | `pass_with_warnings` | `False` | `3` | `False` | `word_count_ok, no_forbidden_words `|
| `style-heavy-brief` | `pass_with_warnings` | `False` | `3` | `False` | `keyword_in_first_para, meta_desc_length_ok `|

## labeled-brief-e2e-shape

- Status: `pass_with_warnings`
- Thread ID: `7283ff5e-d80e-48dd-a42f-c06ea508a467`
- Czas: `112.21s`
- checkpoint_2 reached: `True`
- draft_validated: `False`
- attempt_count: `3`
- first_attempt_passed: `False`
- normalized_topic: `AI w marketingu B2B dla firm przemysłowych`
- normalized_keywords: `AI w marketingu B2B, lead generation, automatyzacja marketingu`
- normalized_context_dynamic: `Ton ekspercki.
Bez list wypunktowanych.
Dodaj 2 przykłady z polskiego rynku.`

### First-pass failures

- `keyword_in_first_para`
- `meta_desc_length_ok`
- `word_count_ok`
- `no_forbidden_words`

### Final validation failures

- Treść artykułu ma 775 słów; wymagane minimum to 800.

- Draft artifact: `.planning/artifacts/author-quality-20260429-123457/drafts/labeled-brief-e2e-shape.md`

## plain-topic-only

- Status: `pass_with_warnings`
- Thread ID: `6e15334a-e4d3-4093-887d-a729aae7e386`
- Czas: `93.13s`
- checkpoint_2 reached: `True`
- draft_validated: `False`
- attempt_count: `3`
- first_attempt_passed: `False`
- normalized_topic: `Jak cyfrowe bliźniaki wspierają utrzymanie ruchu w zakładach przemysłowych?`
- normalized_keywords: `brak`
- normalized_context_dynamic: `brak`

### First-pass failures

- `keyword_in_first_para`
- `meta_desc_length_ok`
- `word_count_ok`
- `no_forbidden_words`

### Final validation failures

- Pierwszy akapit musi zawierać główne słowo kluczowe "Jak cyfrowe bliźniaki wspierają utrzymanie ruchu w zakładach przemysłowych?".
- Treść artykułu ma 648 słów; wymagane minimum to 800.

- Draft artifact: `.planning/artifacts/author-quality-20260429-123457/drafts/plain-topic-only.md`

## explicit-keywords-api-fields

- Status: `pass_with_warnings`
- Thread ID: `edc354ae-5b49-4783-a416-de835fd0f9d6`
- Czas: `61.87s`
- checkpoint_2 reached: `True`
- draft_validated: `False`
- attempt_count: `3`
- first_attempt_passed: `False`
- normalized_topic: `Strategia content marketingowa dla firm BIM pozyskujących leady B2B`
- normalized_keywords: `content marketing BIM, lead generation B2B, BIM marketing`
- normalized_context_dynamic: `Pisz konkretnie, po polsku, z naciskiem na proces wdrożenia i mierzalne efekty.`

### First-pass failures

- `keyword_in_first_para`
- `meta_desc_length_ok`
- `word_count_ok`

### Final validation failures

- Treść artykułu ma 622 słów; wymagane minimum to 800.
- Usuń niedozwolone rdzenie słów: nowoczesn.

- Draft artifact: `.planning/artifacts/author-quality-20260429-123457/drafts/explicit-keywords-api-fields.md`

## style-heavy-brief

- Status: `pass_with_warnings`
- Thread ID: `5f399bd1-da70-482a-bc31-a8e905ca81fc`
- Czas: `104.14s`
- checkpoint_2 reached: `True`
- draft_validated: `False`
- attempt_count: `3`
- first_attempt_passed: `False`
- normalized_topic: `Jak firmy projektowe wdrażają AI bez utraty kontroli nad jakością`
- normalized_keywords: `AI w firmie projektowej, governance AI`
- normalized_context_dynamic: `Ton krytyczny, bez obietnic sprzedażowych.
Pokaż ryzyka, proces wdrożenia i checklistę decyzyjną.`

### First-pass failures

- `keyword_in_first_para`
- `meta_desc_length_ok`
- `word_count_ok`

### Final validation failures

- Pierwszy akapit musi zawierać główne słowo kluczowe "AI w firmie projektowej".
- Meta-description musi mieć 150-160 znaków; obecnie ma 148.

- Draft artifact: `.planning/artifacts/author-quality-20260429-123457/drafts/style-heavy-brief.md`
