import asyncio
import json
import logging
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator
from sse_starlette.sse import EventSourceResponse

from bond.api.runtime import ActiveRun, CommandRuntime
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

# LangGraph recursion limit — acts as safety backstop behind the per-node hard caps.
# Base path: ~7 nodes. cp1 loop: up to 10 * 2 = 20. cp2 loop: up to 10 * 2 = 20. Total ≤ 47.
_RECURSION_LIMIT = 50

# SSE response headers shared by all streaming endpoints.
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Content-Encoding": "identity",
}

_HEARTBEAT_INTERVAL_SECONDS = 5.0

# Maps pending_node → frontend stage label for GET /history and _emit_post_stream_events.
# Shadow stages aligned with bond/api/stream.py _STAGE_MAP.
_STAGE_MAP = {
    "duplicate_check": "idle",
    "researcher": "research",
    "structure": "structure",
    "checkpoint_1": "structure",
    "writer": "writing",
    "checkpoint_2": "writing",
    "save_metadata": "done",
    "shadow_analyze": "shadow_analysis",
    "shadow_annotate": "shadow_annotation",
    "shadow_checkpoint": "shadow_annotation",
}


def _build_hitl_pause_from_state(next_node: str, st: dict[str, Any]) -> dict[str, Any] | None:
    """Fallback HITL payload builder when LangGraph interrupts are absent in tasks."""
    if next_node == "duplicate_check" and st.get("duplicate_match"):
        match = st["duplicate_match"]
        return {
            "checkpoint_id": "duplicate_check",
            "type": "approve_reject",
            "warning": "Wykryto podobny temat",
            "existing_title": match.get("existing_title") or match.get("title"),
            "existing_date": match.get("existing_date") or match.get("date"),
            "similarity_score": match.get("similarity_score") or match.get("similarity"),
        }

    if next_node == "checkpoint_1":
        return {
            "checkpoint_id": "checkpoint_1",
            "type": "approve_reject",
            "research_report": st.get("research_report", ""),
            "heading_structure": st.get("heading_structure", ""),
            "cp1_iterations": st.get("cp1_iterations", 0),
        }

    if next_node == "checkpoint_2":
        return {
            "checkpoint_id": "checkpoint_2",
            "type": "approve_reject",
            "draft": st.get("draft", ""),
            "draft_validated": st.get("draft_validated", True),
            "cp2_iterations": st.get("cp2_iterations", 0),
            "iterations_remaining": 3 - st.get("cp2_iterations", 0),
        }

    if next_node == "shadow_checkpoint":
        return {
            "checkpoint_id": "shadow_checkpoint",
            "type": "approve_reject",
            "annotations": st.get("annotations", []) or [],
            "shadow_corrected_text": st.get("shadow_corrected_text", "") or "",
            "iteration_count": st.get("iteration_count", 0),
        }

    return None


def _build_hitl_pause_from_snapshot(state_snapshot) -> dict[str, Any] | None:
    """Extract HITL pause payload from a LangGraph state snapshot."""
    st = state_snapshot.values
    next_nodes = list(getattr(state_snapshot, "next", []) or [])
    pending_node = next_nodes[0] if next_nodes else None

    if not pending_node:
        return None

    hitl_pause = None

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
                        break
                if hitl_pause:
                    break

    if not hitl_pause:
        hitl_pause = _build_hitl_pause_from_state(pending_node, st)

    return hitl_pause


def _build_stage_status(stage: str, session_status: str) -> dict[str, str]:
    """Map explicit session status to the existing frontend stage-status contract."""
    if session_status == "paused":
        return {stage: "pending"}
    if session_status == "running":
        return {stage: "running"}
    if session_status == "completed":
        return {stage: "complete"}
    if session_status == "error":
        return {stage: "error"}
    return {}


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
        if len(v) > SHADOW_MAX_CHARS:
            raise ValueError(
                f"Tekst wejściowy jest zbyt długi ({len(v)} znaków). "
                f"Maksimum w trybie Cień: {SHADOW_MAX_CHARS} znaków."
            )
        return v


class ResumeRequest(BaseModel):
    thread_id: str
    action: str
    feedback: Optional[str] = None
    edited_structure: Optional[str] = None
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Post-stream state emission (no longer requires a Request object)
# ---------------------------------------------------------------------------

async def _emit_post_stream_events(graph, config: dict, state_snapshot=None):
    """
    Inspect the persisted checkpoint and yield terminal SSE events.

    Emitted after the graph stream exhausts without error:
    - If paused at HITL: stage + hitl_pause events.
    - If reached END: optional system_alert + shadow output + done.
    """
    if state_snapshot is None:
        state_snapshot = await graph.aget_state(config)

    if state_snapshot.next:
        next_node = state_snapshot.next[0]
        stage = _STAGE_MAP.get(next_node, "idle")
        yield StreamEvent(
            type="stage",
            data=json.dumps({"stage": stage, "status": "pending"}),
        ).model_dump_json()

        hitl_pause = _build_hitl_pause_from_snapshot(state_snapshot)
        if hitl_pause:
            yield StreamEvent(
                type="hitl_pause",
                data=json.dumps(hitl_pause),
            ).model_dump_json()
    else:
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
# Background graph producer
# ---------------------------------------------------------------------------

