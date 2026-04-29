# Author Quality Evaluation

| Case | Status | draft_validated | attempts | first_passed | final_failures |
|------|--------|-----------------|----------|--------------|----------------|
| `labeled-brief-e2e-shape` | `pass_with_warnings` | `False` | `3` | `False` | `word_count_ok `|
| `plain-topic-only` | `pass_with_warnings` | `False` | `3` | `False` | `keyword_in_first_para, meta_desc_length_ok, word_count_ok `|
| `explicit-keywords-api-fields` | `pass_with_warnings` | `False` | `3` | `False` | `keyword_in_first_para, meta_desc_length_ok, word_count_ok, no_forbidden_words `|
| `style-heavy-brief` | `pass_with_warnings` | `False` | `3` | `False` | `meta_desc_length_ok, word_count_ok `|

## labeled-brief-e2e-shape

- Status: `pass_with_warnings`
- Thread ID: `9b413e4f-aeb1-479b-81ec-26cb6b1ea19f`
- Czas: `86.82s`
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

### Final validation failures

- Treść artykułu ma 465 słów; wymagane minimum to 800.

- Draft artifact: `.planning/artifacts/author-quality-20260429-113845/drafts/labeled-brief-e2e-shape.md`

## plain-topic-only

- Status: `pass_with_warnings`
- Thread ID: `33c60713-c959-42ba-ab55-f6ca546ff1e3`
- Czas: `130.23s`
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

### Final validation failures

- Pierwszy akapit musi zawierać główne słowo kluczowe "Jak cyfrowe bliźniaki wspierają utrzymanie ruchu w zakładach przemysłowych?".
- Meta-description musi mieć 150-160 znaków; obecnie ma 132.
- Treść artykułu ma 543 słów; wymagane minimum to 800.

- Draft artifact: `.planning/artifacts/author-quality-20260429-113845/drafts/plain-topic-only.md`

## explicit-keywords-api-fields

- Status: `pass_with_warnings`
- Thread ID: `071e4db9-1992-4042-9088-eca6eee0c7a2`
- Czas: `85.36s`
- checkpoint_2 reached: `True`
- draft_validated: `False`
- attempt_count: `3`
- first_attempt_passed: `False`
- normalized_topic: `Strategia content marketingowa dla firm BIM pozyskujących leady B2B`
- normalized_keywords: `content marketing BIM, lead generation B2B, BIM marketing`
- normalized_context_dynamic: `Pisz konkretnie, po polsku, z naciskiem na proces wdrożenia i mierzalne efekty.`

### First-pass failures

- `meta_desc_length_ok`
- `word_count_ok`

### Final validation failures

- Pierwszy akapit musi zawierać główne słowo kluczowe "content marketing BIM".
- Meta-description musi mieć 150-160 znaków; obecnie ma 138.
- Treść artykułu ma 631 słów; wymagane minimum to 800.
- Usuń niedozwolone rdzenie słów: nowoczesn.

- Draft artifact: `.planning/artifacts/author-quality-20260429-113845/drafts/explicit-keywords-api-fields.md`

## style-heavy-brief

- Status: `pass_with_warnings`
- Thread ID: `0f5cb302-aff9-446e-9f40-318d07741745`
- Czas: `96.41s`
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

- Meta-description musi mieć 150-160 znaków; obecnie ma 146.
- Treść artykułu ma 545 słów; wymagane minimum to 800.

- Draft artifact: `.planning/artifacts/author-quality-20260429-113845/drafts/style-heavy-brief.md`
