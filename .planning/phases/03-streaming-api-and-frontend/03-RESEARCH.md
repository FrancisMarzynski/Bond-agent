# Phase 3: Streaming API and Frontend - Research

**Researched:** 2026-02-21
**Domain:** FastAPI SSE streaming, LangGraph HITL resume, Next.js 15 App Router, React markdown editor
**Confidence:** HIGH (core stack verified via official docs and Context7), MEDIUM (some edge-case patterns)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Layout & content structure**
- Draft appears in a dedicated editor pane — separate from the chat, with its own scroll
- Author / Shadow mode toggle is a toggle switch in the header/nav — always visible, not dominant
- Session history appears in a left sidebar — users can revisit past drafts and resume incomplete sessions

**Streaming & progress UX**
- Research stage: a stage indicator shows while research runs; full result appears at once when done (no word-by-word streaming for research)
- Writing stage: tokens stream directly into the editor pane as they arrive — the draft builds up live in the editor
- Stage progression (Research → Structure → Writing) communicated via a stepper / progress bar at the top showing the current stage
- Errors during long operations: error message appears in the chat with a retry button

**Checkpoint interaction**
- Reject feedback flow: chat-style — Reject action triggers an agent message asking what to change, focus moves to the normal chat input for the user's reply
- Iteration limit display: remaining attempts counter is shown near the Reject button at Checkpoint 2 (e.g. "2 of 3 attempts remaining")
- Approve/Reject button placement and post-checkpoint transitions: Claude's discretion

**Corpus management**
- Ingestion form presents all 4 input types as stacked form sections: paste text, file upload, Google Drive folder, blog URL — each as a distinct card/section on the page
- Ingestion progress: inline feedback within the submitted section (spinner → success/error state)
- Where corpus management lives in the app and how corpus status is surfaced: Claude's discretion

### Claude's Discretion
- Overall spatial layout (how chat column and editor pane relate)
- Approve/Reject button placement at checkpoints
- Post-checkpoint visual transitions (what happens after user approves)
- Corpus management page/route location
- How corpus status (article count, low-corpus warning) is surfaced in the main UI

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| UI-01 | Interfejs zawiera wyraźny przełącznik trybu Author / Shadow widoczny w głównym widoku czatu | shadcn/ui `Switch` + header layout; locked as nav toggle |
| UI-02 | Interfejs zawiera progress indicator podczas długich operacji z etapami: research → struktura → pisanie | Custom stepper component using shadcn/ui `Progress` + custom stage state; stage events dispatched via LangGraph `stream_mode="updates"` |
| UI-03 | Użytkownik widzi wygenerowany content w edytorze Markdown z podglądem | `@uiw/react-md-editor` controlled component; tokens appended via `useState` + SSE stream |
| UI-04 | Użytkownik może zatwierdzić lub odrzucić output na każdym checkpoint (przyciski Zatwierdź / Odrzuć) | HITL: LangGraph `interrupt()` + `Command(resume=...)` via `/api/chat/resume` POST; buttons rendered when SSE emits `hitl_pause` event |
| UI-05 | Przy odrzuceniu, użytkownik może wpisać feedback tekstowy dla agenta | Chat-style reject flow: Reject button → agent message → focus to chat input → POST to resume endpoint with feedback |
| UI-06 | Przycisk "Zatwierdź i Zapisz" zapisuje metadane do Metadata Log i oznacza temat jako użyty | Resume endpoint passes `{"action": "approve_save"}` → LangGraph node calls `save_metadata` (already in Phase 2) |
| UI-07 | Interfejs reaguje na zdarzenia strumieniowe — tokeny LLM są wyświetlane progressywnie (nie czeka na cały output) | `stream_mode="messages-tuple"` in LangGraph → FastAPI `StreamingResponse` → fetch + `ReadableStream` in Next.js client |
| UI-08 | Użytkownik ma dostęp do sekcji zarządzania corpus (dodawanie artykułów, widok statusu) | `/corpus` route; FastAPI `UploadFile` + `Form()` multipart endpoints; status from Phase 1 GET endpoints |
</phase_requirements>

---

## Summary

Phase 3 adds a streaming HTTP layer over the LangGraph backend (built in Phases 1–2) and a Next.js 15 browser UI. The core technical challenge is threefold: (1) bridging LangGraph's async streaming to browser-consumable Server-Sent Events through FastAPI, (2) surfacing HITL checkpoints as interactive UI events, and (3) progressively building the draft in a Markdown editor as tokens arrive.

