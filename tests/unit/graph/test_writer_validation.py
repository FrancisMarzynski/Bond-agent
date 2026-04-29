import importlib
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

fake_langchain_anthropic = types.ModuleType("langchain_anthropic")
fake_langchain_anthropic.ChatAnthropic = object
sys.modules.setdefault("langchain_anthropic", fake_langchain_anthropic)

fake_langchain_openai = types.ModuleType("langchain_openai")
fake_langchain_openai.ChatOpenAI = object
sys.modules.setdefault("langchain_openai", fake_langchain_openai)

fake_chroma = types.ModuleType("bond.store.chroma")
fake_chroma.get_corpus_collection = lambda: None
sys.modules.setdefault("bond.store.chroma", fake_chroma)

sys.modules.pop("markdown", None)
sys.modules.pop("bs4", None)
sys.modules["markdown"] = importlib.import_module("markdown")
sys.modules["bs4"] = importlib.import_module("bs4")

sys.modules.pop("bond.graph.nodes.writer", None)
writer = importlib.import_module("bond.graph.nodes.writer")


def test_validate_draft_ignores_meta_description_for_first_paragraph_keyword_check():
    draft = """Meta-description: To jest meta-description o długości dokładnie stu pięćdziesięciu pięciu znaków, więc walidacja długości powinna przejść bez dodatkowych poprawek teraz.

# Jak cyfrowe bliźniaki wspierają utrzymanie ruchu w zakładach przemysłowych?

Jak cyfrowe bliźniaki wspierają utrzymanie ruchu w zakładach przemysłowych to pytanie, na które odpowiadają dane z produkcji, serwisu i monitoringu maszyn.

Drugi akapit dodaje kontekst operacyjny, omawia planowanie przestojów, analizę awarii i rolę predykcyjnego utrzymania ruchu w praktyce zakładu."""

    report = writer._validate_draft(
        draft,
        "Jak cyfrowe bliźniaki wspierają utrzymanie ruchu w zakładach przemysłowych?",
        20,
    )

    assert report["checks"]["keyword_in_h1"] is True
    assert report["checks"]["keyword_in_first_para"] is True
    assert report["checks"]["meta_desc_length_ok"] is True


def test_validate_draft_normalizes_punctuation_when_matching_keyword():
    draft = """Meta-description: Ta meta-description również ma długość w bezpiecznym zakresie i nie musi powtarzać pytajnika z keywordu, by test był wiarygodny teraz.

# Jak firmy projektowe wdrażają AI bez utraty kontroli nad jakością

Jak firmy projektowe wdrażają AI bez utraty kontroli nad jakością zależy od governance, etapów wdrożenia i kontroli jakości danych wejściowych.

Kolejny akapit rozwija temat ryzyk, przeglądu procedur i kryteriów decyzyjnych, dzięki czemu walidacja długości treści także przechodzi bez problemu."""

    report = writer._validate_draft(
        draft,
        "Jak firmy projektowe wdrażają AI bez utraty kontroli nad jakością?",
        20,
    )

    assert report["checks"]["keyword_in_h1"] is True
    assert report["checks"]["keyword_in_first_para"] is True


def test_apply_validation_repairs_injects_question_keyword_into_first_paragraph():
    primary_keyword = (
        "Jak cyfrowe bliźniaki wspierają utrzymanie ruchu w zakładach przemysłowych?"
    )
    draft = """Meta-description: Cyfrowe bliźniaki pomagają ograniczać przestoje, koszty i awarie, a jednocześnie poprawiają przewidywalność utrzymania ruchu w produkcji przemysłowej.

# Jak cyfrowe bliźniaki wspierają utrzymanie ruchu w zakładach przemysłowych?

Cyfrowe bliźniaki pomagają zespołom utrzymania ruchu szybciej lokalizować źródła awarii i planować interwencje serwisowe.

Drugi akapit rozwija temat danych procesowych, harmonogramów postojów i wpływu wdrożenia na przewidywalność pracy zakładu."""

    validation = writer._validate_draft(draft, primary_keyword, 20)
    repaired = writer._apply_validation_repairs(
        draft,
        validation,
        primary_keyword=primary_keyword,
        min_words=20,
        research_data=None,
        allow_word_count_expansion=False,
    )
    report = writer._validate_draft(repaired, primary_keyword, 20)

    assert report["checks"]["keyword_in_first_para"] is True
    assert primary_keyword in repaired


def test_apply_validation_repairs_fixes_meta_length_and_forbidden_words():
    primary_keyword = "AI w firmie projektowej"
    draft = """Meta-description: AI wspiera projektowanie i porządkuje proces wdrożenia w firmie projektowej.

# AI w firmie projektowej

Wdrożenie sztucznej inteligencji w firmie projektowej wymaga jasnych zasad jakości, odpowiedzialności i kontroli danych.

Nowoczesne procedury pomagają uporządkować akceptację modeli, zakres odpowiedzialności i sposób raportowania wyników."""

    validation = writer._validate_draft(draft, primary_keyword, 20)
    repaired = writer._apply_validation_repairs(
        draft,
        validation,
        primary_keyword=primary_keyword,
        min_words=20,
        research_data=None,
        allow_word_count_expansion=False,
    )
    report = writer._validate_draft(repaired, primary_keyword, 20)

    assert report["checks"]["keyword_in_first_para"] is True
    assert report["checks"]["meta_desc_length_ok"] is True
    assert report["checks"]["no_forbidden_words"] is True


def test_apply_validation_repairs_expands_short_draft_with_research_data():
    primary_keyword = "content marketing BIM"
    draft = """Meta-description: Content marketing BIM wspiera lead generation B2B dzięki danym projektowym, lepszej segmentacji i skuteczniejszej pracy na realnych case studies.

# Content marketing BIM dla lead generation B2B

Content marketing BIM pomaga zespołom sprzedaży i marketingu lepiej porządkować dane o projektach, potrzebach klientów i przebiegu procesu zakupowego.

Drugi akapit pokazuje, że firmy wykorzystujące uporządkowane treści szybciej doprowadzają prospecta do rozmowy handlowej."""
    validation = writer._validate_draft(draft, primary_keyword, 80)
    repaired = writer._apply_validation_repairs(
        draft,
        validation,
        primary_keyword=primary_keyword,
        min_words=80,
        research_data={
            "fakty": [
                "Projektanci częściej wybierają dostawców, którzy dostarczają komplet danych BIM i opis procesu wdrożenia.",
                "Case studies skracają drogę od pierwszego kontaktu do rozmowy technicznej, bo redukują liczbę pytań o zakres wdrożenia.",
                "Treści oparte na danych procesowych lepiej wspierają kwalifikację leadów niż ogólne komunikaty sprzedażowe.",
            ],
            "statystyki": [
                "73% projektantów preferuje dane BIM dostarczane bezpośrednio przez producenta.",
                "51% wzrost leadów z platformy BIMobject pokazuje, że kanał cyfrowy realnie wpływa na popyt.",
                "25% wzrost konwersji w case study wynikał z lepszego powiązania treści z etapem wdrożenia.",
            ],
        },
        allow_word_count_expansion=True,
    )
    report = writer._validate_draft(repaired, primary_keyword, 80)

    assert report["checks"]["word_count_ok"] is True
