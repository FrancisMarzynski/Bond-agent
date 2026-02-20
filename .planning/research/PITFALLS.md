# Pitfalls & Anti-Patterns

**Domain:** LangGraph blog writing agent with RAG style mimicry
**Project:** Bond — Agent Redakcyjny
**Researched:** 2026-02-20
**Confidence:** MEDIUM — based on training data (cutoff August 2025) + PROJECT.md analysis

---

## Critical Pitfalls

### 1. RAG Corpus Too Small for Reliable Style Mimicry

**Warning signs:**
- Style retrievals keep returning the same 2-3 fragments
- Generated text sounds generic despite "style injection"
- Blind test results fail (KPI4) even after corpus loading

**Prevention:**
- Minimum viable corpus: 10+ full articles, chunked to ~300-500 tokens
- Chunk by paragraph, not by sentence or fixed character count — stylometric units are semantic
- Tag each chunk with: `source_type` (own/external), `author_id`, `article_id`, `date`
- Test retrieval quality BEFORE integrating with writer: manually check that top-3 results for a query are genuinely stylistically similar

**Phase:** Corpus ingestion pipeline (early Phase 1 — blocks everything else)

---

### 2. LangGraph State Blowup on Long Sessions

**Warning signs:**
- Memory usage grows unbounded across research → draft → correction cycles
- `MemorySaver` causes out-of-memory on long articles or many correction loops
- State serialization becomes slow (>1s) for simple operations

**Prevention:**
- Use `SqliteSaver` (not `MemorySaver`) from day one — even for MVP
- Keep research results as references (store to file/DB, put only path in state) not as raw strings in state
- Limit correction loop history: store only last N feedback messages in state, not full history
- Set explicit state schema with Pydantic models — untyped dicts accumulate garbage

```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_conn_string("bond_sessions.db")
graph = graph_builder.compile(checkpointer=checkpointer)
```

**Phase:** Phase 1 — core graph setup. Fix before first streaming integration.

---

### 3. Human-in-the-Loop Checkpoint Not Resuming Correctly

**Warning signs:**
- After user approves research report, graph re-runs research instead of continuing
- Frontend receives duplicate events on resume
- Thread ID collisions cause wrong session to resume

**Prevention:**
- Always pass the same `thread_id` for resume: `{"configurable": {"thread_id": session_id}}`
- Use `interrupt_before` on the node AFTER the checkpoint (not on the checkpoint itself)
- Test the full interrupt → frontend → resume cycle in isolation before wiring to UI
- Store `thread_id` in browser session storage, not component state (survives page refresh)

```python
graph = graph_builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["generate_draft"]  # pause before draft, await approval
)

# To resume after user approval:
graph.invoke(None, config={"configurable": {"thread_id": session_id}})
```

**Phase:** Phase 1 — Author mode HITL checkpoints.

---

### 4. Streaming Tokens Lost or Duplicated in React Frontend

**Warning signs:**
- Words appear out of order or repeat
- SSE connection drops mid-stream and reconnects from beginning
- Progress indicator shows 100% then resets

**Prevention:**
- Use `astream_events` (LangGraph v0.2+), not `astream` — event-based API handles reconnects
- Implement SSE `id:` field on each event so browser's `EventSource` can resume from last event
- Buffer partial tokens on backend before flushing — don't send single characters
- Test with slow network (Chrome DevTools throttling) before release

```python
# FastAPI endpoint
async def stream_article(request: ArticleRequest):
    async def generate():
        async for event in graph.astream_events(inputs, config=config, version="v2"):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"].content
                yield f"data: {json.dumps({'token': chunk})}\n\n"
    return EventSourceResponse(generate())
```

**Phase:** Phase with frontend integration (streaming UI).

---

### 5. Exa / Web Search Quality Issues for Polish-Language Queries

**Warning signs:**
- Research report contains mostly English sources for Polish blog topics
- Sources are irrelevant or low-quality (SEO spam sites)
- Research loop exceeds time budget (>2 min) due to poor result quality requiring re-queries

**Prevention:**
- Explicitly pass language hint in queries: append "po polsku" or "in Polish" or use Exa's `include_domains` parameter to prioritize Polish domains
- Implement source quality filter: exclude domains from a blocklist of known content farms
- Cache results per (query_hash, date) — don't re-call API for same query in same session (PROJECT.md requirement)
- Set `num_results=8` and filter down to top 5 by relevance after retrieval, not before

**Phase:** Phase with Researcher node implementation.

---

### 6. Duplicate Topic Detection False Positives / False Negatives

**Warning signs:**
- Agent blocks writing about "Python async" because it previously wrote about "Python basics" (false positive)
- Agent allows writing about "jak zbudować chatbota" when "chatbot tutorial Python" is already in log (false negative)

**Prevention:**
- Use embedding similarity for duplicate detection, not keyword matching
- Threshold tuning required: start at 0.85 cosine similarity — too low = false positives, too high = misses
- Store topic embedding in Metadata Log alongside text — reuse same embedding model as RAG corpus
- Expose threshold as configurable env var (`DUPLICATE_THRESHOLD=0.85`) so it can be tuned without code changes
- Show user the detected duplicate with original article title + date — let them override if context is different

**Phase:** Phase with Metadata Log implementation.