The recommended architecture is a **direct browser-to-FastAPI SSE connection** — the Next.js frontend fetches `/api/chat/stream` on the FastAPI server directly (CORS-enabled) rather than proxying through Next.js Route Handlers. This avoids the well-documented Next.js SSE buffering pitfall where `StreamingResponse` is held until handler completion. The LangGraph backend uses `stream_mode="messages-tuple"` (or `"updates"` for node transitions) together with custom events dispatched via `adispatch_custom_event` to emit structured progress events that the frontend deserializes into stage indicators and checkpoint prompts.

For HITL, LangGraph's native `interrupt()` / `Command(resume=...)` mechanism paired with `AsyncSqliteSaver` enables reliable pause-and-resume across browser page refreshes. The `thread_id` (UUID generated at session start) is stored in `sessionStorage` on the client, and the frontend passes it on every request. The editor pane uses `@uiw/react-md-editor` in controlled mode, with tokens appended to the `value` state on each SSE message event.

**Primary recommendation:** Use `stream_mode="messages-tuple"` with custom progress events from FastAPI → direct SSE to browser (bypassing Next.js route handler buffering); store thread_id in sessionStorage; use `@uiw/react-md-editor` for the draft pane.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | ≥0.115 | HTTP server, SSE endpoints, file upload | Industry standard for Python async APIs; `StreamingResponse` built-in |
| uvicorn | ≥0.34 | ASGI server | FastAPI's recommended production server |
| langgraph | ≥0.3 | Graph execution and streaming | Phase 2 decision; `stream_mode` and `interrupt()` APIs needed |
| langgraph-checkpoint-sqlite | 3.0.3 | Async SQLite persistence for HITL resume | Phase 2 decision (`AsyncSqliteSaver`); import: `from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver` |
| Next.js | 15.x | Frontend framework | App Router, TypeScript, RSC support |
| React | 19.x | UI library | Ships with Next.js 15 |
| TypeScript | 5.x | Type safety | Standard for Next.js projects |
| Tailwind CSS | 4.x | Utility CSS | shadcn/ui now targets v4; CSS-first config (no `tailwind.config.js`) |
| shadcn/ui | latest | Component library | Components copied into `/components/ui`; fully Tailwind v4 compatible |
| @uiw/react-md-editor | ≥3.20 | Markdown editor + preview | Controlled component; textarea-based (no CodeMirror/Monaco); ~4.6 kB gzipped; GFM; TypeScript |
| zustand | ≥5.x | Frontend state management | Lightweight; SSR-safe; natural fit for streaming message accumulation in Next.js |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-multipart | ≥0.0.12 | FastAPI file uploads (required by `UploadFile`) | Corpus ingestion form (file, PDF, DOCX) |
| eventsource-parser | ≥3.x | SSE stream parsing in browser | If proxying SSE through Next.js Route Handler (not recommended for this project) |
| uuid (Python stdlib) | N/A | Generate `thread_id` | On session creation in FastAPI |
| lucide-react | latest | Icon set for shadcn/ui | Progress stepper, mode toggle icons |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `@uiw/react-md-editor` | MDXEditor | MDXEditor is WYSIWYG/Lexical — heavier, better UX but overkill for token streaming use case where raw markdown display suffices |
| `@uiw/react-md-editor` | `react-markdown` + textarea | `react-markdown` is render-only; would require custom split-pane editor — hand-rolling what react-md-editor provides |
| Zustand | TanStack Query `streamedQuery` | TanStack's `streamedQuery` is experimental; Zustand's direct state mutation is simpler for SSE accumulation |
| Direct browser→FastAPI SSE | Next.js Route Handler proxy | Proxy introduces buffering bug (Next.js waits for handler completion before sending response); direct is safer |
| SSE | WebSockets | Next.js App Router Route Handlers don't support WebSocket servers; SSE is unidirectional server→client which matches LLM streaming exactly |

**Installation:**
```bash
# FastAPI backend
pip install fastapi uvicorn python-multipart "langgraph>=0.3" langgraph-checkpoint-sqlite

# Next.js frontend
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"
npx shadcn@latest init
npx shadcn@latest add button card switch progress separator input textarea badge
npm install @uiw/react-md-editor zustand lucide-react
```

---

## Architecture Patterns

### Recommended Project Structure

