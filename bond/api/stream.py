import json
import logging
from typing import AsyncIterator, Any, Iterator

from bond.schemas import StreamEvent

logger = logging.getLogger(__name__)

_OPEN_THINKING_TAG = "<thinking>"
_CLOSE_THINKING_TAG = "</thinking>"

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
# Covers both author mode and shadow mode pipelines in full.
_STAGE_MAP: dict[str, str] = {
    "duplicate_check": "checking",
    "researcher": "research",
    "structure": "structure",
    "checkpoint_1": "structure",     # paused at structure review
    "writer": "writing",
    "checkpoint_2": "writing",       # paused at draft review
    "save_metadata": "done",
    "shadow_analyze": "shadow_analysis",
    "shadow_annotate": "shadow_annotation",
    "shadow_checkpoint": "shadow_annotation",  # paused at annotation review
}

# Human-readable Polish labels for node start/end lifecycle events.
# Keyed by node name → {"start": ..., "end": ...}.
# Used to produce informative UI messages without leaking internal node names.
_NODE_LABELS: dict[str, dict[str, str]] = {
    "duplicate_check": {
        "start": "Sprawdzam duplikaty tematów...",
        "end": "Weryfikacja duplikatów zakończona",
    },
    "researcher": {
        "start": "Wyszukuję informacje o temacie...",
        "end": "Badania zakończone",
    },
    "structure": {
        "start": "Tworzę strukturę artykułu...",
        "end": "Struktura artykułu gotowa",
    },
    "checkpoint_1": {
        "start": "Oczekuję na zatwierdzenie struktury...",
        "end": "Struktura zatwierdzona",
    },
    "writer": {
        "start": "Piszę treść artykułu...",
        "end": "Wersja robocza gotowa",
    },
    "checkpoint_2": {
        "start": "Oczekuję na zatwierdzenie wersji roboczej...",
        "end": "Wersja robocza zatwierdzona",
    },
    "save_metadata": {
        "start": "Zapisuję metadane artykułu...",
        "end": "Artykuł zapisany pomyślnie",
    },
    "shadow_analyze": {
        "start": "Analizuję styl na podstawie korpusu...",
        "end": "Analiza stylistyczna zakończona",
    },
    "shadow_annotate": {
        "start": "Generuję adnotacje stylistyczne...",
        "end": "Adnotacje stylistyczne gotowe",
    },
    "shadow_checkpoint": {
        "start": "Oczekuję na zatwierdzenie adnotacji...",
        "end": "Adnotacje zatwierdzone",
    },
}


class _WriterTokenSanitizer:
    """Incrementally strip <thinking>...</thinking> blocks from writer tokens."""

    def __init__(self) -> None:
        self._buffer = ""
        self._inside_thinking = False

    def reset(self) -> None:
        self._buffer = ""
        self._inside_thinking = False

    def feed(self, text: str) -> Iterator[str]:
        if not text:
            return

        self._buffer += text

        while self._buffer:
            if self._inside_thinking:
                close_index = self._buffer.find(_CLOSE_THINKING_TAG)
                if close_index != -1:
                    self._buffer = self._buffer[
                        close_index + len(_CLOSE_THINKING_TAG) :
                    ]
                    self._inside_thinking = False
                    continue

                suffix_length = _matching_tag_suffix_length(
                    self._buffer, _CLOSE_THINKING_TAG
                )
                self._buffer = self._buffer[-suffix_length:] if suffix_length else ""
                return

            open_index = self._buffer.find(_OPEN_THINKING_TAG)
            if open_index != -1:
                visible_text = self._buffer[:open_index]
                if visible_text:
                    yield visible_text

                self._buffer = self._buffer[open_index + len(_OPEN_THINKING_TAG) :]
                self._inside_thinking = True
                continue

            suffix_length = _matching_tag_suffix_length(self._buffer, _OPEN_THINKING_TAG)
            visible_end = len(self._buffer) - suffix_length
            visible_text = self._buffer[:visible_end]
            if visible_text:
                yield visible_text

            self._buffer = self._buffer[visible_end:]
            return


async def parse_stream_events(events: AsyncIterator[Any]) -> AsyncIterator[str]:
    """
    Parses LangGraph astream_events (v2) and yields raw JSON StreamEvent strings.

    Handles three LangGraph event kinds:
    - on_chain_start       → node_start  +  optional stage update
    - on_chain_end         → node_end
    - on_chat_model_stream → token  (empty chunks are dropped)

    All non-token events carry JSON-encoded ``data`` fields so that the
    frontend can deserialise them uniformly.  Token events carry raw text
    to avoid the overhead of an extra JSON layer on the hot streaming path.

    The caller is responsible for catching exceptions that propagate out of
    this generator (e.g. model API errors, rate-limit errors).  The generator
    performs best-effort cleanup of ``events`` in its finally block.
    """
    active_node: str | None = None
    writer_token_sanitizer = _WriterTokenSanitizer()

    try:
        async for event in events:
            kind = event.get("event")

            if kind == "on_chain_start":
                node_name = _extract_node_name(event)
                if node_name:
                    active_node = node_name
                    if node_name == "writer":
                        writer_token_sanitizer.reset()
                    label = _NODE_LABELS.get(node_name, {}).get("start", node_name)
                    yield StreamEvent(
                        type="node_start",
                        data=json.dumps({"node": node_name, "label": label}),
                    ).model_dump_json()
                    if node_name in _STAGE_MAP:
                        yield StreamEvent(
                            type="stage",
                            data=json.dumps({
                                "stage": _STAGE_MAP[node_name],
                                "status": "running",
                                "label": label,
                            }),
                        ).model_dump_json()

            elif kind == "on_chain_end":
                node_name = _extract_node_name(event)
                if node_name:
                    label = _NODE_LABELS.get(node_name, {}).get("end", node_name)
                    yield StreamEvent(
                        type="node_end",
                        data=json.dumps({"node": node_name, "label": label}),
                    ).model_dump_json()
                    if node_name == active_node:
                        active_node = None
                    if node_name == "writer":
                        writer_token_sanitizer.reset()

            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is not None:
                    for text in _iter_token_texts(chunk):
                        token_texts = (
                            writer_token_sanitizer.feed(text)
                            if active_node == "writer"
                            else (text,)
                        )
                        for token_text in token_texts:
                            if token_text:
                                yield StreamEvent(
                                    type="token", data=token_text
                                ).model_dump_json()

    finally:
        # Best-effort cleanup: close the astream_events async iterator so that
        # LangGraph releases its internal resources when the producer finishes or
        # an unrecoverable error occurs. This runs in the background task, not in
        # the SSE response generator, so it does not cancel graph execution on
        # client disconnect.
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


def _matching_tag_suffix_length(text: str, tag: str) -> int:
    max_length = min(len(text), len(tag) - 1)
    for suffix_length in range(max_length, 0, -1):
        if text.endswith(tag[:suffix_length]):
            return suffix_length
    return 0


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
