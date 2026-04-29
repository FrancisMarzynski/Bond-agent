import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

fake_markdown = types.ModuleType("markdown")
fake_markdown.markdown = lambda text: text
sys.modules.setdefault("markdown", fake_markdown)

fake_bs4 = types.ModuleType("bs4")
fake_bs4.BeautifulSoup = lambda html, parser: SimpleNamespace(
    get_text=lambda separator="": html
)
sys.modules.setdefault("bs4", fake_bs4)

fake_langchain_anthropic = types.ModuleType("langchain_anthropic")
fake_langchain_anthropic.ChatAnthropic = object
sys.modules.setdefault("langchain_anthropic", fake_langchain_anthropic)

fake_langchain_openai = types.ModuleType("langchain_openai")
fake_langchain_openai.ChatOpenAI = object
sys.modules.setdefault("langchain_openai", fake_langchain_openai)

fake_chroma = types.ModuleType("bond.store.chroma")
fake_chroma.get_corpus_collection = lambda: None
sys.modules.setdefault("bond.store.chroma", fake_chroma)

sys.modules.pop("bond.graph.nodes.writer", None)
writer = importlib.import_module("bond.graph.nodes.writer")


def _validation_report(
    *,
    passed: bool,
    primary_keyword: str = "AI marketing",
    failure_codes: list[str] | None = None,
    failures: list[dict] | None = None,
    body_word_count: int = 900,
    meta_description_length: int = 155,
) -> dict:
    failure_codes = failure_codes or []
    failures = failures or []
    return {
        "passed": passed,
        "checks": {
            "keyword_in_h1": "keyword_in_h1" not in failure_codes,
            "keyword_in_first_para": "keyword_in_first_para" not in failure_codes,
            "meta_desc_length_ok": "meta_desc_length_ok" not in failure_codes,
            "word_count_ok": "word_count_ok" not in failure_codes,
            "no_forbidden_words": "no_forbidden_words" not in failure_codes,
        },
        "failure_codes": failure_codes,
        "failures": failures,
        "primary_keyword": primary_keyword,
        "body_word_count": body_word_count,
        "min_words": 800,
        "meta_description_length": meta_description_length,
        "meta_description_min_length": 150,
        "meta_description_max_length": 160,
        "forbidden_stems": [],
        "attempt_count": 0,
        "attempts": [],
    }


class FakeDraftModel:
    def __init__(self, contents: list[str]):
        self.contents = contents
        self.invocations: list[list] = []
        self.max_tokens = 4096
        self.runnable = SimpleNamespace(profile={"max_input_tokens": 30_000})
        self.fallbacks = []

    def get_num_tokens_from_messages(self, messages) -> int:
        return 100

    def get_num_tokens(self, text: str) -> int:
        return 100

    async def ainvoke(self, messages):
        index = len(self.invocations)
        self.invocations.append(messages)
        return SimpleNamespace(
            content=self.contents[index],
            usage_metadata={"input_tokens": 10, "output_tokens": 20},
        )


@pytest.mark.asyncio
async def test_writer_autorepair_uses_previous_draft_and_failed_constraints(monkeypatch):
    fake_llm = FakeDraftModel(["PIERWSZY DRAFT", "DRUGI DRAFT"])
    validation_reports = iter(
        [
            _validation_report(
                passed=False,
                failure_codes=["keyword_in_h1", "meta_desc_length_ok"],
                failures=[
                    {
                        "code": "keyword_in_h1",
                        "message": 'H1 musi zawierać główne słowo kluczowe "AI marketing".',
                    },
                    {
                        "code": "meta_desc_length_ok",
                        "message": "Meta-description musi mieć 150-160 znaków; obecnie ma 121.",
                    },
                ],
                meta_description_length=121,
            ),
            _validation_report(passed=True),
        ]
    )

    monkeypatch.setattr(
        writer,
        "get_article_count",
        lambda: writer.settings.low_corpus_threshold,
    )
    monkeypatch.setattr(writer, "get_draft_llm", lambda **kwargs: fake_llm)
    monkeypatch.setattr(writer, "_fetch_rag_exemplars", lambda topic, n=5: [])
    monkeypatch.setattr(writer, "build_context_block", lambda context: "")
    monkeypatch.setattr(writer, "_validate_draft", lambda *args: next(validation_reports))
    monkeypatch.setattr(writer, "estimate_cost_usd", lambda *args, **kwargs: 0.25)

    result = await writer.writer_node(
        {
            "topic": "Temat testowy",
            "keywords": ["AI marketing"],
            "heading_structure": "# H1\n## H2",
            "research_report": "Raport",
        }
    )

    assert len(fake_llm.invocations) == 2
    second_prompt = fake_llm.invocations[1][1].content
    assert "WYMAGANE POPRAWKI SEO" in second_prompt
    assert "PIERWSZY DRAFT" in second_prompt
    assert 'H1 musi zawierać główne słowo kluczowe "AI marketing".' in second_prompt
    assert "Meta-description musi mieć 150-160 znaków; obecnie ma 121." in second_prompt
    assert result["draft_validated"] is True
    assert result["draft_validation_details"]["attempt_count"] == 2
    assert result["draft_validation_details"]["attempts"] == [
        {
            "attempt_number": 1,
            "passed": False,
            "failed_codes": ["keyword_in_h1", "meta_desc_length_ok"],
        },
        {"attempt_number": 2, "passed": True, "failed_codes": []},
    ]