```
Bond-agent/
├── backend/
│   ├── main.py                  # FastAPI app, lifespan, CORS
│   ├── api/
│   │   ├── chat.py              # /api/chat/stream, /api/chat/resume
│   │   └── corpus.py            # /api/corpus/ingest, /api/corpus/status
│   ├── graph/                   # Phase 2 LangGraph (unchanged)
│   │   ├── graph.py
│   │   ├── nodes/
│   │   └── state.py
│   └── checkpointer.py          # AsyncSqliteSaver init helper
└── frontend/
    ├── src/
    │   ├── app/
    │   │   ├── layout.tsx        # Root layout, sidebar
    │   │   ├── page.tsx          # Main chat + editor view
    │   │   └── corpus/
    │   │       └── page.tsx      # Corpus management
    │   ├── components/
    │   │   ├── ChatInterface.tsx
    │   │   ├── ModeToggle.tsx
    │   │   ├── StageProgress.tsx
    │   │   ├── EditorPane.tsx    # @uiw/react-md-editor wrapper
    │   │   ├── CheckpointPanel.tsx
    │   │   └── corpus/
    │   │       ├── CorpusStatus.tsx
    │   │       └── IngestionForm.tsx
    │   ├── hooks/
    │   │   ├── useStream.ts      # SSE connection logic
    │   │   └── useSession.ts     # sessionStorage thread_id
    │   └── store/
    │       └── chatStore.ts      # Zustand: messages, stage, hitl state
```

### Pattern 1: FastAPI + AsyncSqliteSaver Lifespan Init

**What:** The `AsyncSqliteSaver` context manager must be held open for the app's lifetime. Use FastAPI's `lifespan` parameter to init the checkpointer and compile the graph once at startup, storing both on `app.state`.

**When to use:** Any FastAPI app using LangGraph with `AsyncSqliteSaver`.

**Example:**
```python
# Source: langgraph-checkpoint-sqlite PyPI docs + FastAPI lifespan docs
from contextlib import asynccontextmanager
from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from graph.graph import build_graph  # Phase 2 graph builder

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
        await checkpointer.setup()
        app.state.graph = build_graph(checkpointer)
        yield
    # checkpointer closed on exit

app = FastAPI(lifespan=lifespan)
```

### Pattern 2: LangGraph SSE Streaming Endpoint

**What:** POST `/api/chat/stream` accepts `{message, thread_id, mode}`, creates a new UUID if no `thread_id` provided, runs the graph with `stream_mode="messages-tuple"` plus custom events, yields SSE.

**When to use:** Main chat initiation endpoint.

**Example:**
```python
# Source: LangGraph streaming docs + deepwiki.com/langchain-ai/langgraph-fullstack-python
import json, uuid
from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    mode: str = "author"

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    thread_id = req.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    async def generate():
        # Emit thread_id first so client can persist it
        yield f"event: thread_id\ndata: {json.dumps({'thread_id': thread_id})}\n\n"

        async for chunk, metadata in request.app.state.graph.astream(
            {"messages": [{"role": "user", "content": req.message}], "mode": req.mode},
            config=config,
            stream_mode="messages-tuple",
        ):
            if hasattr(chunk, "content") and chunk.content:
                yield f"event: token\ndata: {json.dumps({'token': chunk.content})}\n\n"
            # node transitions come as updates — handled via custom events below

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # CRITICAL: disables nginx buffering
        }
    )
```

### Pattern 3: LangGraph Custom Progress Events

**What:** Graph nodes emit stage transitions (research_start, structure_complete, etc.) using `adispatch_custom_event`. These appear as `on_custom_event` in `astream_events` but can also be yielded from a custom stream mode. Simpler approach: use `stream_mode="updates"` alongside `stream_mode="messages-tuple"` (pass as list) to detect node transitions.

**When to use:** Stepper progress (Research → Structure → Writing stages in the locked UX decision).

**Example:**
```python
# Source: LangChain custom events announcement + LangGraph streaming docs
# In a graph node:
from langchain_core.callbacks import adispatch_custom_event

async def research_node(state):
    await adispatch_custom_event("stage_change", {"stage": "research", "status": "running"})
    # ... do research ...
    await adispatch_custom_event("stage_change", {"stage": "research", "status": "complete"})
    return state

# In FastAPI, filter via astream_events:
async for event in graph.astream_events(input, config=config, version="v2"):
    if event["event"] == "on_custom_event" and event["name"] == "stage_change":
        yield f"event: stage\ndata: {json.dumps(event['data'])}\n\n"
    elif event["event"] == "on_chat_model_stream":
        token = event["data"]["chunk"].content
        if token:
            yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
```

