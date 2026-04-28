# Bond — Agent Redakcyjny

LangGraph-powered editorial assistant. Two modes: **Author** (topic → research → HITL → draft → HITL → publish) and **Shadow** (paste text → style analysis → annotated corrections → HITL → corrected version). All UI text and commit messages are in Polish.

## Commands

### Backend (Python, run from project root)

```bash
uv run uvicorn bond.api.main:app --reload --port 8000   # dev server
uv run pytest                                            # all tests
uv run pytest tests/unit/                               # unit tests only
uv run ruff check .                                     # lint
uv run ruff format .                                    # format
```

### Frontend (run from `frontend/`)

```bash
npm run dev      # Next.js dev server (port 3000)
npm run build    # production build
npm run lint     # ESLint
```

### Docker

```bash
docker compose up --build          # start all services
docker compose up bond-api         # backend + ChromaDB only
```

## Architecture

```
bond/
  api/
    main.py          # FastAPI app, lifespan compiles graph once → app.state.graph
    routes/
      chat.py        # /api/chat/stream + /api/chat/resume + /api/chat/history/{id}
      corpus.py      # /api/corpus/* (ingest, status)
    stream.py        # parse_stream_events(), _STAGE_MAP, _KNOWN_NODES
  graph/
    graph.py         # build_author_graph(), compile_graph(), routing functions
    state.py         # BondState (TypedDict), AuthorState alias
    nodes/           # one file per node; all sync def, return dict | Command
  corpus/            # chunker, ingestor, retriever, sources/*
  db/                # metadata_log.py, search_cache.py, schema.sql
  store/             # chroma.py (singleton client), article_log.py
  config.py          # Settings (pydantic-settings), settings singleton
  schemas.py         # StreamEvent, CheckpointResponse, AgentInput, AgentOutput
  llm.py             # get_research_llm(), get_draft_model() — cascaded selection
  prompts/           # context.py, writer.py
frontend/
  src/
    app/             # Next.js App Router pages (layout.tsx, page.tsx, shadow/page.tsx)
    components/      # React components
    components/ui/   # shadcn/ui primitives (button, card, input, …)
    hooks/           # useStream.ts, useSession.ts
    store/           # chatStore.ts (author + shared), shadowStore.ts
    lib/             # sse.ts (SSEParser), utils.ts
    config.ts        # API_URL
```

## Key Invariants

**SSE event wire format** — all events:
```json
{"type": "<kind>", "data": "<payload_string>"}
```
Types: `thread_id`, `stage`, `token`, `heartbeat`, `node_start`, `node_end`, `hitl_pause`, `shadow_corrected_text`, `annotations`, `system_alert`, `done`, `error`. Defined in `StreamEvent` (`schemas.py`) with `Literal` — add new types there first.

**HITL interrupt payload shape** (locked — do not change):
```python
interrupt({
    "checkpoint": "<node_name>",
    "type": "approve_reject",
    ...fields,
})
```

**Resume request** sends `{"action": "approve"|"reject"|"abort", "feedback": "..."}` via `POST /api/chat/resume`. Handler builds `Command(resume=...)`.

**Graph routing is stable** — routing function bodies (`_route_after_cp1`, `_route_after_cp2`, `_route_after_shadow_checkpoint`, `route_mode`) and `add_conditional_edges` wiring must not change between plans. Replace node bodies via `_node_registry`, never touch edge declarations.

**Defense-in-depth caps** — every HITL loop has two guards:
1. Node-level: `Command(goto=END)` when `iterations >= HARD_CAP`
2. Routing-level: safety check in the `_route_after_*` function in `graph.py`

## Backend Patterns

**Nodes** — all sync functions, return `dict` (state patch) or `Command`:
```python
from bond.graph.state import BondState
from langgraph.types import interrupt, Command
from langgraph.graph import END

def my_node(state: BondState) -> dict | Command:
    ...
    user_response = interrupt({...})
    ...
    return {"some_field": value}
```