@pytest.mark.asyncio
async def test_writer_autorepair_preserves_user_feedback_priority(monkeypatch):
    fake_llm = FakeDraftModel(["DRAFT PO FEEDBACKU", "DRAFT PO NAPRAWIE"])
    validation_reports = iter(
        [
            _validation_report(
                passed=False,
                failure_codes=["word_count_ok"],
                failures=[
                    {
                        "code": "word_count_ok",
                        "message": "Treść artykułu ma 640 słów; wymagane minimum to 800.",
                    }
                ],
                body_word_count=640,
            ),
            _validation_report(passed=True),
        ]
    )

    monkeypatch.setattr(
        writer,
        "get_article_count",
        lambda: writer.settings.low_corpus_threshold,
    )
    monkeypatch.setattr(writer, "get_draft_llm", lambda **kwargs: fake_llm)
    monkeypatch.setattr(writer, "_fetch_rag_exemplars", lambda topic, n=5: [])
    monkeypatch.setattr(writer, "build_context_block", lambda context: "")
    monkeypatch.setattr(writer, "_validate_draft", lambda *args: next(validation_reports))
    monkeypatch.setattr(writer, "estimate_cost_usd", lambda *args, **kwargs: 0.25)

    await writer.writer_node(
        {
            "topic": "Temat testowy",
            "keywords": ["AI marketing"],
            "heading_structure": "# H1\n## H2",
            "research_report": "Raport",
            "draft": "OBECNY DRAFT",
            "cp2_feedback": "Dodaj konkretny case study i mocniejszy wstęp.",
        }
    )

    first_prompt = fake_llm.invocations[0][1].content
    second_prompt = fake_llm.invocations[1][1].content
    assert "FEEDBACK UŻYTKOWNIKA" in first_prompt
    assert "OBECNY DRAFT" in first_prompt
    assert "FEEDBACK I WYMAGANE POPRAWKI" in second_prompt
    assert "Priorytet 1 — uwzględnij feedback użytkownika:" in second_prompt
    assert "Dodaj konkretny case study i mocniejszy wstęp." in second_prompt
    assert "Treść artykułu ma 640 słów; wymagane minimum to 800." in second_prompt


@pytest.mark.asyncio
async def test_writer_successful_first_pass_skips_autorepair_prompt(monkeypatch):
    fake_llm = FakeDraftModel(["GOTOWY DRAFT"])

    monkeypatch.setattr(
        writer,
        "get_article_count",
        lambda: writer.settings.low_corpus_threshold,
    )
    monkeypatch.setattr(writer, "get_draft_llm", lambda **kwargs: fake_llm)
    monkeypatch.setattr(writer, "_fetch_rag_exemplars", lambda topic, n=5: [])
    monkeypatch.setattr(writer, "build_context_block", lambda context: "")
    monkeypatch.setattr(
        writer,
        "_validate_draft",
        lambda *args: _validation_report(passed=True),
    )
    monkeypatch.setattr(writer, "estimate_cost_usd", lambda *args, **kwargs: 0.25)

    result = await writer.writer_node(
        {
            "topic": "Temat testowy",
            "keywords": ["AI marketing"],
            "heading_structure": "# H1\n## H2",
            "research_report": "Raport",
        }
    )

    assert len(fake_llm.invocations) == 1
    first_prompt = fake_llm.invocations[0][1].content
    assert "WYMAGANE POPRAWKI SEO" not in first_prompt
    assert "FEEDBACK I WYMAGANE POPRAWKI" not in first_prompt
    assert result["draft_validated"] is True
    assert result["draft_validation_details"]["attempt_count"] == 1
