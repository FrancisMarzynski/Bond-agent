# Phase 2: Author Mode Backend - Research

**Researched:** 2026-02-20
**Domain:** LangGraph StateGraph / HITL / Exa web search / RAG injection / duplicate detection
**Confidence:** HIGH (core stack verified via official sources and PyPI); MEDIUM (Exa Polish-language quality, duplicate threshold calibration)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Research report format**
- Structure: Title + URL + 2-3 sentence summary per source
- Begins with a brief synthesis section (2-3 paragraphs) summarizing key themes across sources before the source list
- Number of sources: Claude's discretion based on topic complexity
- Storage and persistence within session: Claude's discretion (LangGraph state or file-backed — whatever fits the graph design)

**Checkpoint 1 interaction model**
- On rejection: user edits the H1/H2/H3 structure outline directly, with an optional free-text note
- Edited structure + note are fed back to regenerate the proposal

**Checkpoint 2 interaction model**
- On rejection: targeted revision of flagged sections only — user specifies which sections to redo, others remain
- The 3-iteration limit is a soft cap: after 3 iterations, continue with a warning (no hard block — user can keep going)
- Session recovery: resume from last LangGraph checkpoint via SqliteSaver if interrupted (no lost work)

**Draft quality enforcement**
- If hard constraints aren't met (keyword placement, heading hierarchy, meta-description length, word count, RAG fragment count): auto-retry silently up to 2 times, then surface the failure
- RAG style fragment integration: Claude's discretion — pick the approach that produces the most natural style transfer
- Minimum word count: configurable via env var, default 800 words
- Low corpus warning: if corpus is below the 10-article threshold, warn the user and pause — proceed only if user confirms

**Duplicate detection**
- Override mechanism: HITL interrupt — pipeline pauses, user decides yes/no before research begins
- Warning content: Claude's discretion — show what's most useful to make the override decision
- Default similarity threshold: Claude's discretion — calibrate to embedding similarity norms
- Override logging: none — once overridden, the session proceeds as a clean new run (no trace in Metadata Log)

### Claude's Discretion

- Number of research sources (scale to topic complexity)
- Research report storage within session (in-graph state vs. file-backed)
- RAG fragment integration approach (soft prompt injection vs. structural placement)
- Duplicate warning content (what context to surface)
- Default DUPLICATE_THRESHOLD value

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-01 | User can launch Author mode by providing topic and keywords | LangGraph StateGraph entry node accepts `topic` + `keywords` in state schema; invoke with thread_id |
| AUTH-02 | Agent performs web research (Exa) and generates report: sources with titles, links, summaries | Exa `search_and_contents` with `summary=True` and `text` options; report stored in graph state |
| AUTH-03 | Agent proposes H1/H2/H3 heading structure based on research | Separate `structure_node` after researcher node; prompt template generates outline from research state |
| AUTH-04 | User approves or rejects report and heading structure (Checkpoint 1) | LangGraph `interrupt()` in checkpoint_1 node; `Command(resume=...)` resumes with approve/reject+feedback |
| AUTH-05 | After Checkpoint 1 approval, agent generates SEO-compliant draft (keyword in H1/first paragraph, heading hierarchy, meta-description 150-160 chars, min 800 words) | `writer_node` with structured SEO prompt template; word count/meta-description length validated post-generation |
| AUTH-06 | Agent stylizes draft by injecting 3-5 exemplar fragments from vector DB (RAG Few-Shot) | ChromaDB `query()` fetches top-K fragments; injected into prompt as few-shot examples before draft generation |
| AUTH-07 | User approves or rejects stylized draft (Checkpoint 2) | Second `interrupt()` call in checkpoint_2 node; same Command resume pattern |
| AUTH-08 | User can provide feedback on rejection — agent regenerates without losing session context (max 3 soft-cap iterations) | Iteration counter tracked in state; conditional edge loops back to writer_node if rejected and count < 3 (or with warning if ≥3) |
| AUTH-09 | After approval, system saves article metadata to Metadata Log (topic, date, mode) | `save_metadata_node` writes to SQLite metadata table (separate from LangGraph checkpoint DB); topic embedding stored for DUPL-01 |
| AUTH-10 | Web search results are cached within session — same topic does not trigger second Exa API call | `search_cache: dict` field in state (or module-level dict keyed by topic+thread_id); checked before Exa call |
| AUTH-11 | LLM models configured via env vars (RESEARCH_MODEL for research/analysis, DRAFT_MODEL for final draft) | `os.environ.get()` at node init; separate ChatOpenAI/ChatAnthropic instances per node |
| DUPL-01 | Before research begins, agent checks for duplicate topics via embedding similarity vs Metadata Log | `duplicate_check_node` embeds incoming topic; queries metadata embeddings table; applies DUPLICATE_THRESHOLD |
| DUPL-02 | When similar topic detected, agent informs user: title of existing article + publication date | `interrupt()` in duplicate_check_node surfaces match title + date; user sees both before deciding |
| DUPL-03 | User can override duplicate warning and continue | `Command(resume=True/False)` resumes; if True, pipeline continues to researcher; if False, graph ends |
| DUPL-04 | Similarity threshold configurable via DUPLICATE_THRESHOLD env var | `float(os.environ.get("DUPLICATE_THRESHOLD", "0.85"))` at node init |
</phase_requirements>