### Pattern 4: HITL Pause/Resume via SSE + REST

**What:** When LangGraph hits `interrupt()`, the SSE stream emits a `hitl_pause` event with checkpoint metadata. The frontend renders Approve/Reject buttons. User action POSTs to `/api/chat/resume` with `thread_id + action`. The server resumes via `Command(resume=value)` and opens a new SSE stream.

**When to use:** Both Checkpoint 1 (research+structure approval) and Checkpoint 2 (draft approval).

**Example:**
```python
# Source: LangGraph interrupts docs + github.com/esurovtsev/langgraph-hitl-fastapi-demo
from langgraph.types import Command

class ResumeRequest(BaseModel):
    thread_id: str
    action: str          # "approve" | "approve_save" | "reject"
    feedback: str | None = None

@app.post("/api/chat/resume")
async def chat_resume(req: ResumeRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    resume_value = {"action": req.action, "feedback": req.feedback}

    async def generate():
        async for chunk, metadata in request.app.state.graph.astream(
            Command(resume=resume_value),
            config=config,
            stream_mode="messages-tuple",
        ):
            if hasattr(chunk, "content") and chunk.content:
                yield f"event: token\ndata: {json.dumps({'token': chunk.content})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

When the graph hits an `interrupt()` node, the stream emits the interrupt value before the generator ends:
```python
# Detecting interrupt in the stream (stream_mode="updates"):
async for event_type, data in graph.astream(input, config=config, stream_mode="updates"):
    if event_type == "__interrupt__":
        yield f"event: hitl_pause\ndata: {json.dumps({'checkpoint': data[0].value})}\n\n"
        return  # Stream ends; client waits for user action
```

### Pattern 5: Next.js Client-Side SSE Consumption

**What:** Direct `fetch()` + `ReadableStream` to FastAPI (not EventSource, which doesn't support POST body). Update Zustand store on each SSE event.

**When to use:** Main chat stream and resume stream.

**Example:**
```typescript
// Source: Upstash SSE blog + Next.js discussions
// hooks/useStream.ts
import { useChatStore } from "@/store/chatStore";

export async function startStream(message: string, threadId: string | null) {
  const store = useChatStore.getState();

  const response = await fetch("http://localhost:8000/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId, mode: store.mode }),
  });

  const reader = response.body!
    .pipeThrough(new TextDecoderStream())
    .getReader();

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    // Parse SSE lines
    const lines = value.split("\n");
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        // handle event type
      } else if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice(6));
        handleSSEEvent(currentEvent, data, store);
      }
    }
  }
}

function handleSSEEvent(event: string, data: any, store: any) {
  switch (event) {
    case "thread_id":
      sessionStorage.setItem("bond_thread_id", data.thread_id);
      store.setThreadId(data.thread_id);
      break;
    case "token":
      store.appendDraftToken(data.token);
      break;
    case "stage":
      store.setStage(data.stage, data.status);
      break;
    case "hitl_pause":
      store.setHitlPause(data.checkpoint);
      break;
    case "done":
      store.setStreaming(false);
      break;
  }
}
```

### Pattern 6: thread_id Session Persistence

**What:** `thread_id` persists in `sessionStorage` under key `bond_thread_id`. On mount, the app reads it and displays the session sidebar. `sessionStorage` clears on tab close; `localStorage` would persist across sessions (left to discretion).

**When to use:** Every page load.

```typescript
// hooks/useSession.ts
export function useSession() {
  const [threadId, setThreadId] = useState<string | null>(null);

  useEffect(() => {
    const stored = sessionStorage.getItem("bond_thread_id");
    if (stored) setThreadId(stored);
  }, []);

  const newSession = () => {
    sessionStorage.removeItem("bond_thread_id");
    setThreadId(null);
  };

  return { threadId, setThreadId, newSession };
}
```

### Pattern 7: FastAPI Corpus Ingestion Endpoint

**What:** Multipart form endpoint accepts all 4 input types. `python-multipart` is required for `UploadFile`.

**Example:**
```python
# Source: FastAPI file upload official docs
from fastapi import UploadFile, File, Form
from typing import Optional

