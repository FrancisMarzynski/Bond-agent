"""Shadow analyze node — stub placeholder for Plan 04-01 full implementation.

Responsibility: Retrieve style corpus fragments relevant to the submitted text
via two-pass ChromaDB query (own text preferred, external as fill).
"""
from __future__ import annotations

import logging

from bond.graph.state import BondState

logger = logging.getLogger(__name__)


def shadow_analyze_node(state: BondState) -> dict:
    """Stub: returns empty corpus fragments until Plan 04-01 implements retrieval.

    Full implementation in Plan 04-01:
    - Embed original_text with paraphrase-multilingual-MiniLM-L12-v2
    - Pass 1: query bond_style_corpus_v1 WHERE source_type='own' (n=5)
    - Pass 2: fill remainder from external fragments
    - Return: {'shadow_corpus_fragments': list[dict]}
    """
    logger.warning(
        "shadow_analyze_node is a stub (Plan 04-01 not yet implemented). "
        "Returning empty corpus fragments — annotations will have no style reference."
    )
    return {"shadow_corpus_fragments": []}