---

## Summary

Phase 2 builds the complete Author mode pipeline as a LangGraph `StateGraph` running in pure Python — no frontend. The graph receives a topic and keywords, performs duplicate checking against the Metadata Log, runs web research via Exa, pauses twice for human approval (Checkpoint 1: research report + heading structure; Checkpoint 2: stylized draft), regenerates on rejection, and saves metadata on final approval. All HITL pauses use LangGraph's `interrupt()` / `Command(resume=...)` pattern backed by `SqliteSaver` so sessions survive process restarts.

The three technically uncertain areas flagged during project initialization have been resolved by research: (1) SqliteSaver now lives in the separate `langgraph-checkpoint-sqlite` package (v3.0.3, released Jan 2026), imported as `from langgraph.checkpoint.sqlite import SqliteSaver`; (2) Exa now returns language-matched results by default since November 2025, so Polish-language queries work without special parameters; (3) `astream_events(version="v2")` is the confirmed streaming API for capturing `on_chat_model_stream` events (needed by Phase 3 but the graph must be designed for it now).

The standard stack is mature and stable: LangGraph, Exa exa-py, sentence-transformers with `paraphrase-multilingual-MiniLM-L12-v2`, and ChromaDB (already established in Phase 1). The main pitfall to avoid is placing non-idempotent operations (Exa API calls, LLM calls) before an `interrupt()` in the same node — because the entire node re-executes on resume.

**Primary recommendation:** Design each HITL checkpoint as its own dedicated node containing only the `interrupt()` call. Put all expensive API calls in the node before the checkpoint node. This eliminates the node re-execution pitfall cleanly.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | latest (install with `-U`) | StateGraph orchestration, HITL interrupt/resume, conditional edges | Project decision; only framework with first-class HITL + persistence |
| langgraph-checkpoint-sqlite | 3.0.3 (Jan 2026) | SqliteSaver for durable state persistence | Project decision; SqliteSaver moved to this separate package in langgraph 0.2+ |
| exa-py | 2.4.0 (Feb 2026) | Web research via Exa neural search API | Project decision; returns full article text + summaries, language-matched by default |
| sentence-transformers | latest | Embeddings for duplicate detection (paraphrase-multilingual-MiniLM-L12-v2) | Project decision; same model used for corpus embeddings in Phase 1 |
| chromadb | latest | Vector store for corpus (Phase 1 output) and topic embedding queries | Project decision; already established in Phase 1 |
| python-dotenv | latest | Load env vars (RESEARCH_MODEL, DRAFT_MODEL, DUPLICATE_THRESHOLD, MIN_WORD_COUNT) | Standard Python env var management |
| pydantic | v2 | State field validation, config schemas | Project constraint (modular architecture) |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| langchain-openai / langchain-anthropic | latest | LLM chat model wrappers for RESEARCH_MODEL and DRAFT_MODEL | One or both depending on which providers are configured |
| aiosqlite | latest (installed by langgraph-checkpoint-sqlite) | Async SQLite for AsyncSqliteSaver | If async invocation path is used in Phase 3 FastAPI integration |
| sqlite3 | stdlib | Metadata Log storage (separate from checkpoint DB) | Lightweight persistence for article metadata |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SqliteSaver | PostgresSaver (langgraph-checkpoint-postgres) | Postgres has better write concurrency but SQLite is sufficient for 1-2 users; PostgresSaver adds infra complexity |
| exa-py | tavily-python | Exa is the project decision; Tavily would require full abstraction layer swap |
| paraphrase-multilingual-MiniLM-L12-v2 | text-embedding-3-small (OpenAI) | Local model has no per-call cost and works offline; OpenAI embedding adds latency and API dependency |

**Installation:**
```bash
pip install langgraph langgraph-checkpoint-sqlite "exa-py>=2.4.0" sentence-transformers chromadb python-dotenv pydantic langchain-openai
```

---

## Architecture Patterns

### Recommended Project Structure

