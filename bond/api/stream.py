import json
import logging
from typing import AsyncIterator, Any, Iterator

from bond.schemas import StreamEvent

logger = logging.getLogger(__name__)

# Business nodes we surface to the frontend — internal LangGraph bookkeeping nodes
# (__start__, __end__, router functions) are intentionally excluded.
_KNOWN_NODES = frozenset({
    "duplicate_check",
    "researcher",
    "structure",
    "checkpoint_1",
    "writer",
    "checkpoint_2",
    "save_metadata",
    "shadow_analyze",
    "shadow_annotate",
    "shadow_checkpoint",
})

# Mapping from node name to the stage label expected by the frontend.
_STAGE_MAP: dict[str, str] = {
    "researcher": "research",
    "structure": "structure",
    "writer": "writing",
    "save_metadata": "done",
}


async def parse_stream_events(events: AsyncIterator[Any]) -> AsyncIterator[str]:
    """
    Parses LangGraph astream_events (v2) and yields raw JSON StreamEvent strings.

    Handles three LangGraph event kinds:
    - on_chain_start  → node_start  +  optional stage update
    - on_chain_end    → node_end
    - on_chat_model_stream → token  (empty chunks are dropped)

    The caller is responsible for catching exceptions that propagate out of this
    generator (e.g. model API errors, rate-limit errors).  The generator performs
    best-effort cleanup of `events` in its finally block.
    """
    try:
        async for event in events:
            kind = event.get("event")

            if kind == "on_chain_start":
                node_name = _extract_node_name(event)
                if node_name:
                    yield StreamEvent(type="node_start", data=node_name).model_dump_json()
                    if node_name in _STAGE_MAP:
                        yield StreamEvent(
                            type="stage",
                            data=json.dumps({"stage": _STAGE_MAP[node_name], "status": "running"}),
                        ).model_dump_json()

            elif kind == "on_chain_end":
                node_name = _extract_node_name(event)
                if node_name:
                    yield StreamEvent(type="node_end", data=node_name).model_dump_json()

            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is not None:
                    for text in _iter_token_texts(chunk):
                        yield StreamEvent(type="token", data=text).model_dump_json()

    finally:
        # Best-effort cleanup: close the astream_events async iterator so that
        # the underlying LangGraph tasks are cancelled when the client disconnects
        # or an error occurs upstream.
        if hasattr(events, "aclose"):
            try:
                await events.aclose()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_node_name(event: dict) -> str | None:
    """
    Return the business-logic node name from a LangGraph event, or None for
    internal nodes (__start__, __end__, routing functions, etc.).
    """
    # Primary source: LangGraph sets this on every node event.
    node_name = event.get("metadata", {}).get("langgraph_node")

    # Fallback: top-level "name" field (present on some older event shapes).
    if not node_name:
        node_name = event.get("name", "")

    return node_name if node_name in _KNOWN_NODES else None


def _iter_token_texts(chunk: Any) -> Iterator[str]:
    """
    Yield individual non-empty text strings from an LLM streaming chunk.

    Handles:
    - AIMessageChunk with str content      (OpenAI / most models)
    - AIMessageChunk with list[ContentBlock] (Anthropic extended format — each
      block becomes a separate token to preserve streaming granularity)
    - Plain dict with a "content" key
    """
    if hasattr(chunk, "content"):
        content = chunk.content
        if isinstance(content, str):
            if content:
                yield content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        yield text
    elif isinstance(chunk, dict):
        content = chunk.get("content", "")
        if isinstance(content, str) and content:
            yield content
