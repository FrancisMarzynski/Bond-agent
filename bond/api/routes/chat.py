import asyncio
import json
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from bond.api.stream import parse_stream_events
from bond.schemas import StreamEvent
from langgraph.types import Command


router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    mode: str = "author"


class ResumeRequest(BaseModel):
    thread_id: str
    action: str
    feedback: Optional[str] = None
    edited_structure: Optional[str] = None
    note: Optional[str] = None


@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """
    Endpoint obsługujący przesyłanie zdarzeń strumieniowych do klienta.
    """
    thread_id = req.thread_id or str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    graph = request.app.state.graph

    async def generate():
        # Uruchomienie strumieniowania (wersja v2)
        events = graph.astream_events(
            {
                "topic": req.message, 
                "keywords": [],
                "messages": [{"role": "user", "content": req.message}], 
                "mode": req.mode
            },
            config=config,
            version="v2",
        )
        
        # Poinformuj frontend o thread_id na samym początku
        yield f"data: {StreamEvent(type='thread_id', data=json.dumps({'thread_id': thread_id})).model_dump_json()}\n\n"
        
        # Generator w formacie SSE
        async def formatted_events():
            async for json_str in parse_stream_events(events):
                yield f"data: {json_str}\n\n"

        gen = formatted_events()
        last_heartbeat = asyncio.get_event_loop().time()
        client_disconnected = False
        finished_cleanly = False

        try:
            while True:
                # Aktywne przerywanie pracy w przypadku rozłączenia
                if await request.is_disconnected():
                    client_disconnected = True
                    break
                
                try:
                    # Oczekujemy na kolejny event z timeoutem, by regularnie sprawdzać is_disconnected()
                    # Pozwala to przerwać długo trwające requesty LLM w LangGraph
                    chunk = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
                    yield chunk
                    last_heartbeat = asyncio.get_event_loop().time()
                except asyncio.TimeoutError:
                    # Brak zdarzeń w ciągu minionej sekundy, pętla sprawdzi znow is_disconnected()
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_heartbeat > 15.0:
                        yield f"data: {StreamEvent(type='heartbeat', data='ping').model_dump_json()}\n\n"
                        last_heartbeat = current_time
                    continue
                except StopAsyncIteration:
                    # Koniec strumienia
                    finished_cleanly = True
                    break
        
        except asyncio.CancelledError:
            # Upewniamy się, że przy ustrzeleniu przez serwer uvicorn również wychodzimy płynnie
            pass
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
        finally:
            # Wymuszenie zwolnienia zasobów i przymusowe przerwanie aktywnego agenta
            await gen.aclose()

        # Po zakończeniu strumienia, sprawdź czy graf nie zatrzymał się na checkpointcie
        # Wysyłamy zdarzenia TYLKO jeśli klient nadal tam jest
        if finished_cleanly and not client_disconnected:
            state_snapshot = await graph.aget_state(config)
            if state_snapshot.next:
                 # Mapowanie stanu do hitl_pause (używamy tej samej logiki co w /history)
                 history_state = await get_chat_history(thread_id, request, state_snapshot=state_snapshot)
                 # Wyślij aktualny stage przed hitl_pause, żeby klient zdążył odebrać go przed przerwaniem strumienia
                 if history_state.get("stage"):
                      yield f"data: {StreamEvent(type='stage', data=json.dumps({'stage': history_state['stage'], 'status': history_state['stageStatus'].get(history_state['stage'], 'running')})).model_dump_json()}\n\n"

                 if history_state.get("hitlPause"):
                      yield f"data: {StreamEvent(type='hitl_pause', data=json.dumps(history_state['hitlPause'])).model_dump_json()}\n\n"
            else:
                 # Shadow mode: emit corrected text and annotations before done
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
    """
    config = {"configurable": {"thread_id": req.thread_id}}
    graph = request.app.state.graph

    # Przygotowanie wartości do wznowienia (Command(resume=...))
    resume_value = {"action": req.action}
    if req.feedback:
        resume_value["feedback"] = req.feedback
    if req.edited_structure:
        resume_value["edited_structure"] = req.edited_structure
    if req.note:
        resume_value["note"] = req.note

    async def generate():
        # Informacja o thread_id (spójność z /stream)
        yield f"data: {StreamEvent(type='thread_id', data=json.dumps({'thread_id': req.thread_id})).model_dump_json()}\n\n"

        events = graph.astream_events(
            Command(resume=resume_value),
            config=config,
            version="v2",
        )
        
        async def formatted_events():
            async for json_str in parse_stream_events(events):
                yield f"data: {json_str}\n\n"

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
            
        if finished_cleanly and not client_disconnected:
            # Logika sprawdzania stanu po resume (analogiczna do /stream)
            state_snapshot = await graph.aget_state(config)
            history_state = await get_chat_history(req.thread_id, request, state_snapshot=state_snapshot)
            if state_snapshot.next:
                 if history_state.get("stage"):
                      yield f"data: {StreamEvent(type='stage', data=json.dumps({'stage': history_state['stage'], 'status': history_state['stageStatus'].get(history_state['stage'], 'running')})).model_dump_json()}\n\n"
                 if history_state.get("hitlPause"):
                      yield f"data: {StreamEvent(type='hitl_pause', data=json.dumps(history_state['hitlPause'])).model_dump_json()}\n\n"
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
    
    # Pobieramy najświeższy snapshot stanu z checkpointera LangGraph jeśli nie podano
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

    # Odtwarzamy historię komunikatów (messages)
    messages = []
    
    raw_messages = st.get("messages", [])
    for msg in raw_messages:
        # LangGraph messages might be dictionaries or LangChain Message objects
        if isinstance(msg, dict):
            messages.append(msg)
        else:
            role = "user" if msg.type == "human" else ("assistant" if msg.type == "ai" else str(msg.type))
            messages.append({"role": role, "content": msg.content})

    # Odtwarzanie obecnego etapu (stage) na podstawie następnych kroków zapisanych w checkpointerze
    stage = "idle"
    hitl_pause = None
    
    if not next_nodes:
        if st.get("metadata_saved"):
            stage = "done"
        else:
            stage = "writing" if "draft" in st else "idle"
    else:
        next_node = next_nodes[0]
        if next_node == "duplicate_check":
            stage = "idle"
        elif next_node == "researcher":
            stage = "research"
        elif next_node == "structure":
            stage = "structure"
        elif next_node == "checkpoint_1":
            stage = "structure"
        elif next_node == "writer":
            stage = "writing"
        elif next_node == "checkpoint_2":
            stage = "writing"
        elif next_node == "save_metadata":
            stage = "done"

    # Wyciąganie payloadu przerwania (interrupt) z zadań w LangGraph
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
                        
                        # Fallback dla iteracji w checkpoint_2
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

