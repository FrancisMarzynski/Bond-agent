"""
bond/schemas.py — Publiczny kontrakt wejścia/wyjścia agenta Bond.

Oddzielony od:
- bond/graph/state.py   → wewnętrzny stan grafu LangGraph (AuthorState)
- bond/models.py        → schematy REST API dla korpusu (ingest)

AgentInput  — co klient/UI/API przekazuje do pipeline'u Trybu Autora
AgentOutput — co agent zwraca po zakończeniu wszystkich węzłów
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    """
    Wejście do pipeline'u Trybu Autora.

    Mapowanie na AuthorState (bond/graph/state.py):
      topic   → state["topic"]
      tone    → przekazywany do writer_node jako instrukcja stylu
      sources → przekazywany do researcher_node jako wskazówki źródłowe
    """

    topic: Annotated[str, Field(
        min_length=3,
        max_length=300,
        description="Temat artykułu. Powinien być konkretny i zwięzły.",
        examples=["Jak zwiększyć ruch na blogu firmowym"],
    )]

    tone: Annotated[str, Field(
        default="profesjonalny",
        description=(
            "Ton i styl pisania. Możliwe wartości: "
            "'profesjonalny', 'ekspercki', 'przyjazny', 'edukacyjny', 'sprzedażowy'."
        ),
        examples=["profesjonalny", "przyjazny"],
    )]

    sources: Annotated[list[str], Field(
        default_factory=list,
        max_length=10,
        description=(
            "Opcjonalna lista URL-i lub fraz kluczowych do uwzględnienia przez węzeł "
            "researcher. Jeśli pusta, agent sam wybiera źródła poprzez Exa MCP."
        ),
        examples=[["https://example.com/artykul", "content marketing B2B"]],
    )]


class AgentOutput(BaseModel):
    """
    Wyjście pipeline'u Trybu Autora po zakończeniu wszystkich węzłów.

    Mapowanie z AuthorState (bond/graph/state.py):
      markdown_content → state["draft"]
      sources_list     → URL-e wyciągnięte z state["search_cache"]
      tokens_used      → agregacja usage_metadata ze wszystkich węzłów LLM
                         (domyślnie 0 — implementacja w osobnym zadaniu)
    """

    markdown_content: Annotated[str, Field(
        description=(
            "Gotowy artykuł w formacie Markdown, zawierający hierarchię H1/H2/H3, "
            "meta-description (150-160 znaków) i minimum 800 słów."
        ),
    )]

    sources_list: Annotated[list[str], Field(
        default_factory=list,
        description=(
            "Lista URL-i źródeł użytych podczas badań, wyciągnięta z search_cache. "
            "Kolejność: od najbardziej do najmniej relewantnych."
        ),
    )]

    tokens_used: Annotated[int, Field(
        default=0,
        ge=0,
        description=(
            "Łączna liczba tokenów zużytych przez wszystkie wywołania LLM "
            "w pipeline'ie (researcher + writer). Wartość 0 = brak danych."
        ),
    )]
