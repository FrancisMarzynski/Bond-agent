import asyncio
import json
import logging
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

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


def _get_resume_lock(thread_id: str) -> asyncio.Lock:
    """Return (and lazily create) a per-thread asyncio.Lock."""
    if thread_id not in _resume_locks:
        _resume_locks[thread_id] = asyncio.Lock()
    return _resume_locks[thread_id]


# LangGraph recursion limit — acts as safety backstop behind the per-node hard caps.
# Base path: ~7 nodes. cp1 loop: up to 10 * 2 = 20. cp2 loop: up to 10 * 2 = 20. Total ≤ 47.
_RECURSION_LIMIT = 50


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    mode: str = "author"

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, v: str, info) -> str:
        # Pydantic v2 passes a FieldValidationInfo; mode is not available here,
        # so we apply the stricter shadow limit universally and let the endpoint
        # enforce mode-specific feedback.
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
# Shared SSE streaming helper
# ---------------------------------------------------------------------------

async def _stream_graph_events(graph, input_or_command, config: dict, request: Request):
    """
    Async generator that:
    - Runs graph.astream_events with recursion_limit guard
    - Emits heartbeat every 15 s to keep proxies alive
    - Detects client disconnect and stops cleanly
    - Catches GraphRecursionError and emits a structured SSE error event
    Returns (finished_cleanly: bool, client_disconnected: bool).
    """
    events = graph.astream_events(
        input_or_command,
        config=config,
        version="v2",
    )

    async def formatted_events():
        try:
            async for json_str in parse_stream_events(events):
                yield f"data: {json_str}\n\n"
        except GraphRecursionError:
            error_msg = (
                "Osiągnięto limit iteracji pętli HITL. "
                "Pipeline zatrzymany automatycznie po przekroczeniu maksymalnej liczby kroków."
            )
            yield f"data: {json.dumps({'type': 'error', 'data': error_msg})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'data': str(exc)})}\n\n"

    gen = formatted_events()
    last_heartbeat = asyncio.get_event_loop().time()
    client_disconnected = False
    finished_cleanly = False

    try:
        while True:
            if await request.is_disconnected():
                client_disconnected = True
                break
            try:
                chunk = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
                yield chunk
                last_heartbeat = asyncio.get_event_loop().time()
            except asyncio.TimeoutError:
                current_time = asyncio.get_event_loop().time()
                if current_time - last_heartbeat > 15.0:
                    yield f"data: {StreamEvent(type='heartbeat', data='ping').model_dump_json()}\n\n"
                    last_heartbeat = current_time
                continue
            except StopAsyncIteration:
                finished_cleanly = True
                break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
    finally:
        await gen.aclose()

    # Yield a sentinel so callers can detect stream completion state
    sentinel = "__META__:" + json.dumps({"finished_cleanly": finished_cleanly, "client_disconnected": client_disconnected})
    yield sentinel


@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """
    Endpoint obsługujący przesyłanie zdarzeń strumieniowych do klienta.
    """
    thread_id = req.thread_id or str(uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": _RECURSION_LIMIT,
    }
    graph = request.app.state.graph

    # Build initial state — set original_text for shadow mode
    initial_state: dict = {
        "topic": req.message,
        "keywords": [],
        "messages": [{"role": "user", "content": req.message}],
        "mode": req.mode,
    }
    if req.mode == "shadow":
        initial_state["original_text"] = req.message

    async def generate():
        yield f"data: {StreamEvent(type='thread_id', data=json.dumps({'thread_id': thread_id})).model_dump_json()}\n\n"

        finished_cleanly = False
        client_disconnected = False

        async for chunk in _stream_graph_events(graph, initial_state, config, request):
            if chunk.startswith("__META__:"):
                meta = json.loads(chunk[len("__META__:"):])
                finished_cleanly = meta["finished_cleanly"]
                client_disconnected = meta["client_disconnected"]
            else:
                yield chunk

        if finished_cleanly and not client_disconnected:
            state_snapshot = await graph.aget_state(config)
            if state_snapshot.next:
                history_state = await get_chat_history(thread_id, request, state_snapshot=state_snapshot)
                if history_state.get("stage"):
                    yield (
                        f"data: {StreamEvent(type='stage', data=json.dumps({'stage': history_state['stage'], 'status': history_state['stageStatus'].get(history_state['stage'], 'running')})).model_dump_json()}\n\n"
                    )
                if history_state.get("hitlPause"):
                    yield (
                        f"data: {StreamEvent(type='hitl_pause', data=json.dumps(history_state['hitlPause'])).model_dump_json()}\n\n"
                    )
            else:
                st_values = state_snapshot.values
                shadow_corrected = st_values.get("shadow_corrected_text") or ""
                annotations = st_values.get("annotations") or []
                if shadow_corrected:
                    yield f"data: {StreamEvent(type='shadow_corrected_text', data=json.dumps({'text': shadow_corrected})).model_dump_json()}\n\n"
                if annotations:
                    yield f"data: {StreamEvent(type='annotations', data=json.dumps(annotations)).model_dump_json()}\n\n"
                yield f"data: {StreamEvent(type='done', data='done').model_dump_json()}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "none",
        },
    )