@app.post("/api/corpus/ingest")
async def ingest_corpus(
    source_type: str = Form(...),          # "text" | "file" | "gdrive" | "url"
    text: Optional[str] = Form(None),      # for paste-text
    file: Optional[UploadFile] = File(None), # for PDF/DOCX/TXT upload
    gdrive_folder_id: Optional[str] = Form(None),
    blog_url: Optional[str] = Form(None),
    source_label: str = Form("own"),        # "own" | "external"
):
    # Route to appropriate Phase 1 ingestion handler
    ...
```

### Anti-Patterns to Avoid

- **Proxying SSE through Next.js Route Handler:** Next.js buffers the entire response before sending; use direct browser→FastAPI SSE instead (CORS is the correct solution, not proxying).
- **MemorySaver for checkpointing:** Phase 2 decision locked SqliteSaver; MemorySaver loses state on any server restart and cannot support HITL resume across page refreshes.
- **EventSource for POST-body streams:** The native `EventSource` API only supports GET. Use `fetch()` + `ReadableStream` for POST-based streaming.
- **`response.body.getReader()` without cleanup:** Always call `reader.releaseLock()` and handle abort signal to avoid memory leaks on long-lived connections.
- **Storing thread_id in React state only:** If the user refreshes mid-workflow, React state is lost; always sync to `sessionStorage`.
- **`export const runtime = 'edge'` for long streams:** Edge Runtime has time limits. For local dev this project, runtime is Node.js (default); no special export needed.
- **Tailwind v3 component patterns with v4:** The project uses Tailwind v4 (no `tailwind.config.js`; CSS-first config in `globals.css`). Don't copy v3 configuration patterns.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Markdown editor with preview | Custom split-pane textarea + marked.js renderer | `@uiw/react-md-editor` | GFM, toolbar, syntax highlighting, controlled + uncontrolled modes, TypeScript |
| SSE event parsing across chunk boundaries | Custom state machine | `eventsource-parser` (if routing via Next.js) or simple line-splitting via `TextDecoderStream` (if direct fetch) | Chunks can split mid-event; parser handles reassembly |
| LLM token streaming protocol | Custom WebSocket server | FastAPI `StreamingResponse` + `stream_mode="messages-tuple"` | Built into LangGraph; no custom protocol needed |
| Graph state persistence across requests | Custom session store / Redis | `AsyncSqliteSaver` (already Phase 2 decision) | Handles checkpoint serialization, thread isolation, concurrent reads |
| File type detection for corpus uploads | Custom MIME parser | FastAPI `UploadFile.content_type` + file extension check | `python-multipart` provides this; add server-side validation of actual bytes only if security is critical |
| Progress / stepper component | Build from scratch | shadcn/ui `Progress` + custom step state | shadcn components compose well; Tailwind v4 classes handle the visual |

**Key insight:** The LangGraph + FastAPI + SSE triangle is a well-trodden path in 2025. Every custom abstraction adds a debugging surface that doesn't exist in the proven pattern.

---

## Common Pitfalls

### Pitfall 1: Next.js SSE Buffering (Critical)
**What goes wrong:** If the frontend tries to proxy SSE through a Next.js App Router Route Handler (`app/api/stream/route.ts`), Next.js buffers the entire `StreamingResponse` before sending — the client sees a blank screen, then all tokens at once.
**Why it happens:** Next.js App Router's Web API Response abstraction waits for the handler to complete when running a `for await` loop inside the `start()` method of a `ReadableStream`.
**How to avoid:** Have the browser connect **directly** to the FastAPI backend via CORS. The Next.js frontend never proxies streaming. Set `Content-Encoding: none` and `Cache-Control: no-cache, no-transform` on FastAPI responses.
**Warning signs:** Tokens arrive all at once after a delay instead of progressively.

### Pitfall 2: LangGraph Node Re-execution on Resume
**What goes wrong:** After `Command(resume=...)`, LangGraph re-runs the **entire node** from the beginning, not from the line after `interrupt()`.
**Why it happens:** LangGraph's checkpointing saves state before the node, not mid-node; resume replays node entry.
**How to avoid:** Place `interrupt()` at the **start** of the node, before any side effects. Use a guard: `if state.get("awaiting_approval"): value = interrupt(...)`.
**Warning signs:** Duplicate research calls, duplicate saves to Metadata Log on resume.

### Pitfall 3: SSE Chunk Boundary Splitting
**What goes wrong:** A single SSE event spans two `reader.read()` chunks; parsing the second chunk alone yields malformed JSON.
**Why it happens:** TCP/HTTP chunking has no relationship to SSE event boundaries.
**How to avoid:** Buffer incomplete lines in the client loop. Example: accumulate `data:` lines until a blank line (double `\n\n`) is reached before parsing. Or use `eventsource-parser` which handles this automatically.
**Warning signs:** Occasional JSON parse errors in the console on token events.

### Pitfall 4: AsyncSqliteSaver Not Closed Properly
**What goes wrong:** If the checkpointer's `async with` context exits (e.g. unhandled exception at startup), subsequent requests get "checkpointer not initialized" or SQLite file lock errors.
**Why it happens:** `AsyncSqliteSaver` holds an `aiosqlite` connection that must be explicitly closed.
**How to avoid:** Always initialize inside FastAPI `lifespan` context manager so cleanup is guaranteed. Call `await checkpointer.setup()` before any graph operations to create the tables.
**Warning signs:** `sqlite3.OperationalError: database is locked` or `NoneType` errors on `app.state.graph`.

### Pitfall 5: Tailwind v4 Breaking Changes
**What goes wrong:** shadcn/ui component commands or examples copied from v3 documentation use `tailwind.config.js` configuration, HSL colors, or `tailwindcss-animate` — all changed in v4.
**Why it happens:** Most tutorial content online still targets Tailwind v3.
**How to avoid:** Initialize with `npx shadcn@latest init` which detects v4 and generates CSS-first config in `globals.css`. Use OKLCH color tokens. Replace `tailwindcss-animate` with `tw-animate-css` if needed.
**Warning signs:** Colors rendering as default browser styles; `tailwindcss-animate` import errors.

### Pitfall 6: EventSource Cannot POST
**What goes wrong:** Developer uses native `EventSource` for SSE but LangGraph needs the message body (topic, thread_id, mode) in the request.
**Why it happens:** `EventSource` only supports GET requests.
**How to avoid:** Use `fetch()` with `ReadableStream` for all SSE consumption. EventSource is only appropriate for parameter-less polling endpoints.
**Warning signs:** "Failed to execute 'EventSource'" TypeError or query-string-only parameters.

### Pitfall 7: Streaming into @uiw/react-md-editor Performance
**What goes wrong:** Appending a token on every SSE message causes a React re-render for every token (potentially 20-50/sec), causing editor lag.
**Why it happens:** React's default reconciler re-renders on every state update.
**How to avoid:** Batch token appends using a `useRef` accumulator and `requestAnimationFrame` flush at ~16ms intervals, or use `useTransition` to mark token appends as non-urgent. Test with typical ~30 token/sec output before optimizing.
**Warning signs:** Editor freezes or stutters; React DevTools shows >30 renders/sec.

---

## Code Examples

Verified patterns from official sources:

### FastAPI CORS Setup for Development
```python
# Source: FastAPI official CORS docs
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### LangGraph stream_mode="messages-tuple"
```python
# Source: LangGraph streaming docs (docs.langchain.com/oss/python/langgraph/streaming)
async for chunk, metadata in graph.astream(
    input_state,
    config={"configurable": {"thread_id": thread_id}},
    stream_mode="messages-tuple",
):
    # chunk: AIMessageChunk with .content (the token)
    # metadata: dict with langgraph_node, tags, etc.
    if chunk.content and metadata.get("langgraph_node") == "write_draft":
        yield f"event: token\ndata: {json.dumps({'token': chunk.content})}\n\n"
```

