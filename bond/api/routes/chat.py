import asyncio
import json
import logging
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator
from sse_starlette.sse import EventSourceResponse

from bond.api.stream import parse_stream_events
from bond.schemas import StreamEvent
from langgraph.types import Command
from langgraph.errors import GraphRecursionError

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Input constraints ---
SHADOW_MAX_CHARS = 10_000   # ~2 500 tokens — prevents runaway context in shadow mode
TOPIC_MAX_CHARS = 1_000     # author mode topic guard

# --- Per-thread resume lock — prevents race conditions when rapidly clicking "Reject" ---
_resume_locks: dict[str, asyncio.Lock] = {}

# Sentinel prefix used to pass stream metadata from _stream_graph_events to callers.
_META_PREFIX = "__META__:"

# LangGraph recursion limit — acts as safety backstop behind the per-node hard caps.
# Base path: ~7 nodes. cp1 loop: up to 10 * 2 = 20. cp2 loop: up to 10 * 2 = 20. Total ≤ 47.
_RECURSION_LIMIT = 50

# SSE response headers shared by all streaming endpoints.
# Note: EventSourceResponse already sets Connection: keep-alive and
# X-Accel-Buffering: no automatically; we only override Cache-Control.
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Content-Encoding": "identity",
}


def _get_resume_lock(thread_id: str) -> asyncio.Lock:
    """Return (and lazily create) a per-thread asyncio.Lock."""
    if thread_id not in _resume_locks:
        _resume_locks[thread_id] = asyncio.Lock()
    return _resume_locks[thread_id]


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    mode: str = "author"

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, v: str, info) -> str:
        # Apply the stricter shadow limit universally; mode-specific feedback is
        # handled inside the endpoint itself.
        if len(v) > SHADOW_MAX_CHARS:
            raise ValueError(
                f"Tekst wejściowy jest zbyt długi ({len(v)} znaków). "
                f"Maksimum dla trybu Shadow Mode: {SHADOW_MAX_CHARS} znaków."
            )
        return v


class ResumeRequest(BaseModel):
    thread_id: str
    action: str
    feedback: Optional[str] = None
    edited_structure: Optional[str] = None
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Core SSE streaming helper
# ---------------------------------------------------------------------------

async def _stream_graph_events(graph, input_or_command, config: dict, request: Request):
    """
    Async generator that drives ``graph.astream_events(version="v2")``.

    Design:
    - Wraps ``parse_stream_events`` in an inner generator that catches all errors
      and converts them to SSE ``error`` events, while tracking whether the error
      occurred via ``had_error``.
    - Sends an SSE ``heartbeat`` every 15 s so that proxies/load-balancers do not
      time out idle connections.
    - Polls ``request.is_disconnected()`` on every 1 s timeout to detect client
      drops and stop processing without waiting for the next LangGraph event.
    - Closes the inner generator in a ``finally`` block to guarantee that the
      underlying ``astream_events`` async iterator and any open model connections
      are properly released — even on client disconnect or task cancellation.

    Yields:
        Raw JSON strings (StreamEvent payloads) consumed by EventSourceResponse.
        One terminal sentinel ``"__META__:{...}"`` carrying bookkeeping flags.
    """
    events = graph.astream_events(input_or_command, config=config, version="v2")

    # Tracks whether a model / graph error occurred inside the inner generator.
    # Used to distinguish a clean "stream finished" from "stream finished after error".
    had_error = False

    async def _inner():
        """Parse LangGraph events and surface errors as SSE error events."""
        nonlocal had_error
        try:
            async for json_str in parse_stream_events(events):
                yield json_str
        except GraphRecursionError:
            had_error = True
            yield StreamEvent(
                type="error",
                data=(
                    "Osiągnięto limit iteracji pętli HITL. "
                    "Pipeline zatrzymany automatycznie po przekroczeniu maksymalnej liczby kroków."
                ),
            ).model_dump_json()
        except Exception as exc:
            had_error = True
            logger.error("Model/graph error during streaming: %s", exc, exc_info=True)
            yield StreamEvent(type="error", data=str(exc)).model_dump_json()

    gen = _inner()
    last_heartbeat = asyncio.get_event_loop().time()
    client_disconnected = False
    finished_cleanly = False

    try:
        while True:
            # Check for client disconnect before every pull from the graph.
            if await request.is_disconnected():
                client_disconnected = True
                break

            try:
                chunk = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
                yield chunk
                last_heartbeat = asyncio.get_event_loop().time()

            except asyncio.TimeoutError:
                # No event arrived within 1 s; maybe send a heartbeat.
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat > 15.0:
                    yield StreamEvent(type="heartbeat", data="ping").model_dump_json()
                    last_heartbeat = now

            except StopAsyncIteration:
                # Inner generator exhausted.  Mark as clean only when no error occurred.
                finished_cleanly = not had_error
                break

    except asyncio.CancelledError:
        # Task was cancelled (e.g. ASGI server shutdown).  Treat as client disconnect.
        client_disconnected = True

    except Exception as exc:
        # Unexpected error in the outer polling loop (not from the model).
        had_error = True
        logger.error("Unexpected error in stream loop: %s", exc, exc_info=True)
        yield StreamEvent(type="error", data=str(exc)).model_dump_json()

    finally:
        # Always close the inner generator so that parse_stream_events' finally block
        # runs and the astream_events iterator is released — freeing model connections.
        await gen.aclose()

    yield _META_PREFIX + json.dumps({
        "finished_cleanly": finished_cleanly,
        "client_disconnected": client_disconnected,
    })


