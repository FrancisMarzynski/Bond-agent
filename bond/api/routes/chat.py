import asyncio
import json
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from bond.api.stream import parse_stream_events
from bond.schemas import StreamEvent


router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    mode: str = "author"


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
        messages.append({"role": "assistant", "content": "Zebrałem informacje z sieci i przygotowałem raport. Przechodzę do struktury."})
    
    if "cp1_feedback" in st and st["cp1_feedback"]:
        messages.append({"role": "user", "content": st["cp1_feedback"]})
        
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