### LangGraph Interrupt + Resume Pattern
```python
# Source: LangGraph interrupts docs (docs.langchain.com/oss/python/langgraph/interrupts)
# In graph node:
from langgraph.types import interrupt

def checkpoint_node(state):
    # Place interrupt at start to avoid re-execution side effects
    human_decision = interrupt({
        "checkpoint_id": "checkpoint_1",
        "draft": state["draft"],
        "type": "approve_reject"
    })
    if human_decision["action"] == "reject":
        state["feedback"] = human_decision["feedback"]
        state["iteration_count"] += 1
    return state

# Resume call:
from langgraph.types import Command
result = await graph.ainvoke(
    Command(resume={"action": "approve"}),
    config={"configurable": {"thread_id": thread_id}},
)
```

### @uiw/react-md-editor Controlled with Streaming Tokens
```typescript
// Source: @uiw/react-md-editor npm docs + uiwjs.github.io/react-md-editor
import MDEditor from "@uiw/react-md-editor";

export function EditorPane({ draft, onChange }: { draft: string; onChange: (v: string) => void }) {
  return (
    <MDEditor
      value={draft}
      onChange={(val) => onChange(val ?? "")}
      height={600}
      preview="live"   // show both edit + preview panels
      data-color-mode="light"
    />
  );
}

// In the parent component, append tokens from Zustand:
const draft = useChatStore((s) => s.draft);
// draft is built up in the store: store.appendDraftToken(token) => state.draft += token
```

