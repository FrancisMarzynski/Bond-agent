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

sys.modules.pop("bond.graph.nodes.shadow_annotate", None)
shadow_annotate = importlib.import_module("bond.graph.nodes.shadow_annotate")


def test_shadow_annotate_prompt_forces_polish_reason_text():
    prompt = shadow_annotate._build_user_prompt(
        "To jest tekst testowy do korekty stylistycznej.",
        [{"text": "Wzorcowy fragment autora."}],
    )

    assert "Pole `reason` napisz wyłącznie po polsku." in prompt
    assert "Wszystkie pola tekstowe odpowiedzi muszą być po polsku." in shadow_annotate._SYSTEM_PROMPT

    reason_description = shadow_annotate.AnnotationItem.model_json_schema()["properties"]["reason"]["description"]
    assert "po polsku" in reason_description
    assert "Your style" not in reason_description
