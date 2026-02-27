"""3-layer context builder for Bond LangGraph nodes.

Layers:
  1. Static      — brand/domain info (Pradma); constant across all runs
  2. Dynamic     — run-specific context supplied by user at pipeline start
  3. Environmental — current date, available tools

Source of truth: .planning/COMMUNICATION_STYLE.md
"""

from __future__ import annotations

from datetime import date

# ---------------------------------------------------------------------------
# Static layer — Pradma brand context
# ---------------------------------------------------------------------------

BRAND_CONTEXT = """Marka: Pradma
Branża: Inżynieria + IT — projektowanie instalacji elektrycznych w technologii BIM
Lokalizacja: Polska (Olsztyn, Gdynia)
Grupa docelowa: Architekci, firmy budowlane, deweloperzy obiektów komercyjnych / \
przemysłowych / użyteczności publicznej (szpitale, uczelnie, stadiony)
Typowe tematy bloga: BIM w projektowaniu elektrycznym, VR/AR w szkoleniach \
inżynierskich, case studies realizacji, technologie XR w przemyśle
Styl treści: Merytoryczny, oparty na danych i własnych case studies, techniczny \
ale zrozumiały dla menedżerów projektów. Język polski.
Unikamy: Pustych obietnic, clickbaitu, określeń „lider rynku" / „najlepszy \
w branży" bez poparcia danymi, generycznych zwrotów marketingowych."""

# ---------------------------------------------------------------------------
# Context block builder
# ---------------------------------------------------------------------------

def build_context_block(dynamic: str | None = None) -> str:
    """
    Assemble the full 3-layer context block for injection into LLM prompts.

    Args:
        dynamic: Run-specific context provided by user (e.g. 'Opisujemy symulator VR
                 dla studentów elektryki z Politechniki Warszawskiej').
                 Pass None for a generic brand article.

    Returns:
        Formatted Markdown context block ready for prompt injection.
    """
    dynamic_section = dynamic.strip() if dynamic else "Brak — artykuł ogólny w tematyce marki."
    today = date.today().isoformat()

    return f"""## KONTEKST MARKI I SESJI

### Warstwa Statyczna (Marka)
{BRAND_CONTEXT}

### Warstwa Dynamiczna (Kontekst Wpisu)
{dynamic_section}

### Warstwa Środowiskowa
Data: {today}
Dostępne narzędzia: Exa (web search), RAG corpus (wzorce stylistyczne)"""
