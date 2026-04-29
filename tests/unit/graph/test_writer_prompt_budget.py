import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.graph import END

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


def _research_data() -> dict:
    return {
        "fakty": [
            "FAKT_ALPHA: Wszystkie drafty nadal wymagają akceptacji człowieka.",
            "FAKT_TAIL: Późny fakt ma przejść do promptu.",
        ],
        "statystyki": [
            "STAT_ALPHA: 41% - wcześniejsza statystyka testowa.",
            "STAT_TAIL: 97% - późna statystyka testowa.",
        ],
        "zrodla": [
            {
                "title": "Źródło 1",
                "url": "https://example.com/1",
                "summary": "SUMMARY_1",
            },
            {
                "title": "Źródło 2",
                "url": "https://example.com/2",
                "summary": "SUMMARY_2",
            },
            {
                "title": "Źródło 3",
                "url": "https://example.com/3",
                "summary": "SUMMARY_TAIL",
            },
        ],
    }


def _payload_text(payload) -> str:
    if isinstance(payload, str):
        return payload
    return "\n".join(str(getattr(message, "content", message)) for message in payload)


def test_writer_system_prompt_does_not_require_visible_thinking_tags():
    assert "&lt;thinking&gt;" not in writer.WRITER_SYSTEM_PROMPT


class FakeCollection:
    def __init__(self, count_value: int):
        self._count_value = count_value

    def count(self) -> int:
        return self._count_value


class FakeDraftModel:
    def __init__(self, *, max_input_tokens: int, token_counter=None):
        self.max_tokens = 4096
        self.runnable = SimpleNamespace(profile={"max_input_tokens": max_input_tokens})
        self.fallbacks = []
        self.token_counter = token_counter or (
            lambda payload: len(_payload_text(payload).split())
        )
        self.invocations: list[list] = []

    def get_num_tokens_from_messages(self, messages) -> int:
        return self.token_counter(messages)

    def get_num_tokens(self, text: str) -> int:
        return self.token_counter(text)

    async def ainvoke(self, messages):
        self.invocations.append(messages)
        return SimpleNamespace(
            content="# Tytuł\n\nTo jest poprawny draft testowy.",
            usage_metadata={"input_tokens": 10, "output_tokens": 20},
        )


@pytest.mark.asyncio
async def test_writer_fresh_draft_prompt_keeps_late_report_content_when_budget_allows(
    monkeypatch,
):
    report = "Raport.\n" + ("WSTĘP " * 700) + "LATE_REPORT_SENTINEL"
    fake_llm = FakeDraftModel(max_input_tokens=30_000)

    monkeypatch.setattr(
        writer,
        "get_article_count",
        lambda: writer.settings.low_corpus_threshold,
    )
    monkeypatch.setattr(writer, "get_draft_llm", lambda **kwargs: fake_llm)
    monkeypatch.setattr(writer, "_fetch_rag_exemplars", lambda topic, n=5: [])
    monkeypatch.setattr(writer, "build_context_block", lambda context: "")
    monkeypatch.setattr(
        writer, "_validate_draft", lambda draft, keyword, min_words: {"seo": True}
    )
    monkeypatch.setattr(writer, "estimate_cost_usd", lambda *args, **kwargs: 0.25)

    result = await writer.writer_node(
        {
            "topic": "Temat",
            "keywords": ["fraza"],
            "heading_structure": "# H1\n## H2",
            "research_report": report,
            "research_data": _research_data(),
        }
    )

    human_message = fake_llm.invocations[0][1].content
    assert "LATE_REPORT_SENTINEL" in human_message
    assert result["draft_validated"] is True
    assert result["tokens_used_draft"] == 30


@pytest.mark.asyncio
async def test_writer_tight_budget_drops_sources_before_losing_facts_and_stats(
    monkeypatch,
):
    report = ("PREFIKS " * 800) + "LATE_REPORT_SENTINEL"

    def token_counter(payload) -> int:
        text = _payload_text(payload)
        tokens = 100
        if "LATE_REPORT_SENTINEL" in text:
            tokens += 300
        if "FAKT_ALPHA" in text:
            tokens += 10
        if "FAKT_TAIL" in text:
            tokens += 10
        if "STAT_ALPHA" in text:
            tokens += 10
        if "STAT_TAIL" in text:
            tokens += 10
        if "Źródło 1" in text:
            tokens += 25
        if "Źródło 2" in text:
            tokens += 25
        if "Źródło 3" in text:
            tokens += 25
        return tokens

    fake_llm = FakeDraftModel(max_input_tokens=4_696, token_counter=token_counter)

    monkeypatch.setattr(
        writer,
        "get_article_count",
        lambda: writer.settings.low_corpus_threshold,
    )
    monkeypatch.setattr(writer, "get_draft_llm", lambda **kwargs: fake_llm)
    monkeypatch.setattr(writer, "_fetch_rag_exemplars", lambda topic, n=5: [])
    monkeypatch.setattr(writer, "build_context_block", lambda context: "")
    monkeypatch.setattr(
        writer, "_validate_draft", lambda draft, keyword, min_words: {"seo": True}
    )
    monkeypatch.setattr(writer, "estimate_cost_usd", lambda *args, **kwargs: 0.25)

    await writer.writer_node(
        {
            "topic": "Temat",
            "keywords": ["fraza"],
            "heading_structure": "# H1\n## H2",
            "research_report": report,
            "research_data": _research_data(),
        }
    )

    human_message = fake_llm.invocations[0][1].content
    assert "FAKT_ALPHA" in human_message
    assert "FAKT_TAIL" in human_message
    assert "STAT_ALPHA" in human_message
    assert "STAT_TAIL" in human_message
    assert "Źródło 1" in human_message
    assert "Źródło 2" in human_message
    assert "Źródło 3" not in human_message
    assert "[Pominięto część źródeł z powodu limitu kontekstu modelu." in human_message
    assert "LATE_REPORT_SENTINEL" not in human_message


@pytest.mark.asyncio
async def test_writer_low_corpus_reject_still_short_circuits_before_budgeting(
    monkeypatch,
):
    monkeypatch.setattr(writer, "get_article_count", lambda: 0)
    monkeypatch.setattr(writer, "interrupt", lambda payload: {"action": "reject"})

    def fail_get_draft_llm(**kwargs):
        raise AssertionError("writer should stop before initializing the draft model")

    monkeypatch.setattr(writer, "get_draft_llm", fail_get_draft_llm)

    result = await writer.writer_node({"topic": "Temat", "keywords": []})

    assert result.goto == END
    assert result.update == {"draft": "", "draft_validated": False}