@router.post("/resume")
async def chat_resume(req: ResumeRequest, request: Request):
    """
    Endpoint do wznawiania pracy agenta po przerwie HITL.

    Per-thread asyncio.Lock prevents race conditions when the user rapidly
    clicks "Reject" — only one resume request per thread_id can execute at once.
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
        yield f"data: {StreamEvent(type='thread_id', data=json.dumps({'thread_id': req.thread_id})).model_dump_json()}\n\n"

        # Acquire lock — reject concurrent resume for same thread
        if lock.locked():
            logger.warning("Concurrent resume request for thread %s — blocking duplicate.", req.thread_id)
            error_msg = "Poprzednia akcja HITL jest jeszcze w toku. Zaczekaj chwilę i spróbuj ponownie."
            yield f"data: {json.dumps({'type': 'error', 'data': error_msg})}\n\n"
            return

        async with lock:
            finished_cleanly = False
            client_disconnected = False

            async for chunk in _stream_graph_events(
                graph, Command(resume=resume_value), config, request
            ):
                if chunk.startswith("__META__:"):
                    meta = json.loads(chunk.removeprefix("__META__:"))
                    finished_cleanly = meta["finished_cleanly"]
                    client_disconnected = meta["client_disconnected"]
                else:
                    yield chunk

            if finished_cleanly and not client_disconnected:
                state_snapshot = await graph.aget_state(config)
                history_state = await get_chat_history(req.thread_id, request, state_snapshot=state_snapshot)
                if state_snapshot.next:
                    if history_state.get("stage"):
                        yield (
                            f"data: {StreamEvent(type='stage', data=json.dumps({'stage': history_state['stage'], 'status': history_state['stageStatus'].get(history_state['stage'], 'running')})).model_dump_json()}\n\n"
                        )
                    if history_state.get("hitlPause"):
                        yield (
                            f"data: {StreamEvent(type='hitl_pause', data=json.dumps(history_state['hitlPause'])).model_dump_json()}\n\n"
                        )
                else:
                    yield f"data: {StreamEvent(type='done', data='done').model_dump_json()}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "none",
        },
    )


@router.get("/history/{thread_id}")
async def get_chat_history(thread_id: str, request: Request, state_snapshot=None):
    """
    Pobiera historię oraz aktualny stan z pliku SQLite (AsyncSqliteSaver)
    dla podanej sesji (thread_id).
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
            "stageStatus": {}
        }

    st = state_snapshot.values
    next_nodes = state_snapshot.next

    messages = []
    raw_messages = st.get("messages", [])
    for msg in raw_messages:
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
        next_node = next_nodes[0]
        stage_map = {
            "duplicate_check": "idle",
            "researcher": "research",
            "structure": "structure",
            "checkpoint_1": "structure",
            "writer": "writing",
            "checkpoint_2": "writing",
            "save_metadata": "done",
        }
        stage = stage_map.get(next_node, "idle")

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
                            if k not in ["checkpoint", "type", "instructions"]:
                                hitl_pause[k] = v

                        if task.name == "checkpoint_2" and "iterations_remaining" not in hitl_pause:
                            hitl_pause["iterations_remaining"] = 3 - st.get("cp2_iterations", 0)

    return {
        "messages": messages,
        "stage": stage,
        "draft": st.get("draft", ""),
        "hitlPause": hitl_pause,
        "stageStatus": {
            stage: "pending" if hitl_pause else "running"
        }
    }