# ---------------------------------------------------------------------------
# Post-stream state emission helpers
# ---------------------------------------------------------------------------

async def _emit_post_stream_events(graph, config: dict, thread_id: str, request: Request):
    """
    After the graph stream finishes cleanly, inspect the persisted checkpoint
    and yield any final SSE events (hitl_pause, done, shadow output, …).

    Yields raw JSON strings for EventSourceResponse.
    """
    state_snapshot = await graph.aget_state(config)

    if state_snapshot.next:
        # Graph is paused at a HITL checkpoint — surface stage + pause info.
        history_state = await get_chat_history(thread_id, request, state_snapshot=state_snapshot)
        if history_state.get("stage"):
            yield StreamEvent(
                type="stage",
                data=json.dumps({
                    "stage": history_state["stage"],
                    "status": history_state["stageStatus"].get(history_state["stage"], "running"),
                }),
            ).model_dump_json()
        if history_state.get("hitlPause"):
            yield StreamEvent(
                type="hitl_pause",
                data=json.dumps(history_state["hitlPause"]),
            ).model_dump_json()
    else:
        # Graph reached END — emit terminal output events.
        st = state_snapshot.values

        hard_cap_msg = st.get("hard_cap_message")
        if hard_cap_msg:
            yield StreamEvent(type="system_alert", data=hard_cap_msg).model_dump_json()

        shadow_corrected = st.get("shadow_corrected_text") or ""
        annotations = st.get("annotations") or []

        if shadow_corrected:
            yield StreamEvent(
                type="shadow_corrected_text",
                data=json.dumps({"text": shadow_corrected}),
            ).model_dump_json()
        if annotations:
            yield StreamEvent(
                type="annotations",
                data=json.dumps(annotations),
            ).model_dump_json()

        yield StreamEvent(type="done", data="done").model_dump_json()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """
    POST /api/chat/stream

    Starts a new agent pipeline run and streams events back as SSE.

    SSE event types (all carry ``{"type": "<kind>", "data": "<payload>"}`` JSON):
      thread_id         — emitted first; carries the session ID
      node_start/end    — LangGraph node lifecycle
      stage             — frontend pipeline stage update
      token             — LLM output chunk
      heartbeat         — keep-alive ping (every 15 s of inactivity)
      hitl_pause        — graph paused at a HITL checkpoint
      shadow_corrected_text / annotations — shadow mode final output
      system_alert      — hard-cap or other non-fatal warning
      done              — terminal event (graph reached END cleanly)
      error             — model or graph error; connection closed afterwards
    """
    thread_id = req.thread_id or str(uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": _RECURSION_LIMIT,
    }
    graph = request.app.state.graph

    initial_state: dict = {
        "topic": req.message,
        "keywords": [],
        "messages": [{"role": "user", "content": req.message}],
        "mode": req.mode,
    }
    if req.mode == "shadow":
        initial_state["original_text"] = req.message

    async def generate():
        # Always emit thread_id first so the frontend can associate events.
        yield StreamEvent(type="thread_id", data=json.dumps({"thread_id": thread_id})).model_dump_json()

        finished_cleanly = False
        client_disconnected = False

        async for chunk in _stream_graph_events(graph, initial_state, config, request):
            if chunk.startswith(_META_PREFIX):
                meta = json.loads(chunk[len(_META_PREFIX):])
                finished_cleanly = meta["finished_cleanly"]
                client_disconnected = meta["client_disconnected"]
            else:
                yield chunk

        if finished_cleanly and not client_disconnected:
            async for event_json in _emit_post_stream_events(graph, config, thread_id, request):
                yield event_json

    return EventSourceResponse(generate(), headers=_SSE_HEADERS, ping=None)


