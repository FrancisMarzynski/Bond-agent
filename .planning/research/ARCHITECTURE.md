# System Architecture

**Domain:** LangGraph multi-agent blog writing system (dual-mode: Author + Shadow)
**Project:** Bond — Agent Redakcyjny
**Researched:** 2026-02-20
**Confidence:** MEDIUM — based on LangGraph 0.2 patterns (training data Aug 2025) + PROJECT.md analysis

---

## Architecture Decision: Single StateGraph, Dual-Branch

**Decision:** Author and Shadow are branches of ONE graph, not two separate graphs.

**Why:**
- Shared state schema, checkpointer, and streaming surface
- `route_mode` entry node dispatches via conditional edges
- RAG retriever node is shared — no duplicate ChromaDB calls
- Single FastAPI endpoint handles both modes

**Anti-pattern to avoid:** Two separate compiled graphs with separate checkpointers — doubles HITL complexity and loses shared context.

---

## Core State Schema

```python
from typing import Annotated, Literal
from langgraph.graph.message import add_messages
from pydantic import BaseModel

class BondState(TypedDict):
    # Mode routing
    mode: Literal["author", "shadow"]

    # Author mode inputs
    topic: str
    keywords: list[str]

    # Shadow mode input
    user_text: str

    # Research
    research_report: str        # Summary + sources list
    research_sources: list[dict]  # [{url, title, summary}]

    # RAG
    style_fragments: list[str]  # Top 3-5 chunks from ChromaDB

    # Generation
    raw_draft: str              # Pre-styling draft
    styled_draft: str           # Final draft with style injection

    # HITL
    human_feedback: str         # User's rejection reason
    approved: bool
    iteration_count: int        # Max 3 correction loops

    # Session messages (for display in chat UI)
    messages: Annotated[list, add_messages]

    # Metadata
    session_id: str
    duplicate_detected: bool
    duplicate_article: str | None  # Title of existing article if detected
```

---

## Graph Topology

### Author Branch

```
[START]
    ↓
route_mode ──────────────────────────────────────────────┐
    ↓ (mode == "author")                                  │
check_duplicates                                          │ (mode == "shadow")
    ↓                                                     │
author_research  ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
    ↓
[INTERRUPT: interrupt_before="author_structure"]
    ↓ (user approves research report + H-structure)
author_structure
    ↓
author_draft (Frontier model)
    ↓
rag_retriever (ChromaDB → style_fragments)
    ↓
author_style (inject style fragments → styled_draft)
    ↓
[INTERRUPT: interrupt_before="author_approve"]
    ↓ (user approves styled_draft)
author_approve ──────→ save_metadata → [END]
    ↓ (rejected: iteration_count < 3)
author_draft (regenerate with feedback)
```

### Shadow Branch

```
[START] → route_mode (mode == "shadow")
    ↓
rag_retriever (ChromaDB → style_fragments)
    ↓
shadow_analyze (compare user_text vs style_fragments)
    ↓
shadow_annotate (produce: annotated_text + corrected_version)
    ↓
[INTERRUPT: interrupt_before="shadow_approve"]
    ↓ (user approves)
shadow_approve → [END]
    ↓ (rejected with reason)
shadow_analyze (regenerate with feedback)
```

---

## Human-in-the-Loop Implementation

LangGraph `interrupt_before` pauses graph execution and persists state via SqliteSaver. Resume via separate API call.

```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_conn_string("bond_sessions.db")

graph = graph_builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["author_structure", "author_approve", "shadow_approve"]
)
```

**Pause flow:**
```python
# Initial run (hits first interrupt, returns)
result = graph.invoke(inputs, config={"configurable": {"thread_id": session_id}})
# State is persisted; frontend shows HITL checkpoint to user

# Resume after user approval
graph.update_state(
    config={"configurable": {"thread_id": session_id}},
    values={"approved": True, "human_feedback": ""}
)
result = graph.invoke(None, config={"configurable": {"thread_id": session_id}})
```

**Critical:** Always pass the same `thread_id` for resume. Store it in browser sessionStorage (survives page refresh).

---

## RAG: ChromaDB Style Retrieval

**Collection:** Single collection `bond_style_corpus` with source metadata.