### Zustand Store for Chat + Streaming State
```typescript
// store/chatStore.ts
import { create } from "zustand";

type Stage = "idle" | "research" | "structure" | "writing" | "done" | "error";
type HitlPause = { checkpoint_id: string; type: string; data: any } | null;

interface ChatStore {
  mode: "author" | "shadow";
  threadId: string | null;
  stage: Stage;
  stageStatus: Record<Stage, "pending" | "running" | "complete">;
  draft: string;
  messages: Array<{ role: string; content: string }>;
  hitlPause: HitlPause;
  isStreaming: boolean;
  // Actions
  setMode: (mode: "author" | "shadow") => void;
  setThreadId: (id: string) => void;
  setStage: (stage: Stage, status: "running" | "complete") => void;
  appendDraftToken: (token: string) => void;
  setHitlPause: (pause: HitlPause) => void;
  setStreaming: (v: boolean) => void;
  addMessage: (msg: { role: string; content: string }) => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  mode: "author",
  threadId: null,
  stage: "idle",
  stageStatus: { idle: "pending", research: "pending", structure: "pending", writing: "pending", done: "pending", error: "pending" },
  draft: "",
  messages: [],
  hitlPause: null,
  isStreaming: false,
  setMode: (mode) => set({ mode }),
  setThreadId: (threadId) => set({ threadId }),
  setStage: (stage, status) => set((s) => ({
    stage,
    stageStatus: { ...s.stageStatus, [stage]: status },
  })),
  appendDraftToken: (token) => set((s) => ({ draft: s.draft + token })),
  setHitlPause: (hitlPause) => set({ hitlPause }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
}));
```

