from typing import Optional, TypedDict


class AuthorState(TypedDict):
    # --- Input ---
    topic: str
    keywords: list[str]
    thread_id: str

    # --- Duplicate detection ---
    duplicate_match: Optional[dict]     # {"title": str, "date": str, "similarity": float} or None
    duplicate_override: Optional[bool]  # True = proceed; False = abort; None = no match

    # --- Research ---
    # search_cache keys are topic strings; values are list[dict] with title/url/summary
    # Full text is stripped after report generation to avoid state bloat (Pitfall 4)
    search_cache: dict
    research_report: Optional[str]      # formatted Markdown report

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