```python
import chromadb
from langchain_chroma import Chroma
from sentence_transformers import SentenceTransformer

# Collection with source tagging
collection = client.get_or_create_collection(
    name="bond_style_corpus_v1",
    metadata={"hnsw:space": "cosine"}
)

# Each document tagged by source
collection.add(
    documents=chunks,
    metadatas=[{"source_type": "own", "author_id": "user"} for _ in chunks],
    ids=chunk_ids
)
```

**Retrieval (Dynamic Few-Shot):**
- Query: current topic + first paragraph of draft (not just topic keyword)
- Top-K: 5 chunks (configurable via env `RAG_TOP_K`)
- Prefer `source_type=own`; fall back to `external` if fewer than 3 own results
- Chunk size: 300–500 tokens, split at paragraph boundaries

**Embedding model:** `paraphrase-multilingual-MiniLM-L12-v2` (Polish-aware, free, local)

---

## Streaming Architecture

**Pattern:** LangGraph `astream_events` → FastAPI SSE → Next.js `ReadableStream`

```python
# FastAPI endpoint
@app.post("/api/chat/stream")
async def stream_article(request: ChatRequest):
    async def generate():
        config = {"configurable": {"thread_id": request.session_id}}
        async for event in graph.astream_events(
            request.inputs, config=config, version="v2"
        ):
            if event["event"] == "on_chat_model_stream":
                token = event["data"]["chunk"].content
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            elif event["event"] == "on_chain_end":
                node_name = event.get("name", "")
                yield f"data: {json.dumps({'type': 'node_complete', 'node': node_name})}\n\n"
            # HITL pause detected when graph returns without END
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return EventSourceResponse(generate())

# Separate resume endpoint
@app.post("/api/chat/resume")
async def resume(request: ResumeRequest):
    graph.update_state(
        config={"configurable": {"thread_id": request.session_id}},
        values={"approved": request.approved, "human_feedback": request.feedback}
    )
    return StreamingResponse(...)
```

**Three SSE event types:**
- `token` — LLM output chunk (rendered progressively in UI)
- `node_complete` — node boundary (drives progress indicator)
- `hitl_pause` — interrupt reached (shows approval UI in frontend)

---

## Component Boundaries

```
┌─────────────────────────────────────────────────────┐
│                   Next.js Frontend                   │
│  ChatInterface → ModeToggle → ProgressIndicator     │
│  MarkdownEditor → ApproveRejectPanel → Repurpose UI │
└───────────────────┬─────────────────────────────────┘
                    │ SSE / REST (JSON)
┌───────────────────▼─────────────────────────────────┐
│                 FastAPI Backend                       │
│  /api/chat/stream  /api/chat/resume                  │
│  /api/corpus/ingest  /api/metadata/check             │
└───────────────────┬─────────────────────────────────┘
                    │ Python function calls
┌───────────────────▼─────────────────────────────────┐
│               LangGraph StateGraph                   │
│  route_mode → [author branch | shadow branch]        │
│  Shared: rag_retriever, save_metadata                │
└──────┬──────────────┬──────────────┬────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼──────┐ ┌────▼────────────────┐
│  ChromaDB   │ │   SQLite   │ │   Exa / Web Search  │
│  (RAG store)│ │(sessions + │ │   (Researcher node) │
│             │ │ metadata)  │ │                     │
└─────────────┘ └────────────┘ └─────────────────────┘
```

---

## Data Flow

### Author Mode (full cycle)

```
User input: topic + keywords
    ↓
route_mode: set state.mode = "author"
    ↓
check_duplicates: embed topic → query SQLite → if match, warn + offer override
    ↓
author_research: Exa search(topic, keywords) → summarize results → research_report
    ↓
[HITL PAUSE] → Frontend shows: research_report + proposed H-structure
    ↓ User approves
author_structure: generate final H1/H2/H3 structure using approved outline
    ↓
author_draft: generate full draft (Frontier model, H-structure + research_report in context)
    ↓
rag_retriever: embed(topic + first_para) → ChromaDB → style_fragments[0..4]
    ↓
author_style: rewrite draft with style injection (Few-Shot exemplars in system prompt)
    ↓
[HITL PAUSE] → Frontend shows: styled_draft in Markdown editor
    ↓ User approves
save_metadata: write {topic, date, word_count, mode} to SQLite Metadata Log
    ↓
[END] — Frontend shows: approved draft + repurpose options
```