async def _run_graph_events(
    run: ActiveRun,
    graph,
    input_or_command,
    config: dict,
) -> None:
    """
    Background producer: drives graph.astream_events() and publishes SSE events
    to the ActiveRun queue. Graph execution is NOT cancelled if the SSE consumer
    disconnects — it continues until the next durable checkpoint or END.
    """
    events = graph.astream_events(input_or_command, config=config, version="v2")
    had_error = False

    try:
        async for json_str in parse_stream_events(events):
            run.publish(json_str)
    except GraphRecursionError:
        had_error = True
        run.publish(
            StreamEvent(
                type="error",
                data=(
                    "Osiągnięto limit iteracji pętli HITL. "
                    "Pipeline zatrzymany automatycznie po przekroczeniu maksymalnej liczby kroków."
                ),
            ).model_dump_json()
        )
    except Exception as exc:
        had_error = True
        logger.error("Model/graph error during streaming: %s", exc, exc_info=True)
        run.publish(StreamEvent(type="error", data=str(exc)).model_dump_json())

    if not had_error:
        async for event_json in _emit_post_stream_events(graph, config):
            run.publish(event_json)


# ---------------------------------------------------------------------------
# Shared SSE consumer generator
# ---------------------------------------------------------------------------

async def _consume_run(run: ActiveRun, request: Request):
    """
    Async generator that reads events from the ActiveRun queue and yields them
    as SSE strings. Polls for client disconnect and sends heartbeats.

    Calls run.detach_subscriber() in its finally block so the background
    producer keeps running after the response closes.
    """
    last_heartbeat = asyncio.get_event_loop().time()
    try:
        while True:
            is_done, event = await run.consume_next(timeout=0.5)

            if is_done:
                break

            if event is None:
                if await request.is_disconnected():
                    break
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat > _HEARTBEAT_INTERVAL_SECONDS:
                    yield StreamEvent(type="heartbeat", data="ping").model_dump_json()
                    last_heartbeat = now
                continue

            last_heartbeat = asyncio.get_event_loop().time()
            yield event

    finally:
        run.detach_subscriber()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """
    POST /api/chat/stream

    Starts a new agent pipeline run and streams events back as SSE.
    Graph execution is owned by a background task independent of the SSE
    response lifetime. A client disconnect detaches the consumer but does not
    cancel the graph — the session remains recoverable via /history.

    Response header ``X-Bond-Thread-Id`` carries the thread ID so that same-tab
    recovery works even when the body drops before the first thread_id SSE event.
    """
    thread_id = req.thread_id or str(uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": _RECURSION_LIMIT,
    }
    graph = request.app.state.graph
    runtime: CommandRuntime = request.app.state.runtime

    initial_state: dict = {
        "topic": req.message,
        "keywords": [],
        "messages": [{"role": "user", "content": req.message}],
        "mode": req.mode,
        "thread_id": thread_id,
    }
    if req.mode == "shadow":
        initial_state["original_text"] = req.message

    async def producer(run: ActiveRun) -> None:
        run.publish(
            StreamEvent(type="thread_id", data=json.dumps({"thread_id": thread_id})).model_dump_json()
        )
        await _run_graph_events(run, graph, initial_state, config)

    run = await runtime.start_run(thread_id, "stream", producer)

    headers = dict(_SSE_HEADERS)
    headers["X-Bond-Thread-Id"] = thread_id

    return EventSourceResponse(_consume_run(run, request), headers=headers, ping=None)


