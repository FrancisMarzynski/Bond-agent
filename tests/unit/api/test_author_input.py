from bond.api.author_input import normalize_author_input


def test_normalize_author_input_parses_labeled_polish_brief():
    result = normalize_author_input(
        """Temat: Jak wdrożyć AI w marketingu B2B
Słowa kluczowe: AI w marketingu B2B, automatyzacja marketingu; lead generation
Wymagania: Ton ekspercki.
Bez list wypunktowanych.
Dodaj 2 przykłady z rynku polskiego."""
    )

    assert result["topic"] == "Jak wdrożyć AI w marketingu B2B"
    assert result["keywords"] == [
        "AI w marketingu B2B",
        "automatyzacja marketingu",
        "lead generation",
    ]
    assert result["context_dynamic"] == (
        "Ton ekspercki.\nBez list wypunktowanych.\nDodaj 2 przykłady z rynku polskiego."
    )


def test_normalize_author_input_prefers_explicit_request_fields():
    result = normalize_author_input(
        """Temat: BIM w projektowaniu instalacji
Słowa kluczowe: stary keyword
Wymagania: stary kontekst""",
        keywords=["Nowy keyword", "nowy keyword", "Lead gen; BIM"],
        context_dynamic="Nowy kontekst dla tego wpisu.",
    )

    assert result["topic"] == "BIM w projektowaniu instalacji"
    assert result["keywords"] == ["Nowy keyword", "Lead gen", "BIM"]
    assert result["context_dynamic"] == "Nowy kontekst dla tego wpisu."


def test_normalize_author_input_leaves_unlabeled_prompt_untouched():
    prompt = "Jak firmy przemysłowe mogą wykorzystać cyfrowe bliźniaki w utrzymaniu ruchu?"

    result = normalize_author_input(prompt)

    assert result == {
        "topic": prompt,
        "keywords": [],
        "context_dynamic": None,
        "raw_message": prompt,
    }


def test_normalize_author_input_handles_empty_keyword_line_without_garbage():
    result = normalize_author_input(
        """Temat: Strategia SEO dla firmy BIM
Słowa kluczowe:
Wymagania: Dodaj konkretny case study."""
    )

    assert result["topic"] == "Strategia SEO dla firmy BIM"
    assert result["keywords"] == []
    assert result["context_dynamic"] == "Dodaj konkretny case study."