### SSE Event Schema (Canonical)
```
// Events emitted by FastAPI over /api/chat/stream and /api/chat/resume:

event: thread_id
data: {"thread_id": "uuid-string"}

event: stage
data: {"stage": "research|structure|writing", "status": "running|complete"}

event: token
data: {"token": "partial text chunk"}

event: message
data: {"role": "assistant", "content": "full message text"}

event: hitl_pause
data: {"checkpoint_id": "cp1|cp2", "type": "approve_reject", "iterations_remaining": 3}

event: error
data: {"message": "human-readable error", "retryable": true}

event: done
data: {}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LangGraph `MemorySaver` | `SqliteSaver` / `AsyncSqliteSaver` | ~LangGraph 0.2 | HITL works across page refreshes; required for this project |
| LangGraph `NodeInterrupt` exception | `interrupt()` function call | LangGraph ~0.2 early 2025 | Cleaner API; still re-runs entire node on resume |
| `astream_events` version="v1" | version="v2" | 2024 | v2 has better metadata, required for `on_custom_event` |
| Custom `__on_event__` callbacks | `adispatch_custom_event` | 2024 | Standard way to emit progress from inside nodes |
| Tailwind CSS `tailwind.config.js` | CSS-first config in `globals.css` | Tailwind v4 (2025) | No JS config; HSL → OKLCH; no `tailwindcss-animate` |
| Next.js Pages Router API routes | App Router Route Handlers | Next.js 13+ | Web API `Request`/`Response`; different from Node.js `req`/`res` |
| EventSource for streaming | `fetch` + `ReadableStream` | Ongoing | EventSource is GET-only; POST+body required for LLM prompts |

**Deprecated/outdated:**
- `from langgraph.checkpoint.sqlite import SqliteSaver` (sync): replaced by `from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver` for async FastAPI usage
- `tailwind.config.js` with `content` array: replaced by CSS `@import "tailwindcss"` in `globals.css`
- `@event_handler` patterns in older LangChain: replaced by `astream_events` v2

---

## Open Questions

1. **LangGraph `stream_mode` list support in `astream`**
   - What we know: `astream_events` with `version="v2"` is the most flexible; `stream_mode="messages-tuple"` + custom events via `adispatch_custom_event` is the cleaner architecture
   - What's unclear: Whether passing `stream_mode=["messages-tuple", "updates"]` as a list to `astream` actually yields tuples of `(mode, chunk)` reliably in LangGraph 0.3+
   - Recommendation: Default to `astream_events` with v2; filter `on_chat_model_stream` for tokens and `on_custom_event` for stage transitions. Simpler to maintain one event type schema.

2. **ResearchNode streaming: full result at once (locked decision)**
   - What we know: User decided research result should appear all at once, not word-by-word
   - What's unclear: The research node calls an LLM for summarization. If that LLM streams tokens by default, suppressing streaming requires explicit `streaming=False` on the model, or filtering by `langgraph_node` metadata in the SSE generator
   - Recommendation: Pass `streaming=False` to the RESEARCH_MODEL instantiation in the researcher node, or filter out `on_chat_model_stream` events where `metadata["langgraph_node"] == "research"`. Emit only a single `event: message` event when research completes.

3. **@uiw/react-md-editor with Tailwind v4**
   - What we know: `@uiw/react-md-editor` ships its own CSS; doesn't depend on Tailwind
   - What's unclear: Whether the editor's default styles conflict with Tailwind v4's OKLCH color variables or Next.js App Router's CSS bundling
   - Recommendation: Import the editor CSS explicitly (`import "@uiw/react-md-editor/markdown-editor.css"`) and wrap in a `data-color-mode="light"` div. Test for visual conflicts early in implementation.

4. **Concurrent requests with AsyncSqliteSaver**
   - What we know: SQLite has write serialization; concurrent writes from multiple threads fail
   - What's unclear: For this single-user MVP, concurrency is low-risk. If uvicorn runs multiple workers (`--workers N`), each worker has its own `AsyncSqliteSaver` instance referencing the same file — potential lock contention
   - Recommendation: Run uvicorn with a single worker (`--workers 1`) for MVP. Document as a known limitation.

---

## Sources

### Primary (HIGH confidence)
- `docs.langchain.com/oss/python/langgraph/streaming` — LangGraph streaming modes, messages-tuple, async
- `docs.langchain.com/oss/python/langgraph/interrupts` — interrupt(), Command(resume=...), thread_id persistence
- `pypi.org/project/langgraph-checkpoint-sqlite/` — version 3.0.3, AsyncSqliteSaver import path, `from_conn_string` API
- `fastapi.tiangolo.com/tutorial/cors/` — CORSMiddleware configuration
- `fastapi.tiangolo.com/tutorial/request-forms-and-files/` — UploadFile + Form combined endpoints
- `fastapi.tiangolo.com/advanced/events/` — lifespan context manager
- `github.com/vercel/next.js/discussions/48427` — SSE buffering in Next.js App Router, working patterns with `TransformStream` + `Content-Encoding: none`
- `deepwiki.com/langchain-ai/langgraph-fullstack-python/2.3-sse-streaming` — Complete FastAPI + LangGraph SSE architecture with `stream_mode="messages-tuple"`
- `ui.shadcn.com/docs/tailwind-v4` — shadcn/ui Tailwind v4 compatibility

### Secondary (MEDIUM confidence)
- `upstash.com/blog/sse-streaming-llm-responses` — Verified: fetch+ReadableStream pattern for Next.js SSE consumption (matches MDN Streams API)
- `github.com/esurovtsev/langgraph-hitl-fastapi-demo` — HITL demo with distinct stream/resume endpoints (verified: matches LangGraph interrupt docs pattern)
- `hackernoon.com/streaming-in-nextjs-15-websockets-vs-server-sent-events` — Next.js SSE headers, `X-Accel-Buffering: no`, reader.releaseLock()

### Tertiary (LOW confidence — flagged for validation)
- `mlvector.com/2025/06/30/30daysoflangchain-day-25` — astream_events event type names (`on_chat_model_start`, `on_tool_start`) — content was truncated; verify with official docs
- Token rendering performance (20-50 re-renders/sec) with `@uiw/react-md-editor` — no official benchmark; derived from React render behavior knowledge; test empirically

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified via official docs/PyPI; versions confirmed
- Architecture (FastAPI SSE pattern): HIGH — multiple official sources + working reference implementation
- HITL resume pattern: HIGH — official LangGraph interrupts docs + working demo repo
- Next.js SSE pitfalls: HIGH — verified via GitHub issue + official docs
- Token streaming performance: LOW — empirical claim, test required
- Tailwind v4 + react-md-editor compatibility: MEDIUM — shadcn v4 confirmed, react-md-editor CSS isolation not officially documented

**Research date:** 2026-02-21
**Valid until:** 2026-03-21 (30 days — LangGraph releases frequently; verify import paths before implementation)