```
bond/
├── graph/
│   ├── __init__.py          # exports compiled graph
│   ├── state.py             # AuthorState TypedDict definition
│   ├── graph.py             # StateGraph builder + compile
│   └── nodes/
│       ├── duplicate_check.py   # DUPL-01, DUPL-02, DUPL-03
│       ├── researcher.py        # AUTH-02, AUTH-10
│       ├── structure.py         # AUTH-03
│       ├── checkpoint_1.py      # AUTH-04 — only interrupt() call
│       ├── writer.py            # AUTH-05, AUTH-06
│       ├── checkpoint_2.py      # AUTH-07 — only interrupt() call
│       └── save_metadata.py     # AUTH-09
├── db/
│   ├── metadata_log.py      # SQLite schema + CRUD for Metadata Log
│   └── schema.sql
├── config.py                # env var loading (RESEARCH_MODEL, DRAFT_MODEL, etc.)
├── harness.py               # CLI test harness for running graph without frontend
└── tests/
    └── test_author_flow.py
```

### Pattern 1: AuthorState TypedDict

**What:** A single TypedDict that holds all state flowing through the graph. Each node reads from it and returns partial updates (only changed keys).

**When to use:** Always — this is the LangGraph state pattern.

```python
# Source: LangGraph official docs (docs.langchain.com/oss/python/langgraph)
from typing import TypedDict, Optional, Annotated
from langgraph.graph.message import add_messages

class AuthorState(TypedDict):
    # Input
    topic: str
    keywords: list[str]
    thread_id: str

    # Duplicate detection
    duplicate_match: Optional[dict]         # {"title": str, "date": str} or None
    duplicate_override: Optional[bool]      # True = user chose to proceed

    # Research
    search_cache: dict                      # key: topic, value: raw Exa results
    research_report: Optional[str]          # formatted Markdown report

    # Structure
    heading_structure: Optional[str]        # H1/H2/H3 outline as Markdown

    # Checkpoint 1
    cp1_approved: Optional[bool]
    cp1_feedback: Optional[str]             # rejection feedback + edited structure
    cp1_iterations: int                     # regeneration count

    # Draft
    draft: Optional[str]                    # full Markdown draft
    draft_validated: Optional[bool]         # passed SEO constraint checks

    # Checkpoint 2
    cp2_approved: Optional[bool]
    cp2_feedback: Optional[str]             # section-targeted feedback
    cp2_iterations: int

    # Output
    metadata_saved: bool
```

### Pattern 2: SqliteSaver Setup (Verified Import Path)

**What:** Separate package install; context manager or direct instantiation for sync use.

**When to use:** All graph compilation — project decision is SqliteSaver from day 1, never MemorySaver.

```python
# Source: pypi.org/project/langgraph-checkpoint-sqlite/ + GitHub issue #1253 resolution
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

# Sync instantiation (for scripts and test harness)
checkpointer = SqliteSaver(sqlite3.connect("bond_checkpoints.db", check_same_thread=False))
graph = builder.compile(checkpointer=checkpointer)

# Async (for FastAPI in Phase 3)
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
# use as async context manager:
async with AsyncSqliteSaver.from_conn_string("bond_checkpoints.db") as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)
```

**CRITICAL:** `check_same_thread=False` is required for sync SQLite when multiple threads access the connection.

### Pattern 3: interrupt() for HITL Checkpoints

**What:** `interrupt()` pauses execution and surfaces a value to the caller. `Command(resume=...)` resumes it.

**When to use:** Checkpoint 1 and Checkpoint 2 nodes — each in their own dedicated node with ONLY the interrupt call.

```python
# Source: docs.langchain.com/oss/python/langgraph/interrupts
from langgraph.types import interrupt, Command

# checkpoint_1.py — dedicated node, nothing else
def checkpoint_1_node(state: AuthorState) -> dict:
    # Surfaces report + structure to caller; pauses here
    user_response = interrupt({
        "research_report": state["research_report"],
        "heading_structure": state["heading_structure"],
        "cp1_iterations": state["cp1_iterations"],
    })
    # user_response is whatever was passed via Command(resume=...)
    # user_response = {"approved": True} or {"approved": False, "edited_structure": "...", "note": "..."}
    if user_response["approved"]:
        return {"cp1_approved": True}
    else:
        return {
            "cp1_approved": False,
            "cp1_feedback": user_response.get("edited_structure", "") + "\n" + user_response.get("note", ""),
            "cp1_iterations": state["cp1_iterations"] + 1,
        }

# Resuming from test harness / API:
config = {"configurable": {"thread_id": "session-abc123"}}
result = graph.invoke(initial_state, config=config)
# Check result["__interrupt__"] to see what the interrupt surfaced
graph.invoke(Command(resume={"approved": True}), config=config)
```

### Pattern 4: Conditional Edge Routing (Approval Loops)

**What:** After each checkpoint node, a routing function decides whether to loop back (regenerate) or advance (proceed).

```python
# Source: docs.langchain.com/oss/python/langgraph/graph-api
def route_after_cp1(state: AuthorState) -> str:
    if state["cp1_approved"]:
        return "writer"
    return "structure"  # loop back to regenerate structure

builder.add_conditional_edges(
    "checkpoint_1",
    route_after_cp1,
    {"writer": "writer", "structure": "structure"}
)

def route_after_cp2(state: AuthorState) -> str:
    if state["cp2_approved"]:
        return "save_metadata"
    # Soft cap: warn but allow continuation beyond 3
    return "writer"

builder.add_conditional_edges(
    "checkpoint_2",
    route_after_cp2,
    {"save_metadata": "save_metadata", "writer": "writer"}
)
```

