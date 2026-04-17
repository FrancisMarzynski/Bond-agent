from typing import Literal, NotRequired, Optional, TypedDict


class Annotation(TypedDict):
    """Single style/grammar annotation produced by shadow_annotate_node."""
    id: str                     # stable unique ID, e.g. "ann_001"
    original_span: str          # exact verbatim text to replace
    replacement: str            # corrected replacement text
    reason: str                 # brief explanation referencing author's style
    start_index: int            # character start index of original_span in text (inclusive)
    end_index: int              # character end index of original_span in text (exclusive)


class BondState(TypedDict):
    # --- Routing ---
    mode: NotRequired[Literal["author", "shadow"]]  # omit → defaults to "author" branch

    # --- Author mode input ---
    topic: Optional[str]
    keywords: Optional[list[str]]
    thread_id: str
    context_dynamic: Optional[str]  # run-specific context supplied at pipeline start

    # --- Duplicate detection ---
    duplicate_match: Optional[dict]     # {"title": str, "date": str, "similarity": float} or None
    duplicate_override: Optional[bool]  # True = proceed; False = abort; None = no match

    # --- Research ---
    # search_cache keys are topic strings; values are list[dict] with title/url/summary
    # Full text is stripped after report generation to avoid state bloat (Pitfall 4)
    search_cache: dict
    research_report: Optional[str]      # formatted Markdown report (rendered from research_data)
    research_data: NotRequired[Optional[dict]]  # structured research output: {fakty, statystyki, zrodla}

    # --- Structure ---
    heading_structure: Optional[str]    # H1/H2/H3 outline as Markdown

    # --- Checkpoint 1 ---
    cp1_approved: Optional[bool]
    cp1_feedback: Optional[str]         # edited structure + optional note from user
    cp1_iterations: int                 # counts regeneration loops

    # --- Draft ---
    draft: Optional[str]                # full Markdown draft
    draft_validated: Optional[bool]     # True = passed all SEO constraint checks

    # --- Checkpoint 2 ---
    cp2_approved: Optional[bool]
    cp2_feedback: Optional[str]         # section-targeted feedback from user
    cp2_iterations: int                 # counts regeneration loops (soft cap at 3)

    # --- Output ---
    metadata_saved: bool

    # --- Shadow mode fields ---
    original_text: Optional[str]                # submitted text for style analysis
    annotations: Optional[list[Annotation]]     # style corrections produced by shadow_annotate
    shadow_corrected_text: Optional[str]        # full text with all annotations applied
    shadow_corpus_fragments: Optional[list[dict]]  # raw corpus fragments from shadow_analyze → shadow_annotate

    # --- Shadow mode checkpoint ---
    iteration_count: int                        # counts shadow annotation regeneration loops (hard cap at 3)
    shadow_approved: Optional[bool]             # True after user approves shadow corrections
    shadow_feedback: Optional[str]              # feedback from user when rejecting shadow annotations

    # --- Hard cap notification ---
    hard_cap_message: NotRequired[Optional[str]]  # set when pipeline aborts due to HARD_CAP_ITERATIONS

    # --- Token & cost tracking ---
    tokens_used_research: NotRequired[int]   # tokens consumed by researcher + structure nodes
    tokens_used_draft: NotRequired[int]      # tokens consumed by writer node (all retry attempts)
    estimated_cost_usd: NotRequired[float]   # running total estimated cost in USD


# Backward-compat alias — all existing Phase 2 node imports use AuthorState without modification
AuthorState = BondState