@router.post("/resume")
async def chat_resume(req: ResumeRequest, request: Request):
    """
    POST /api/chat/resume

    Resumes the agent pipeline after a HITL checkpoint pause.

    Per-thread asyncio.Lock prevents race conditions when the user rapidly
    clicks "Reject" — only one resume request per thread_id executes at once.
    """
    config = {
        "configurable": {"thread_id": req.thread_id},
        "recursion_limit": _RECURSION_LIMIT,
    }
    graph = request.app.state.graph
    lock = _get_resume_lock(req.thread_id)

    resume_value: dict[str, Any] = {"action": req.action}
    if req.feedback:
        resume_value["feedback"] = req.feedback
    if req.edited_structure:
        resume_value["edited_structure"] = req.edited_structure
    if req.note:
        resume_value["note"] = req.note

    async def generate():
        yield StreamEvent(type="thread_id", data=json.dumps({"thread_id": req.thread_id})).model_dump_json()

        if lock.locked():
            logger.warning("Concurrent resume for thread %s — rejecting duplicate.", req.thread_id)
            yield StreamEvent(
                type="error",
                data="Poprzednia akcja HITL jest jeszcze w toku. Zaczekaj chwilę i spróbuj ponownie.",
            ).model_dump_json()
            return

        async with lock:
            finished_cleanly = False
            client_disconnected = False

            async for chunk in _stream_graph_events(graph, Command(resume=resume_value), config, request):
                if chunk.startswith(_META_PREFIX):
                    meta = json.loads(chunk.removeprefix(_META_PREFIX))
                    finished_cleanly = meta["finished_cleanly"]
                    client_disconnected = meta["client_disconnected"]
                else:
                    yield chunk

            if finished_cleanly and not client_disconnected:
                async for event_json in _emit_post_stream_events(graph, config, req.thread_id, request):
                    yield event_json

    return EventSourceResponse(generate(), headers=_SSE_HEADERS, ping=None)


@router.get("/history/{thread_id}")
async def get_chat_history(thread_id: str, request: Request, state_snapshot=None):
    """
    GET /api/chat/history/{thread_id}

    Returns session state from the SQLite checkpoint store (AsyncSqliteSaver).
    """
    config = {"configurable": {"thread_id": thread_id}}
    graph = request.app.state.graph

    if state_snapshot is None:
        state_snapshot = await graph.aget_state(config)

    if not state_snapshot or not hasattr(state_snapshot, "values") or not state_snapshot.values:
        return {
            "messages": [],
            "stage": "idle",
            "draft": "",
            "hitlPause": None,
            "stageStatus": {},
        }

    st = state_snapshot.values
    next_nodes = state_snapshot.next

    messages = []
    for msg in st.get("messages", []):
        if isinstance(msg, dict):
            messages.append(msg)
        else:
            role = "user" if msg.type == "human" else ("assistant" if msg.type == "ai" else str(msg.type))
            messages.append({"role": role, "content": msg.content})

    stage = "idle"
    hitl_pause = None

    if not next_nodes:
        if st.get("metadata_saved"):
            stage = "done"
        else:
            stage = "writing" if "draft" in st else "idle"
    else:
        stage_map = {
            "duplicate_check": "idle",
            "researcher": "research",
            "structure": "structure",
            "checkpoint_1": "structure",
            "writer": "writing",
            "checkpoint_2": "writing",
            "save_metadata": "done",
        }
        stage = stage_map.get(next_nodes[0], "idle")

    if hasattr(state_snapshot, "tasks"):
        for task in state_snapshot.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                for intr in task.interrupts:
                    val = getattr(intr, "value", intr)
                    if isinstance(val, dict):
                        hitl_pause = {
                            "checkpoint_id": val.get("checkpoint", task.name),
                            "type": val.get("type", "approve_reject"),
                        }
                        for k, v in val.items():
                            if k not in ("checkpoint", "type", "instructions"):
                                hitl_pause[k] = v
                        if task.name == "checkpoint_2" and "iterations_remaining" not in hitl_pause:
                            hitl_pause["iterations_remaining"] = 3 - st.get("cp2_iterations", 0)

    return {
        "messages": messages,
        "stage": stage,
        "draft": st.get("draft", ""),
        "hitlPause": hitl_pause,
        "stageStatus": {stage: "pending" if hitl_pause else "running"},
    }