@router.post("/resume")
async def chat_resume(req: ResumeRequest, request: Request):
    """
    POST /api/chat/resume

    Resumes the agent pipeline after a HITL checkpoint pause.

    The per-thread asyncio.Lock is acquired HERE (in the route handler, before the
    background task starts) so any concurrent resume request sees it as locked
    immediately, not just after the SSE generator starts consuming. The lock is
    released inside the producer's finally block when the graph reaches the next
    durable state — not when the SSE response closes.
    """
    config = {
        "configurable": {"thread_id": req.thread_id},
        "recursion_limit": _RECURSION_LIMIT,
    }
    graph = request.app.state.graph
    runtime: CommandRuntime = request.app.state.runtime
    lock = _get_resume_lock(req.thread_id)

    resume_value: dict[str, Any] = {"action": req.action}
    if req.feedback:
        resume_value["feedback"] = req.feedback
    if req.edited_structure:
        resume_value["edited_structure"] = req.edited_structure
    if req.note:
        resume_value["note"] = req.note

    if lock.locked():
        logger.warning("Concurrent resume for thread %s — rejecting duplicate.", req.thread_id)

        async def _reject():
            yield StreamEvent(
                type="thread_id",
                data=json.dumps({"thread_id": req.thread_id}),
            ).model_dump_json()
            yield StreamEvent(
                type="error",
                data="Poprzednia akcja HITL jest jeszcze w toku. Zaczekaj chwilę i spróbuj ponownie.",
            ).model_dump_json()

        return EventSourceResponse(_reject(), headers=_SSE_HEADERS, ping=None)

    # Acquire the lock BEFORE starting the task so no concurrent request
    # can sneak through between the locked() check and the task's first await.
    await lock.acquire()

    async def producer(run: ActiveRun) -> None:
        try:
            run.publish(
                StreamEvent(
                    type="thread_id",
                    data=json.dumps({"thread_id": req.thread_id}),
                ).model_dump_json()
            )
            await _run_graph_events(run, graph, Command(resume=resume_value), config)
        finally:
            # Release the lock only when the graph has reached a durable state,
            # not when the SSE consumer disconnects.
            lock.release()

    run = await runtime.start_run(req.thread_id, "resume", producer)

    headers = dict(_SSE_HEADERS)
    headers["X-Bond-Thread-Id"] = req.thread_id

    return EventSourceResponse(_consume_run(run, request), headers=headers, ping=None)


@router.get("/history/{thread_id}")
async def get_chat_history(thread_id: str, request: Request, state_snapshot=None):
    """
    GET /api/chat/history/{thread_id}

    Returns session state from the SQLite checkpoint store (AsyncSqliteSaver),
    overlaid with live runtime metadata when a background task is still running.
    """
    config = {"configurable": {"thread_id": thread_id}}
    graph = request.app.state.graph
    runtime: Optional[CommandRuntime] = getattr(request.app.state, "runtime", None)

    if state_snapshot is None:
        state_snapshot = await graph.aget_state(config)

    if not state_snapshot or not hasattr(state_snapshot, "values") or not state_snapshot.values:
        return {
            "messages": [],
            "stage": "idle",
            "draft": "",
            "hitlPause": None,
            "stageStatus": {},
            "session_status": "idle",
            "pending_node": None,
            "can_resume": False,
            "originalText": "",
            "annotations": [],
            "shadowCorrectedText": "",
            "active_command": None,
            "error_message": None,
        }

    st = state_snapshot.values
    next_nodes = list(getattr(state_snapshot, "next", []) or [])
    pending_node = next_nodes[0] if next_nodes else None

    messages = []
    for msg in st.get("messages", []):
        if isinstance(msg, dict):
            messages.append(msg)
        else:
            role = "user" if msg.type == "human" else ("assistant" if msg.type == "ai" else str(msg.type))
            messages.append({"role": role, "content": msg.content})

    stage = "idle"
    hitl_pause = None
    draft_value = st.get("draft") or st.get("shadow_corrected_text", "") or ""

    if pending_node:
        stage = _STAGE_MAP.get(pending_node, "idle")
    elif (
        st.get("metadata_saved")
        or st.get("shadow_corrected_text")
        or st.get("annotations")
    ):
        stage = "done"
    elif st.get("draft"):
        stage = "writing"

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
                        break
                if hitl_pause:
                    break

    if not hitl_pause and pending_node:
        hitl_pause = _build_hitl_pause_from_state(pending_node, st)

    if hitl_pause:
        session_status = "paused"
    elif pending_node:
        session_status = "running"
    else:
        session_status = "completed"

    # Runtime overlay — merge live execution state if a background task is still running.
    active_command: Optional[str] = None
    error_message: Optional[str] = None

    run = runtime.get_run(thread_id) if runtime else None
    if run is not None:
        if run.task and not run.task.done():
            active_command = run.active_command
            # A still-running task means the graph hasn't committed a new checkpoint
            # yet. Override session_status only when the checkpoint says "completed"
            # (which would be a stale read from a previous run).
            if session_status == "completed" and not run.finished_cleanly:
                session_status = "running"
        elif run.terminal_error and not pending_node:
            error_message = run.terminal_error
            session_status = "error"

    return {
        "messages": messages,
        "stage": stage,
        "draft": draft_value,
        "hitlPause": hitl_pause,
        "stageStatus": _build_stage_status(stage, session_status),
        "session_status": session_status,
        "pending_node": pending_node,
        "can_resume": session_status == "paused" and hitl_pause is not None,
        "originalText": st.get("original_text", "") or "",
        "annotations": st.get("annotations", []) or [],
        "shadowCorrectedText": st.get("shadow_corrected_text", "") or "",
        "active_command": active_command,
        "error_message": error_message,
    }