### Pattern 5: Exa Research with Session Cache

**What:** Check `search_cache` dict in state before calling Exa. Store results under the topic key.

```python
# Source: exa-py PyPI / docs.exa.ai
from exa_py import Exa

def researcher_node(state: AuthorState) -> dict:
    topic = state["topic"]
    cache = state.get("search_cache", {})

    if topic in cache:
        raw_results = cache[topic]  # AUTH-10: no duplicate API call
    else:
        exa = Exa(api_key=os.environ["EXA_API_KEY"])
        # search_and_contents: text=True for full article, summary=True for abstractive summaries
        response = exa.search_and_contents(
            query=f"{topic} {' '.join(state['keywords'])}",
            num_results=8,          # scale to topic complexity (Claude's discretion)
            type="auto",            # auto = neural + keyword blend
            text={"max_characters": 3000},
            summary={"query": topic},
        )
        raw_results = [
            {
                "title": r.title,
                "url": r.url,
                "summary": r.summary,
                "text": r.text,
            }
            for r in response.results
        ]
        cache[topic] = raw_results

    report = _format_research_report(raw_results, state["keywords"])
    return {"research_report": report, "search_cache": cache}
```

**Note on language:** Exa detects query language automatically since Nov 2025 and returns matching-language results by default. Polish queries return Polish results without extra parameters.

### Pattern 6: Duplicate Detection

**What:** Embed incoming topic, query Metadata Log embeddings, compare cosine similarity.

```python
# Source: trychroma.com/docs + huggingface.co sentence-transformers
from sentence_transformers import SentenceTransformer
import chromadb

DUPLICATE_THRESHOLD = float(os.environ.get("DUPLICATE_THRESHOLD", "0.85"))

def duplicate_check_node(state: AuthorState) -> dict:
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    topic_embedding = model.encode([state["topic"]])[0].tolist()

    # Metadata Log embeddings stored in a separate ChromaDB collection
    client = chromadb.PersistentClient(path="./bond_chroma")
    meta_collection = client.get_or_create_collection(
        name="metadata_log",
        configuration={"hnsw": {"space": "cosine"}}
    )

    results = meta_collection.query(
        query_embeddings=[topic_embedding],
        n_results=1,
        include=["metadatas", "distances"]
    )

    if results["ids"][0]:
        # ChromaDB returns cosine DISTANCE, not similarity; convert:
        distance = results["distances"][0][0]
        similarity = 1.0 - distance
        if similarity >= DUPLICATE_THRESHOLD:
            match_meta = results["metadatas"][0][0]
            # Pause for user decision
            proceed = interrupt({
                "warning": "Similar topic found",
                "existing_title": match_meta.get("title"),
                "existing_date": match_meta.get("published_date"),
                "similarity_score": round(similarity, 3),
            })
            if not proceed:
                return {"duplicate_override": False}  # graph will route to END
            return {"duplicate_override": True}

    return {"duplicate_override": None}  # no duplicate found, proceed
```

**Threshold recommendation:** 0.85 cosine similarity as default (project-flagged as requiring calibration — budget tuning time). At 384-dim with paraphrase-multilingual model, 0.85 is conservative (low false-positive rate). Can lower to 0.80 if too many near-duplicates slip through.

### Pattern 7: RAG Style Injection

**What:** Fetch top-K style fragments from Phase 1 corpus, inject into writer prompt as few-shot examples.

```python
# Source: chromadb docs + project Phase 1 corpus collection
def writer_node(state: AuthorState) -> dict:
    # RAG: fetch exemplar style fragments
    client = chromadb.PersistentClient(path="./bond_chroma")
    corpus = client.get_collection("style_corpus")  # Phase 1 output

    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    query_embedding = model.encode([state["topic"]]).tolist()

    rag_results = corpus.query(
        query_embeddings=query_embedding,
        n_results=5,
        where={"source_type": "own_text"},  # prefer own texts per Phase 1 tagging
        include=["documents", "metadatas"]
    )
    exemplar_fragments = rag_results["documents"][0]  # list of 5 text strings

    # Inject as few-shot prefix in system prompt
    system_prompt = _build_writer_system_prompt(
        exemplars=exemplar_fragments,
        keywords=state["keywords"],
        heading_structure=state["heading_structure"],
        research_report=state["research_report"],
        cp2_feedback=state.get("cp2_feedback"),  # targeted section feedback on regeneration
        min_words=int(os.environ.get("MIN_WORD_COUNT", "800")),
    )
    llm = ChatOpenAI(model=os.environ["DRAFT_MODEL"], temperature=0.7)
    draft = llm.invoke(system_prompt).content

    # Validate SEO constraints; silent auto-retry up to 2 times
    draft, validated = _validate_and_retry(draft, state, llm, system_prompt, max_retries=2)
    return {"draft": draft, "draft_validated": validated}
```

