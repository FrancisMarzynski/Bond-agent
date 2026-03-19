"""Shadow annotate node — stub placeholder for Plan 04-01 full implementation.

Responsibility: Call DRAFT_MODEL LLM with structured output to generate style
annotations and assemble the corrected text.
"""
from __future__ import annotations

import logging

from bond.graph.state import BondState

logger = logging.getLogger(__name__)


def shadow_annotate_node(state: BondState) -> dict:
    """Stub: returns empty annotations until Plan 04-01 implements LLM call.

    Full implementation in Plan 04-01:
    - Build prompt from original_text + corpus fragments + prior rejected annotations
    - Call ChatOpenAI(model=DRAFT_MODEL).with_structured_output(AnnotationResult)
    - Apply all annotations via substring replacement to produce corrected_text
    - Track annotation status (new/modified/unchanged) for frontend highlighting
    - Return: {
        'annotations': list[Annotation],
        'shadow_corrected_text': str,
        'shadow_previous_annotations': list[dict],
      }
    """
    logger.warning(
        "shadow_annotate_node is a stub (Plan 04-01 not yet implemented). "
        "Returning empty annotations and unmodified original text."
    )
    return {
        "annotations": [],
        "shadow_corrected_text": state.get("original_text", ""),
    }
