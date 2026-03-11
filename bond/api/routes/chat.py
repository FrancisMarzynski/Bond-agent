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
            {"messages": [{"role": "user", "content": req.message}], "mode": req.mode},
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

        try:
            while True:
                # Aktywne przerywanie pracy w przypadku rozłączenia
                if await request.is_disconnected():
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
            state_snapshot = await graph.aget_state(config)
            if state_snapshot.next:
                 # Mapowanie stanu do hitl_pause (używamy tej samej logiki co w /history)
                 history_state = await get_chat_history(thread_id, request)
                 # Wyślij aktualny stage przed hitl_pause, żeby klient zdążył odebrać go przed przerwaniem strumienia
                 if history_state.get("stage"):
                      yield f"data: {StreamEvent(type='stage', data=json.dumps({'stage': history_state['stage'], 'status': history_state['stageStatus'].get(history_state['stage'], 'running')})).model_dump_json()}\n\n"

                 if history_state.get("hitlPause"):
                      yield f"data: {StreamEvent(type='hitl_pause', data=json.dumps(history_state['hitlPause'])).model_dump_json()}\n\n"
            else:
                 # Jeśli nie ma następnych kroków i nie było błędu, wyślij 'done'
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

        try:
            while True:
                if await request.is_disconnected():
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
                    break
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
        finally:
            await gen.aclose()
            # Logika sprawdzania stanu po resume (analogiczna do /stream)
            state_snapshot = await graph.aget_state(config)
            history_state = await get_chat_history(req.thread_id, request)
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
async def get_chat_history(thread_id: str, request: Request):
    """
    Pobiera historię oraz aktualny stan z pliku SQLite (AsyncSqliteSaver) 
    dla podanej sesji (thread_id).
    """
    config = {"configurable": {"thread_id": thread_id}}
    graph = request.app.state.graph
    
    # Pobieramy najświeższy snapshot stanu z checkpointera LangGraph
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

    # Odtwarzamy historię komunikatów (messages) na podstawie dostępnych kluczy w stanie
    messages = []
    
    if "topic" in st:
        messages.append({"role": "user", "content": st["topic"]})
    
    if "research_report" in st and st["research_report"]:
        messages.append({"role": "assistant", "content": "Zebrałem informacje z sieci i przygotowałem raport."})
    
    if "heading_structure" in st and st["heading_structure"]:
        messages.append({"role": "assistant", "content": f"Oto proponowana struktura nagłówków:\n\n{st['heading_structure']}"})

    if "cp1_feedback" in st and st["cp1_feedback"]:
        messages.append({"role": "user", "content": st["cp1_feedback"]})
        
    if "draft" in st and st["draft"]:
        messages.append({"role": "assistant", "content": f"Przygotowałem projekt artykułu:\n\n{st['draft'][:500]}..."})

    if "cp2_feedback" in st and st["cp2_feedback"]:
        messages.append({"role": "user", "content": st["cp2_feedback"]})

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
        if next_node == "researcher":
            stage = "research"
        elif next_node == "structure":
            stage = "structure"
        elif next_node == "checkpoint_1":
            stage = "structure"
            # Odtworzenie stanu pauzy HITL
            if "heading_structure" in st:
                hitl_pause = {
                    "checkpoint_id": "checkpoint_1",
                    "type": "approve_reject",
                }
        elif next_node == "writer":
            stage = "writing"
        elif next_node == "checkpoint_2":
            stage = "writing"
            # Odtworzenie stanu pauzy HITL
            if "draft" in st:
                hitl_pause = {
                    "checkpoint_id": "checkpoint_2",
                    "type": "approve_reject",
                    "iterations_remaining": 3 - st.get("cp2_iterations", 0)
                }
        elif next_node == "save_metadata":
            stage = "done"

    return {
        "messages": messages,
        "stage": stage,
        "draft": st.get("draft", ""),
        "hitlPause": hitl_pause,
        "stageStatus": {
            stage: "pending" if hitl_pause else "running"
        }
    }