### Shadow Mode (full cycle)

```
User input: paste article text
    ↓
route_mode: set state.mode = "shadow"
    ↓
rag_retriever: embed(first 500 chars of user_text) → ChromaDB → style_fragments
    ↓
shadow_analyze: diff user_text style vs style_fragments → identify deviations
    ↓
shadow_annotate: produce annotated_text (inline suggestions) + corrected_version
    ↓
[HITL PAUSE] → Frontend shows: annotated_text + corrected_version side-by-side
    ↓ User approves or rejects with feedback
[END] / regenerate loop
```

---

## Suggested Build Order

**Layer 0 — Infrastructure (no LLM)**
- ChromaDB: create collection, test add/query
- SQLite: sessions table + metadata_log table
- Env var schema: define all required variables, add validation on startup
- Corpus ingestion script: paste text → chunk → embed → store

**Layer 1 — Graph skeleton (no generation)**
- BondState TypedDict
- `route_mode` node with conditional edges
- SqliteSaver checkpointer
- HITL interrupt points (stub nodes)
- Verify: graph compiles, checkpointer persists state

**Layer 2 — RAG retriever**
- ChromaDB LangChain integration
- `rag_retriever` node (shared by both branches)
- Test: retrieval quality with 5+ exemplar articles loaded

**Layer 3 — Author branch (no HITL yet)**
- `author_research` (Exa search + summarize)
- `author_draft` (Frontier model + SEO prompt)
- `author_style` (inject style_fragments)
- Test: full draft generation without interrupts

**Layer 4 — HITL mechanism**
- Wire `interrupt_before` to author_structure and author_approve nodes
- FastAPI resume endpoint
- Test: pause → state persists → resume → continues correctly

**Layer 5 — Shadow branch**
- `shadow_analyze` + `shadow_annotate` nodes
- Same HITL mechanism as Layer 4

**Layer 6 — Streaming FastAPI API**
- `astream_events` → SSE endpoint
- Token streaming, node_complete events, hitl_pause events
- Resume endpoint

**Layer 7 — Next.js Frontend**
- ChatInterface + SSE consumer
- ModeToggle (Author/Shadow)
- ProgressIndicator (per-node)
- MarkdownEditor (approve/reject panel)

**Layer 8 — YouTube + Repurposing pipelines**
- `youtube_extractor` node (youtube-transcript-api)
- `repurpose` node (4 platform variants)

**Layer 9 — Polish + Metadata**
- `check_duplicates` node (embedding similarity vs Metadata Log)
- Research cache (in-session memoization)
- Cost monitoring per-article

**Critical path to first working demo (Author mode):** Layers 0 → 1 → 2 → 3 → 4 → 6 → 7

---

## Key Anti-Patterns

| Anti-Pattern | Why Dangerous | Fix |
|-------------|---------------|-----|
| Two separate graphs for Author/Shadow | Duplicates checkpointer state, breaks shared RAG | One graph, conditional edges |
| ChromaDB query inside every LLM node | 3+ redundant vector DB calls per session | Shared `rag_retriever` node, store in state |
| `graph.invoke()` for user-facing calls | Blocks HTTP thread for 2-5 min → timeout | Always use `graph.astream_events()` |
| Full article text in `messages` list | Token cost explosion on correction loops | Store draft in dedicated state field, not messages |
| Hardcoded `"gpt-4o"` model names | Breaks configurability requirement | Always `os.environ["DRAFT_MODEL"]` |
| `MemorySaver` checkpointer | State lost on server restart | `SqliteSaver` from day one |
| Skip checkpointer for HITL | Graph cannot pause/resume | Hard blocker — checkpointer is mandatory for HITL |

---

## Sources

- Project context: `.planning/PROJECT.md`
- LangGraph 0.2 documentation patterns: StateGraph, SqliteSaver, interrupt_before, astream_events (training data Aug 2025)
- FastAPI SSE + LangGraph streaming pattern: established community pattern
- ChromaDB multi-source collection design: standard RAG pattern
- Overall confidence: MEDIUM on API specifics (verify import paths), HIGH on architectural decisions and component boundaries
