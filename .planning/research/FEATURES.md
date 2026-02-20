# Feature Landscape

**Domain:** AI Blog Writing Agent (dual-mode: Author + Shadow)
**Project:** Bond — Agent Redakcyjny
**Researched:** 2026-02-20
**Confidence:** MEDIUM — external research tools unavailable; based on training data (cutoff Aug 2025) + detailed PROJECT.md context. Competitive landscape may have shifted.

---

## Table Stakes

Features users expect from any AI writing tool. Missing = product feels incomplete or broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Long-form article generation (800+ words) | Core use case; any AI writer has this | Low | PROJECT.md mandates min. 800 words, H1/H2/H3, meta-description 150–160 chars |
| Markdown output | Standard format for CMS hand-off; all modern tools output Markdown | Low | Already in requirements |
| Topic + keyword input | Minimum viable prompt surface for content marketers | Low | Already in requirements |
| Web research with cited sources | Users expect grounded content, not hallucinated facts; Perplexity-style research is now table stakes | Medium | PROJECT.md: "raport z listą źródeł z linkami i streszczeniami"; use Exa MCP or Tavily |
| Inline feedback / regeneration loop | Users need to reject and iterate without starting over; all mature tools have this | Medium | PROJECT.md: "odrzucić draft i podać feedback — Agent regeneruje bez utraty kontekstu sesji" |
| SEO structure (headings, meta) | Marketers judge output by SEO compliance immediately | Low | Prompt-engineering approach is sufficient for MVP; no external SEO API needed |
| Progress indication for long operations | Without it, users assume the tool is broken after 30s; non-negotiable UX | Low | PROJECT.md: "progress indicator dla długich operacji" |
| Session context persistence | Losing context mid-session is a dealbreaker; all tools maintain thread state | Medium | LangGraph state/checkpointer handles this natively |
| Markdown editor / preview | Users need to read and lightly edit output inline; raw textarea is inadequate | Medium | PROJECT.md: "Edytor Markdown dla wygenerowanego contentu" |
| Mode selection UI | Without a clear Author / Shadow toggle, users are confused about what the agent does | Low | PROJECT.md: "przełącznik trybu Author/Shadow widoczny w głównym widoku czatu" |

---

## Differentiators

Features specific to Bond's competitive position. Not universally expected, but high value for this use case.

### Core Differentiators (Build in MVP)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| RAG-based style mimicry (Author's voice) | Virtually no competitor injects user-uploaded style exemplars into generation; output sounds like the author, not generic AI | High | Two source types: user's own texts + nominated external bloggers, tagged per source in vector metadata. Use cosine similarity to retrieve top 3–5 exemplar chunks. Critical for KPI4 (style indistinguishable in blind test). |
| Shadow mode (style review + annotation) | Rare feature: most tools only generate; review/correction against a personal style baseline is unique | High | Output = annotated original + corrected version. Must retrieve exemplars from same RAG store as Author mode. Dependency: RAG store must be populated before Shadow is useful. |
| Human-in-the-loop checkpoints (research approval + structure approval) | Competitors auto-proceed; Bond treats the human as decision-maker at each stage. Reduces rejection, increases trust. | Medium | Two mandatory checkpoints in Author flow: (1) approve research report + proposed H-structure, (2) approve final draft. LangGraph `interrupt` nodes are the right primitive. |
| Duplicate topic detection (Metadata Log) | No competitor tracks your own publication history and blocks re-coverage. Directly addresses a stated baseline problem. | Low-Medium | Simple SQL or JSON log. Check topic similarity before research starts (embedding similarity or keyword match). Configurable time window (e.g., 12 months). Critical for KPI3. |
| YouTube transcript → article pipeline | Bridges video and text content strategy; most tools need manual copy-paste of transcripts | Medium | `youtube-transcript-api` handles caption extraction. Works only for videos with captions. Generates blog article or summary in Markdown. |
| Social media repurposing (4 platforms) | Extends ROI of each article; saves 30–60 min of manual adaptation per article | Medium | Platforms: Facebook, LinkedIn, Instagram, X. Must respect character limits (X: 280, LinkedIn: 3000, Facebook: 63206, Instagram: 2200). Output Markdown only, no autopost. |
| Cascaded model selection (Mini for research, Frontier for draft) | Reduces cost by 60–80% vs using Frontier for everything, while maintaining quality where it matters | Medium | Configurable via env vars. Research/analysis = GPT-4o Mini or Claude Haiku. Final draft = GPT-4o or Claude Sonnet/Opus. |
| Onboarding RAG corpus from URLs + text paste | Lowers barrier for style corpus population; most RAG tools require file upload only | Medium | Accept: plain text paste, URL (scrape + chunk), ideally Google Drive link. Tag each chunk with source ID for attribution. |

### Secondary Differentiators (Build Post-MVP)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| CMS autopost (WordPress) | Removes last manual step; high user demand | Medium | Explicitly out of scope for MVP; consider Phase 2 |
| Image suggestion / alt-text generation | Visual content planning alongside article | Low-Medium | Out of scope for MVP |
| SEO API integration (Ahrefs, Semrush, Surfer) | Volume data for keyword selection; competitive gap analysis | High | Out of scope for MVP; SEO by prompt-engineering is sufficient initially |
| Multi-user workspace with permissions | Team use cases; approval routing | High | Out of scope for MVP (single-user assumed) |
| Fine-tuned style model | Higher fidelity style mimicry than RAG alone | Very High | Out of scope entirely; ICL + RAG is the stated constraint |

