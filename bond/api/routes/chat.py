import asyncio
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from bond.api.stream import parse_stream_events


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
                except asyncio.TimeoutError:
                    # Brak zdarzeń w ciągu minionej sekundy, pętla sprawdzi znow is_disconnected()
                    continue
                except StopAsyncIteration:
                    # Koniec strumienia
                    break
        
        except asyncio.CancelledError:
            # Upewniamy się, że przy ustrzeleniu przez serwer uvicorn również wychodzimy płynnie
            pass
        except Exception as e:
            import json
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