**RAG injection approach (Claude's discretion resolved):** Soft prompt injection (few-shot prefix in system prompt) is preferred over structural placement. It produces more natural style transfer by letting the LLM internalize tone/voice patterns rather than copy-paste fragments verbatim.

### Pattern 8: SEO Constraint Validation

**What:** After draft generation, validate that all hard constraints are met before presenting to user.

```python
# Source: project requirements AUTH-05
import re

def _validate_draft(draft: str, keywords: list[str], min_words: int) -> dict[str, bool]:
    primary_keyword = keywords[0].lower() if keywords else ""
    lines = draft.split("\n")
    h1_lines = [l for l in lines if l.startswith("# ")]
    first_para = next((l for l in lines if l.strip() and not l.startswith("#")), "")

    # Find meta description (expect it as a specific Markdown section or HTML comment)
    meta_match = re.search(r"Meta[- ]?[Dd]escription[:\s]+(.+)", draft)
    meta_desc = meta_match.group(1).strip() if meta_match else ""

    word_count = len(draft.split())

    return {
        "keyword_in_h1": bool(h1_lines and primary_keyword in h1_lines[0].lower()),
        "keyword_in_first_para": primary_keyword in first_para.lower(),
        "meta_desc_length_ok": 150 <= len(meta_desc) <= 160,
        "word_count_ok": word_count >= min_words,
        "has_rag_fragments": True,  # injected by construction
    }
```

### Pattern 9: Metadata Log Save

**What:** After Checkpoint 2 approval, save article metadata to a dedicated SQLite table (not the LangGraph checkpoint DB).

```python
# Source: Python stdlib sqlite3
import sqlite3
from datetime import datetime

def save_metadata_node(state: AuthorState) -> dict:
    # Save to separate metadata DB, not the LangGraph checkpoint DB
    conn = sqlite3.connect("bond_metadata.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS metadata_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            published_date TEXT NOT NULL,
            mode TEXT NOT NULL,
            thread_id TEXT
        )
    """)
    conn.execute(
        "INSERT INTO metadata_log (topic, published_date, mode, thread_id) VALUES (?, ?, ?, ?)",
        (state["topic"], datetime.now().isoformat(), "author", state["thread_id"])
    )
    conn.commit()

    # Also store embedding in ChromaDB metadata collection for future DUPL-01 checks
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    embedding = model.encode([state["topic"]])[0].tolist()
    client = chromadb.PersistentClient(path="./bond_chroma")
    meta_collection = client.get_or_create_collection("metadata_log", configuration={"hnsw": {"space": "cosine"}})
    meta_collection.add(
        ids=[state["thread_id"]],
        embeddings=[embedding],
        metadatas=[{"title": state["topic"], "published_date": datetime.now().isoformat()}]
    )

    conn.close()
    return {"metadata_saved": True}
```

### Pattern 10: Test Harness (No Frontend)

**What:** CLI script that drives the graph through approve/reject decisions programmatically. Required because Phase 2 has no frontend.

```python
# Source: LangGraph HITL docs pattern
config = {"configurable": {"thread_id": "test-session-001"}}
initial_state = {
    "topic": "Jak zwiększyć ruch na blogu firmowym",
    "keywords": ["SEO blog", "content marketing"],
    "thread_id": "test-session-001",
    "search_cache": {},
    "cp1_iterations": 0,
    "cp2_iterations": 0,
    "metadata_saved": False,
}

# Step 1: run to first interrupt
result = graph.invoke(initial_state, config=config)
# result["__interrupt__"] contains what the interrupt surfaced

# Step 2: approve Checkpoint 1
result = graph.invoke(Command(resume={"approved": True}), config=config)

# Step 3: approve Checkpoint 2
result = graph.invoke(Command(resume={"approved": True}), config=config)
print(result["draft"])
```

### Graph Wiring Overview

```
START
  └─► duplicate_check_node
        ├─[no match or override=True]──► researcher_node
        └─[override=False]─────────────► END

researcher_node ──► structure_node ──► checkpoint_1_node
                                              │
                        ┌─[approved=True]─────┘
                        │
                        ▼
                     writer_node ──► checkpoint_2_node
                          ▲               │
                          │  [approved    │
                          └──  =False]────┘
                                         │
                                [approved=True]
                                         ▼
                               save_metadata_node ──► END
```

### Anti-Patterns to Avoid

- **Non-idempotent operations before interrupt():** The CRITICAL pitfall — when the graph resumes after an interrupt, the entire node re-executes from line 1. Any Exa API call or LLM call placed before `interrupt()` in the same node will fire again on resume. Solution: put the `interrupt()` call in a dedicated node with no other logic.
- **Multiple interrupt() calls in one node:** LangGraph matches resume values by index. If you have two `interrupt()` calls in one node and the first one fires, on resume it re-executes from the top and must encounter both interrupts in order again. This leads to subtle bugs. Solution: one interrupt per node.
- **Using MemorySaver instead of SqliteSaver:** MemorySaver loses state on process restart. This breaks session recovery (AUTH-08 requirement). Project decision is SqliteSaver from day 1.
- **Same SQLite file for checkpoints and Metadata Log:** The checkpoint DB is managed by LangGraph and has a fixed schema. The Metadata Log needs a separate table in a separate file to avoid conflicts.
- **Storing full Exa results in GraphState without size awareness:** LangGraph serializes the entire state to SQLite on every superstep. Large text blobs (full article text from Exa) inflate checkpoint size. Store only what downstream nodes need — summaries for the report, not full text.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HITL pause/resume | Custom event queue + polling | LangGraph `interrupt()` + `Command(resume=...)` | Built-in state serialization, durable across restarts, supports time-travel debugging |
| Graph state persistence | Custom JSON serialization to file | `SqliteSaver` (langgraph-checkpoint-sqlite) | Handles concurrent writes, serialization edge cases, superstep alignment |
| Multilingual text embeddings | Custom embedding pipeline | `sentence-transformers` + `paraphrase-multilingual-MiniLM-L12-v2` | 50+ language support, 384-dim cosine-optimized, same model as Phase 1 |
| Vector similarity search + metadata | Custom cosine similarity loop | ChromaDB `query()` with distance threshold | HNSW index for speed; metadata filtering built-in |
| Web research | Direct HTTP scraping | Exa `search_and_contents()` | Full-text extraction, AI summaries, language-matched results, no scraping complexity |
| SEO word count | Complex tokenizer | `len(text.split())` | Good enough for 800-word minimum check; does not need NLP tokenizer |

**Key insight:** LangGraph's interrupt system is not just a convenience — it handles the serialization, storage, and restoration of complete graph state at microsecond-level checkpoints. Building this from scratch would require weeks and would not be as reliable.

---

## Common Pitfalls

### Pitfall 1: Node Re-Execution on Resume
**What goes wrong:** Code before `interrupt()` in the same node executes twice — once when the graph first reaches the node, and again when the graph resumes after the human approves/rejects. API calls get double-billed. LLM calls produce different outputs (non-deterministic).

**Why it happens:** LangGraph resumes by re-running the entire node from the beginning, not from the line containing `interrupt()`.

**How to avoid:** Place `interrupt()` in a dedicated node with no other logic. All expensive operations belong in the preceding node. This is confirmed in LangGraph HITL docs.

**Warning signs:** Exa API usage metrics show double the expected calls; LLM generates a new draft each time the user opens the checkpoint.

### Pitfall 2: SqliteSaver Package Not Installed
**What goes wrong:** `ModuleNotFoundError: No module named 'langgraph.checkpoint.sqlite'` even though `langgraph` is installed.

**Why it happens:** In langgraph 0.2+, SqliteSaver moved to the separate `langgraph-checkpoint-sqlite` package. The import path is unchanged but the install is separate.

**How to avoid:** `pip install langgraph-checkpoint-sqlite`. Import remains `from langgraph.checkpoint.sqlite import SqliteSaver`.

**Warning signs:** Import error at graph compile time.

### Pitfall 3: ChromaDB Returns Distance, Not Similarity
**What goes wrong:** A `DUPLICATE_THRESHOLD` of 0.85 never matches anything (all distances are < 0.15 instead of > 0.85).

**Why it happens:** ChromaDB returns cosine DISTANCE (0 = identical, 2 = opposite), not cosine SIMILARITY (1 = identical, -1 = opposite). With normalized embeddings, cosine distance = 1 - cosine similarity.

**How to avoid:** Always convert: `similarity = 1.0 - distance` before comparing to threshold.

**Warning signs:** DUPL-01 check never triggers any warnings even for obviously identical topics.

### Pitfall 4: State Size Inflation from Full Exa Text
**What goes wrong:** LangGraph serializes entire state to SQLite at every superstep. Storing full article text (3000 chars × 8 results = 24KB) in state causes checkpoint bloat and slows serialization.

**Why it happens:** The `search_cache` dict stores everything passed from Exa, including `text` fields.

**How to avoid:** Strip `text` field from cache after generating the research report. Keep only `title`, `url`, `summary` in state. The full text is only needed for report generation, not for downstream nodes.

**Warning signs:** Checkpoint SQLite file grows to several MB after a few sessions.

### Pitfall 5: Thread ID Collision Between Test Runs
**What goes wrong:** Test harness reuses the same `thread_id`, causing the SqliteSaver to load stale state from a previous run instead of starting fresh.

**Why it happens:** SqliteSaver uses `thread_id` as the primary key — same ID = same session.

**How to avoid:** Generate a new UUID for each test run: `thread_id = str(uuid.uuid4())`. In production, generate per-session from the frontend.

**Warning signs:** Graph immediately sees stale research data from a previous run; first node produces unexpected output.

### Pitfall 6: Exa API Language Filtering (Understand, Don't Fight)
**What goes wrong:** Polish-language queries receive a mix of Polish and English results when building a report for a Polish blog.

**Why it happens:** Before Nov 2025, Exa returned mixed-language results. Since Nov 2025, language filtering is ON by default and cannot currently be disabled via a documented parameter.

**How to avoid:** This is now the correct behavior — Polish queries return Polish results. If English sources are wanted in a Polish-language pipeline, include `include_domains` to target specific English sites.

**Warning signs:** All results are in Polish when English sources were expected (or vice versa). This is not a bug in the implementation.

### Pitfall 7: Cp2 Iteration Counter Not Incrementing Correctly
**What goes wrong:** The soft iteration cap appears to trigger on iteration 2 instead of after iteration 3.

**Why it happens:** Off-by-one in the counter update. Counter starts at 0; if you increment before the interrupt, the first rejection sets it to 1, making iteration 2 look like "3rd attempt."

**How to avoid:** Increment `cp2_iterations` at the TOP of the checkpoint node only when `cp2_approved = False` is returned. Track: 0 = not yet at checkpoint, 1 = first rejection, 2 = second rejection, 3+ = soft cap warning territory.

---

## Code Examples

### Complete Graph Compilation with SqliteSaver

```python
# Source: pypi.org/project/langgraph-checkpoint-sqlite/ (v3.0.3)
import sqlite3
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from .state import AuthorState
from .nodes import (
    duplicate_check_node,
    researcher_node,
    structure_node,
    checkpoint_1_node,
    writer_node,
    checkpoint_2_node,
    save_metadata_node,
)

def build_author_graph() -> StateGraph:
    builder = StateGraph(AuthorState)

    builder.add_node("duplicate_check", duplicate_check_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("structure", structure_node)
    builder.add_node("checkpoint_1", checkpoint_1_node)
    builder.add_node("writer", writer_node)
    builder.add_node("checkpoint_2", checkpoint_2_node)
    builder.add_node("save_metadata", save_metadata_node)

    builder.add_edge(START, "duplicate_check")
    builder.add_conditional_edges(
        "duplicate_check",
        lambda s: "researcher" if s.get("duplicate_override") is not False else END,
    )
    builder.add_edge("researcher", "structure")
    builder.add_edge("structure", "checkpoint_1")
    builder.add_conditional_edges(
        "checkpoint_1",
        lambda s: "writer" if s.get("cp1_approved") else "structure",
    )
    builder.add_edge("writer", "checkpoint_2")
    builder.add_conditional_edges(
        "checkpoint_2",
        lambda s: "save_metadata" if s.get("cp2_approved") else "writer",
    )
    builder.add_edge("save_metadata", END)

    return builder

def compile_graph():
    builder = build_author_graph()
    checkpointer = SqliteSaver(
        sqlite3.connect("bond_checkpoints.db", check_same_thread=False)
    )
    return builder.compile(checkpointer=checkpointer)
```

### Exa Research with Summary

```python
# Source: pypi.org/project/exa-py/ (v2.4.0) + docs.exa.ai
from exa_py import Exa

exa = Exa(api_key=os.environ["EXA_API_KEY"])

response = exa.search_and_contents(
    query="content marketing dla B2B SaaS",   # Polish query → Polish results by default
    num_results=8,
    type="auto",
    text={"max_characters": 2000},             # full text for report synthesis
    summary={"query": "content marketing SaaS"},  # abstractive summary per result
)

for r in response.results:
    print(r.title)    # article title
    print(r.url)      # source URL
    print(r.summary)  # Gemini Flash generated summary
    print(r.text)     # full extracted markdown text
```

### astream_events for Token Streaming (Design Now for Phase 3)

```python
# Source: LangGraph streaming docs — confirmed version="v2" pattern
async def stream_graph(initial_state: dict, config: dict):
    async for event in graph.astream_events(initial_state, config=config, version="v2"):
        event_type = event["event"]
        if event_type == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield chunk.content   # stream token to frontend
        elif event_type == "on_chain_end":
            node_name = event.get("name")
            # Signal node completion to frontend progress indicator
            yield f"[NODE_COMPLETE:{node_name}]"
```

**Note:** Graph must be designed with `astream_events` in mind even in Phase 2, because Phase 3 will plug the same graph into FastAPI SSE without rewrites.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `from langgraph.checkpoint.sqlite import SqliteSaver` from `langgraph` base | Same import path, but requires `pip install langgraph-checkpoint-sqlite` separately | LangGraph 0.2.x (mid-2024) | Must add `langgraph-checkpoint-sqlite` to requirements.txt |
| `interrupt_before=["node_name"]` at compile time | `interrupt()` function called inside node body | LangGraph ~0.2.19 | `interrupt()` is more flexible — can pass arbitrary payload; preferred pattern |
| Mixed-language Exa results | Language-matched results by default | Exa, November 2025 | Polish queries return Polish results without configuration; no workaround needed |
| `astream_events(version="v1")` | `astream_events(version="v2")` | LangGraph streaming evolution | v2 is the current stable API for token streaming |

**Deprecated/outdated:**
- `MemorySaver`: Not deprecated but intentionally avoided — loses state on process restart, breaks HITL session recovery
- `interrupt_before` at compile: Superseded by `interrupt()` inside nodes (more expressive, passes arbitrary payload)
- `aiosqlite.connect()` directly: Use `AsyncSqliteSaver.from_conn_string()` class method instead

---

## Open Questions

1. **Exa API language filtering toggle**
   - What we know: Language filtering is ON by default since Nov 2025; documentation does not expose a parameter to disable it
   - What's unclear: Whether future exa-py versions will expose a `language` or `filter_language=False` parameter for mixed-language research
   - Recommendation: Implement the Researcher node without worrying about this; if a Polish blog needs English sources, use `include_domains` to target specific English domains explicitly

2. **DUPLICATE_THRESHOLD default value**
   - What we know: 0.85 cosine similarity is the project-flagged starting point; paraphrase-multilingual-MiniLM-L12-v2 produces 384-dim vectors
   - What's unclear: How the model distributes similarity scores for Polish blog topics (calibration requires real corpus data from Phase 1)
   - Recommendation: Start at 0.85 (low false-positive rate). After Phase 1 corpus is populated, run 10-20 topic pairs through the model and inspect distances before finalizing

3. **Exa rate limits and cost at 8 results/session**
   - What we know: Exa is on a free plan (per project docs); API has rate limits
   - What's unclear: Whether `summary=True` counts as extra tokens/credits; exact rate limit values
   - Recommendation: Implement session cache (AUTH-10) rigorously as the primary cost control; add a simple rate limit retry with exponential backoff in the Researcher node

4. **ChromaDB collection reuse from Phase 1**
   - What we know: Phase 1 creates the `style_corpus` collection; Phase 2 needs `metadata_log` collection
   - What's unclear: Whether Phase 1 has committed to specific ChromaDB `PersistentClient` path that Phase 2 must match
   - Recommendation: Standardize on `./bond_chroma` as the ChromaDB path; document in `config.py` as `CHROMA_PATH` env var

---

## Sources

### Primary (HIGH confidence)

- PyPI `langgraph-checkpoint-sqlite` v3.0.3 (January 2026) — version, install command, import path
- `https://docs.langchain.com/oss/python/langgraph/interrupts` — interrupt() API, Command(resume=...) pattern, SqliteSaver setup
- `https://docs.langchain.com/oss/python/langgraph/graph-api` — add_conditional_edges, routing functions, TypedDict state
- `https://docs.trychroma.com/docs/collections/configure` — HNSW cosine space configuration
- `https://pypi.org/project/exa-py/` — version 2.4.0 (Feb 2026), search_and_contents method, AsyncExa
- `https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` — 50-language support, 384-dim, cosine similarity
- GitHub issue `langchain-ai/langgraph#1253` — confirmed resolution of SqliteSaver package split

### Secondary (MEDIUM confidence)

- `https://exa.ai/docs/changelog/language-filtering-default` — language filtering ON by default since Nov 2025 (redirect confirmed; content verified)
- `https://exa.ai/docs/sdks/python-sdk-specification` — search_and_contents parameters (text, summary, highlights)
- LangGraph HITL Medium article (Data Science Collective) — interrupt() node re-execution behavior, idempotency requirement
- LangGraph Community Forum — multiple interrupt pitfalls, thread twice-execution issue

### Tertiary (LOW confidence — validate before implementing)

- DUPLICATE_THRESHOLD 0.85 value — flagged in STATE.md as "recommendation, not validated"; requires corpus calibration
- Exa free tier rate limits — not documented in public SDK; needs live testing

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified on PyPI with current versions; import paths confirmed via GitHub issues
- Architecture: HIGH — LangGraph patterns from official docs; Exa and ChromaDB patterns from official SDKs
- Pitfalls: HIGH (node re-execution, ChromaDB distance vs. similarity) — verified via official docs and GitHub issues; MEDIUM (Exa language, threshold calibration) — needs runtime validation

**Research date:** 2026-02-20
**Valid until:** 2026-03-22 (30 days — stable libraries; re-verify Exa changelog if exa-py updates beyond 2.4.0)