---

## Anti-Features

Features to explicitly NOT build. Building these would harm the product.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Auto-publish to CMS or social media | Bypasses human-in-the-loop, the core design principle; risk of publishing unreviewed AI content publicly | Output Markdown only; human copies and publishes manually. Consider CMS export in Phase 2. |
| Audio/video processing (Whisper, ffmpeg) | Adds significant infrastructure complexity for marginal gain; YouTube has captions for most relevant content | Use `youtube-transcript-api` for caption extraction only; document the captions-only limitation upfront |
| Fine-tuning or model training on user data | GDPR/privacy risk; enormous compute cost; violates project constraints | Use RAG + Few-Shot (ICL) exclusively for style adaptation |
| Real-time SEO data (keyword volume, SERP rank) | External API dependency adds cost, maintenance, API key management; complexity the team cannot support in MVP | Use prompt-engineering for SEO structure; document as a known gap |
| Multi-user accounts / role management | Doubles auth complexity; not needed for 1–2 users (CEO, marketing manager) | Single-user session; consider in Phase 2 if team grows |
| Content scheduling / calendar | Scope creep; Bond is a writing assistant, not a CMS | Keep Metadata Log minimal (topic + date only); let existing tools handle scheduling |
| AI image generation | Unrelated to text quality; adds cost and provider dependency | Out of scope entirely; document as deliberate omission |
| Chat history search / archive | Nice-to-have UX pattern from ChatGPT; not critical for MVP workflow | Store current session state; consider persistent history in Phase 2 |
| Grammar / plagiarism checker (Grammarly-style) | Commodity feature; adds external API dependency; not aligned with style-mimicry goal | Shadow mode covers style correction; rely on user's own review for grammar |

---

## Feature Dependencies

```
RAG Corpus (populated) → Style Mimicry in Author mode
RAG Corpus (populated) → Shadow mode corrections (quality degrades to zero without exemplars)
RAG Corpus → Onboarding flow (must run before any style-sensitive output)

Web Research (Exa/Tavily) → Research Report → [CHECKPOINT 1: User approves]
[CHECKPOINT 1 approved] → H-structure generation → [CHECKPOINT 1b: User approves structure]
[CHECKPOINT 1b approved] → Full draft generation → RAG style injection
Full draft → [CHECKPOINT 2: User approves]
[CHECKPOINT 2 approved] → Metadata Log write (topic + date)

Metadata Log → Duplicate topic check (must exist before Author mode first run)

YouTube transcript extraction → Article generation (same pipeline as Author, but no web research step)

Approved article (any source) → Repurposing pipeline → 4 platform variants

Cascaded model config → All generation nodes (Mini or Frontier selected per node type)
```

---

## MVP Recommendation

### Prioritize (Phase 1 core)

1. Author mode — full pipeline: web research, checkpoint, draft, RAG style injection, checkpoint
2. RAG style corpus — onboarding + retrieval (required for Author and Shadow to have value)
3. Duplicate topic detection — Metadata Log with similarity check
4. Human-in-the-loop checkpoints — LangGraph interrupt nodes at research and draft stages

### Prioritize (Phase 1 supporting)

5. Shadow mode — style review + annotated correction output
6. Basic chat UI — mode toggle, progress indicator, Markdown editor, approve/reject buttons

### Defer to Phase 2

- YouTube → Article pipeline (no blocking dependency; less critical than core writing loop)
- Social media repurposing (valuable but not the primary workflow)
- CMS autopost, image suggestions, SEO API integrations

**Rationale for deferral:** YouTube and repurposing extend the value of an article that already exists. The core value (draft in <4h, style fidelity, no duplicates) depends entirely on the Author + Shadow + RAG foundation. Ship the foundation first, validate KPIs 1–4, then add the distribution layer.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Table stakes | MEDIUM | Based on training data (Jasper, Writesonic, Copy.ai, Perplexity patterns as of Aug 2025). WebSearch unavailable. Core expectations unlikely to have changed significantly. |
| Differentiators | HIGH | Based directly on PROJECT.md requirements which are validated internally. RAG style mimicry + dual-mode + HITL is a genuinely rare combination. |
| Anti-features | HIGH | Based on PROJECT.md Out of Scope section + known complexity traps from training data. |
| Dependencies | HIGH | Based on logical analysis of the stated feature set; dependency chain is unambiguous. |

---

## Sources

- `.planning/PROJECT.md` — Primary source (project requirements, out-of-scope list, constraints, KPIs)
- Training data knowledge of: Jasper.ai, Writesonic, Copy.ai, MarketMuse, Surfer SEO, Perplexity AI, ChatGPT writing workflows (as of August 2025) — MEDIUM confidence, unverified against current state
- LangGraph documentation patterns for `interrupt` nodes and human-in-the-loop — HIGH confidence from training; verify with Context7 during implementation
- `youtube-transcript-api` Python library — MEDIUM confidence; verify version compatibility during implementation
