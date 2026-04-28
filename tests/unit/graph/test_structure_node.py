import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

fake_langchain_anthropic = types.ModuleType("langchain_anthropic")
fake_langchain_anthropic.ChatAnthropic = object
sys.modules.setdefault("langchain_anthropic", fake_langchain_anthropic)

fake_langchain_openai = types.ModuleType("langchain_openai")
fake_langchain_openai.ChatOpenAI = object
sys.modules.setdefault("langchain_openai", fake_langchain_openai)

sys.modules.pop("bond.graph.nodes.structure", None)
structure = importlib.import_module("bond.graph.nodes.structure")


def _research_data() -> dict:
    return {
        "fakty": [
            "FAKT_ALPHA: Proces wymaga akceptacji człowieka.",
            "FAKT_TAIL: Późny fakt z końca raportu musi przetrwać.",
        ],
        "statystyki": [
            "STAT_TAIL: 91% - późna statystyka nie może zniknąć.",
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


class FakeDraftModel:
    def __init__(self, *, max_input_tokens: int, token_counter=None):
        self.max_tokens = 800
        self.runnable = SimpleNamespace(profile={"max_input_tokens": max_input_tokens})
        self.fallbacks = []
        self.token_counter = token_counter or (
            lambda payload: len(_payload_text(payload).split())
        )
        self.prompts: list[str] = []

    def get_num_tokens_from_messages(self, messages) -> int:
        return self.token_counter(messages)

    def get_num_tokens(self, text: str) -> int:
        return self.token_counter(text)

    async def ainvoke(self, prompt: str):
        self.prompts.append(prompt)
        return SimpleNamespace(
            content="# H1\n## H2",
            usage_metadata={"input_tokens": 11, "output_tokens": 7},
        )


@pytest.mark.asyncio
async def test_structure_node_keeps_late_report_content_when_prompt_fits(monkeypatch):
    report = "Raport.\n" + ("WSTĘP " * 450) + "LATE_REPORT_SENTINEL"
    fake_llm = FakeDraftModel(max_input_tokens=20_000)

    monkeypatch.setattr(structure, "get_draft_llm", lambda **kwargs: fake_llm)
    monkeypatch.setattr(structure, "build_context_block", lambda context: "")
    monkeypatch.setattr(structure, "estimate_cost_usd", lambda *args, **kwargs: 0.15)

    result = await structure.structure_node(
        {
            "topic": "Temat testowy",
            "keywords": ["fraza"],
            "research_report": report,
            "research_data": _research_data(),
        }
    )

    assert "LATE_REPORT_SENTINEL" in fake_llm.prompts[0]
    assert result["heading_structure"] == "# H1\n## H2"
    assert result["tokens_used_research"] == 18
    assert result["estimated_cost_usd"] == 0.15


@pytest.mark.asyncio
async def test_structure_node_uses_compacted_variant_in_feedback_path_instead_of_raw_slice(
    monkeypatch,
):
    report = ("PREFIKS " * 500) + "LATE_REPORT_SENTINEL"

    def token_counter(payload) -> int:
        text = _payload_text(payload)
        tokens = 40
        if "LATE_REPORT_SENTINEL" in text:
            tokens += 200
        if "FAKT_TAIL" in text:
            tokens += 10
        if "STAT_TAIL" in text:
            tokens += 10
        if "Źródło 1" in text:
            tokens += 15
        if "Źródło 2" in text:
            tokens += 15
        if "Źródło 3" in text:
            tokens += 15
        return tokens

    fake_llm = FakeDraftModel(max_input_tokens=1_260, token_counter=token_counter)

    monkeypatch.setattr(structure, "get_draft_llm", lambda **kwargs: fake_llm)
    monkeypatch.setattr(structure, "build_context_block", lambda context: "")
    monkeypatch.setattr(structure, "estimate_cost_usd", lambda *args, **kwargs: 0.05)

    await structure.structure_node(
        {
            "topic": "Temat testowy",
            "keywords": ["fraza"],
            "research_report": report,
            "research_data": _research_data(),
            "cp1_feedback": "Zostaw H2 o wdrożeniu.",
            "cp1_iterations": 1,
        }
    )

    prompt = fake_llm.prompts[0]
    assert "Zostaw H2 o wdrożeniu." in prompt
    assert "FAKT_TAIL" in prompt
    assert "STAT_TAIL" in prompt
    assert structure.select_research_context is not None
    assert "LATE_REPORT_SENTINEL" not in prompt
    assert "Źródło 1" not in prompt
    assert "[Pominięto część źródeł z powodu limitu kontekstu modelu." in prompt