**Pydantic models** — always `ConfigDict(extra="forbid")` for public schemas:
```python
class MyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

**Settings** — import the singleton, never instantiate `Settings()` again:
```python
from bond.config import settings
```

**SQLite** — always `check_same_thread=False` for async use. Schema-on-connect: run `CREATE TABLE IF NOT EXISTS` on every `_get_conn()` call (zero-config migration).

**ChromaDB** — use `get_chroma_client()` singleton from `bond/store/chroma.py`. Never instantiate `PersistentClient` directly in a node.

**Logging** — one logger per module, no log calls in hot streaming path:
```python
log = logging.getLogger(__name__)
```

**LLMs** — use `get_research_llm()` for research/analysis nodes, `get_draft_model()` for writer/structure nodes. Configured via `settings.research_model` / `settings.draft_model`.

## Frontend Patterns

**All interactive components** need `"use client"` at the top.

**Zod schemas** defined at module scope, not inside components or hooks:
```ts
const HitlPauseSchema = z.object({ ... });  // top of file
```

**Stores** — two Zustand stores:
- `useChatStore` (`chatStore.ts`) — shared streaming state, Author mode, `hitlPause`
- `useShadowStore` (`shadowStore.ts`) — Shadow mode: `originalText`, `annotations`, `shadowCorrectedText`

Access state outside React with `useChatStore.getState()` / `useShadowStore.getState()`.

**`useStream` hook** — single entry point for starting and resuming streams. Manages `AbortController` via the store; never hold a controller reference in a component.

**`resumeStream` signature**:
```ts
resumeStream(threadId, action, feedback, onThreadId)
// action: "approve" | "approve_save" | "reject"
```

**Path alias** — `@/` resolves to `frontend/src/`.

**shadcn/ui** — UI primitives live in `components/ui/`. Use `Button`, `Textarea`, `Card`, `Badge`, etc. from there; don't reach for raw HTML.

## Data Stores

| Store | Path | Purpose |
|---|---|---|
| ChromaDB | `./data/chroma` | Style corpus vectors + semantic search cache |
| LangGraph checkpoints | `./data/bond_checkpoints.db` | HITL state persistence |
| Metadata log | `./data/bond_metadata.db` | Published article log (duplicate detection) |
| Article log | `./data/articles.db` | Corpus article count (low-corpus warning) |

Two separate SQLite files for checkpoints vs metadata to avoid schema conflicts.

## Environment Variables

Copy `.env.example` to `.env`. Required keys:
- `OPENAI_API_KEY` — gpt-4o-mini (research) + gpt-4o (draft/structure)
- `EXA_API_KEY` — web search via Exa MCP
- `GOOGLE_CREDENTIALS_PATH` / `GOOGLE_AUTH_METHOD` — for Google Drive corpus source

Model selection: `RESEARCH_MODEL=gpt-4o-mini`, `DRAFT_MODEL=gpt-4o` (overrides config defaults).

## Testing

```bash
uv run pytest                          # all
uv run pytest tests/unit/api/          # API unit tests
uv run pytest -k test_metadata         # filter by name
```

Tests use `pytest-asyncio` with `asyncio_mode = "auto"`. Fixtures in `tests/conftest.py`.

## Current State

Phase 4 (Shadow Mode) is ~90% complete. **One gap remains** (SHAD-05/06):

`HitlPauseSchema` in `chatStore.ts` is missing `annotations`, `shadow_corrected_text`, `iteration_count` fields → Zod strips them → `shadowStore` is never populated when `shadow_checkpoint` fires. Additionally, `ShadowPanel` has no approve/reject buttons for the shadow checkpoint case.

Fix: extend `HitlPauseSchema`, wire `setAnnotations`/`setShadowCorrectedText` in the `hitl_pause` handler in `useStream.ts`, add approve/reject UI to `ShadowPanel`.

See `.planning/STATE.md` for full details.