---

### 7. youtube-transcript-api Breaks Without Warning

**Warning signs:**
- Works in dev, fails in production for the same video
- "No transcript found" for videos that clearly have captions in YouTube UI
- Intermittent failures that resolve on retry

**Prevention:**
- Always request multiple language fallbacks: `["pl", "en", "a.pl", "a.en"]` (the `a.` prefix = auto-generated)
- Wrap in retry with exponential backoff — YouTube rate-limits transcript requests
- Add explicit error message to user: "This video doesn't have captions. Bond only supports videos with subtitles."
- Monitor GitHub issues for the library — it breaks when YouTube changes internal endpoints (happens ~2-3x per year)

```python
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound

def get_transcript(video_id: str) -> str | None:
    try:
        transcript = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["pl", "en", "a.pl", "a.en"]
        )
        return " ".join(t["text"] for t in transcript)
    except NoTranscriptFound:
        return None  # Signal to UI: show user-friendly error
```

**Phase:** Phase with YouTube pipeline (can be later phase).

---

### 8. LLM Context Window Overflow on Long Research + Draft Cycle

**Warning signs:**
- `ContextWindowExceededError` or silent truncation on long articles
- Research report + exemplar chunks + draft prompt exceeds model context
- Draft ignores research results (they were truncated from context)

**Prevention:**
- Budget context explicitly: Research report max 2000 tokens, exemplar chunks max 1500 tokens (3-5 × 300-500), draft prompt template max 500 tokens, leaving ~4000+ for actual generation
- Summarize research report before injecting into draft prompt — don't pass raw research to writer node
- Use Pydantic models for all state values with explicit length limits
- Test with longest realistic input (multiple search results, long topic) before shipping

**Phase:** Phase 1 — writer node integration.

---

### 9. Social Media Repurposing Ignores Platform Character Limits

**Warning signs:**
- X (Twitter) posts generated at 800 words
- LinkedIn posts that violate character limits and get cut off in preview
- Instagram captions missing hashtag structure

**Prevention:**
- Enforce limits in prompt template, not just description:
  - X: 280 characters (strict)
  - LinkedIn: 3000 characters (soft limit; optimal 1300)
  - Instagram: 2200 characters + 30 hashtags max
  - Facebook: practical limit ~400 characters for engagement
- Validate output length after generation, regenerate if exceeded (not just truncate — truncation destroys meaning)
- Test each platform variant independently before shipping repurposing feature

**Phase:** Phase with repurposing pipeline.

---

### 10. SEO Prompt Drift — Instructions Ignored in Long Drafts

**Warning signs:**
- H2 headings missing from long articles even when instructed
- Meta-description exceeds 160 characters
- Keywords front-loaded in first paragraph but absent from headings

**Prevention:**
- Put SEO constraints in a separate system prompt section, not inline with style instructions — competing instructions cancel each other
- Post-process: after generation, programmatically verify H1 presence, H2 count, meta-description length, first-paragraph keyword presence. If fails, regenerate the specific section only (not the whole article)
- Use structured output for draft metadata: `{"meta_description": "...", "h1": "...", "body": "..."}`

**Phase:** Phase with writer node (SEO-aware generation).

---

## Minor Pitfalls

| Pitfall | Quick Prevention |
|---------|-----------------|
| Hardcoded model names (`"gpt-4o"`) | Always use `os.environ["DRAFT_MODEL"]` — configurable without code change |
| Missing loading states in React | User thinks app is broken after 10s silence; add SSE heartbeat every 5s |
| Correction loop context loss | Pass full conversation history in state, not just last message; use `add_messages` reducer |
| Embedding model mismatch | Corpus indexed with model A, query uses model B — scores are meaningless; pin model in config |
| ChromaDB collection naming conflict | Use collection names like `bond_style_corpus_v1` with version suffix — makes migration easier |
| No session cleanup | Old SqliteSaver entries accumulate; add TTL or periodic cleanup for sessions older than 7 days |
| Pydantic v1/v2 mismatch | LangGraph requires Pydantic v2; if any dependency imports Pydantic v1, it causes silent validation failures |

---

## Phase Mapping

| Pitfall | Priority | Phase to Address |
|---------|----------|-----------------|
| RAG corpus too small | CRITICAL | Phase 1 — corpus ingestion |
| LangGraph state blowup | HIGH | Phase 1 — core graph setup |
| HITL checkpoint not resuming | HIGH | Phase 1 — Author mode |
| SSE streaming issues | HIGH | Phase with frontend |
| Exa quality for Polish | MEDIUM | Phase with Researcher node |
| Duplicate detection false pos/neg | MEDIUM | Phase with Metadata Log |
| youtube-transcript-api breaks | LOW | Phase with YouTube pipeline |
| Context window overflow | HIGH | Phase 1 — writer node |
| Social media char limits | MEDIUM | Phase with repurposing |
| SEO prompt drift | MEDIUM | Phase with writer node |

---

## Sources

- Project context: `.planning/PROJECT.md`
- Training data (August 2025): LangGraph GitHub issues, ChromaDB migration notes, Exa community discussions, LangChain streaming patterns, youtube-transcript-api GitHub issues
- Overall confidence: MEDIUM — patterns are well-established; specific API behaviors should be verified during implementation
