import importlib
import sys
import types
from types import SimpleNamespace

import pytest
from langgraph.graph import END

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

writer = importlib.import_module("bond.graph.nodes.writer")


def _valid_report(primary_keyword: str = "Temat", min_words: int = 800) -> dict:
    return {
        "passed": True,
        "checks": {
            "keyword_in_h1": True,
            "keyword_in_first_para": True,
            "meta_desc_length_ok": True,
            "word_count_ok": True,
            "no_forbidden_words": True,
        },
        "failure_codes": [],
        "failures": [],
        "primary_keyword": primary_keyword,
        "body_word_count": min_words + 50,
        "min_words": min_words,
        "meta_description_length": 155,
        "meta_description_min_length": 150,
        "meta_description_max_length": 160,
        "forbidden_stems": [],
        "attempt_count": 0,
        "attempts": [],
    }


class LowCorpusInterrupt(Exception):
    def __init__(self, payload):
        super().__init__("interrupt")
        self.payload = payload


class FakeCollection:
    def __init__(self, count_value: int):
        self._count_value = count_value

    def count(self) -> int:
        return self._count_value


class FakeDraftModel:
    async def ainvoke(self, messages):
        return SimpleNamespace(
            content="# Tytul\n\nTo jest poprawny draft testowy.",
            usage_metadata={"input_tokens": 10, "output_tokens": 20},
        )


@pytest.mark.asyncio
async def test_writer_low_corpus_interrupt_payload_shape(monkeypatch):
    monkeypatch.setattr(writer.settings, "low_corpus_threshold", 11)
    monkeypatch.setattr(writer, "get_article_count", lambda: 0)
    monkeypatch.setattr(
        writer,
        "get_corpus_collection",
        lambda: (_ for _ in ()).throw(
            AssertionError("writer low-corpus gate should not read Chroma chunk count")
        ),
    )

    def fake_interrupt(payload):
        raise LowCorpusInterrupt(payload)

    monkeypatch.setattr(writer, "interrupt", fake_interrupt)

    with pytest.raises(LowCorpusInterrupt) as excinfo:
        await writer.writer_node({"topic": "Temat", "keywords": []})

    payload = excinfo.value.payload
    assert payload["checkpoint"] == "low_corpus"
    assert payload["type"] == "approve_reject"
    assert payload["corpus_count"] == 0
    assert payload["threshold"] == 11
    assert "Korpus zawiera tylko 0 artykułów" in payload["warning"]


@pytest.mark.asyncio
async def test_writer_low_corpus_approve_continues_generation(monkeypatch):
    monkeypatch.setattr(writer, "get_article_count", lambda: 0)
    monkeypatch.setattr(writer, "interrupt", lambda payload: {"action": "approve"})
    monkeypatch.setattr(writer, "get_draft_llm", lambda **kwargs: FakeDraftModel())
    monkeypatch.setattr(writer, "_fetch_rag_exemplars", lambda topic, n=5: [])
    monkeypatch.setattr(writer, "build_context_block", lambda context: "")
    monkeypatch.setattr(
        writer, "_validate_draft", lambda draft, keyword, min_words: _valid_report(keyword, min_words)
    )
    monkeypatch.setattr(writer, "estimate_cost_usd", lambda *args, **kwargs: 0.25)

    result = await writer.writer_node(
        {
            "topic": "Temat",
            "keywords": [],
            "heading_structure": "# Tytul",
            "research_report": "Raport",
        }
    )

    assert result["draft"].startswith("# Tytul")
    assert result["draft_validated"] is True
    assert result["draft_validation_details"]["attempt_count"] == 1
    assert result["tokens_used_draft"] == 30
    assert result["estimated_cost_usd"] == 0.25


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["reject", "abort"])
async def test_writer_low_corpus_reject_and_abort_terminate_safely(monkeypatch, action):
    monkeypatch.setattr(writer, "get_article_count", lambda: 0)
    monkeypatch.setattr(writer, "interrupt", lambda payload: {"action": action})

    result = await writer.writer_node({"topic": "Temat", "keywords": []})

    assert result.goto == END
    assert result.update == {
        "draft": "",
        "draft_validated": False,
        "draft_validation_details": None,
    }
