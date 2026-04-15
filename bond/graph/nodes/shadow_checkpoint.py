"""Shadow checkpoint node — human review of generated style annotations.

Responsibility:
1. Pause the pipeline and surface annotations + corrected text for user review.
2. On "approve": advance to END.
3. On "reject": loop back to shadow_annotate with user feedback; increment iteration_count.
4. Hard-stop after HARD_CAP_ITERATIONS (3) rejections to prevent runaway cost loops.
5. On "abort": terminate pipeline immediately.

SHAD-04 compliance:
- iteration_count is incremented on each rejection.
- Hard cap at HARD_CAP_ITERATIONS terminates pipeline with hard_cap_message.
- Feedback is stored in shadow_feedback and read by shadow_annotate_node on re-run.
"""
from __future__ import annotations

import logging

from pydantic import ValidationError
from langgraph.types import interrupt, Command
from langgraph.graph import END

from bond.graph.state import BondState
from bond.schemas import CheckpointResponse

log = logging.getLogger(__name__)

HARD_CAP_ITERATIONS = 3


def shadow_checkpoint_node(state: BondState) -> dict | Command:
    """Pause for human review of shadow annotations.

    Surfaces: annotations, shadow_corrected_text, iteration_count.
    Resume format:
      Approve: {"action": "approve"}
      Reject:  {"action": "reject", "feedback": "Zbyt formalny ton w akapicie 2..."}
      Abort:   {"action": "abort"}

    On rejection: feedback is stored in shadow_feedback; graph routes back to
    shadow_annotate which incorporates the feedback on its next LLM call.
    Hard cap: after HARD_CAP_ITERATIONS rejections the pipeline terminates with
    a hard_cap_message.
    """
    iteration_count = state.get("iteration_count", 0)

    # Hard cap — abort shadow pipeline when iteration limit is reached
    if iteration_count >= HARD_CAP_ITERATIONS:
        log.warning(
            "shadow_checkpoint: hard cap reached — terminating pipeline after %d/%d iterations "
            "(thread_id=%s)",
            iteration_count,
            HARD_CAP_ITERATIONS,
            state.get("thread_id", "unknown"),
        )
        return Command(
            goto=END,
            update={
                "hard_cap_message": (
                    f"Przekroczono limit {HARD_CAP_ITERATIONS} iteracji korekty stylistycznej. "
                    "Ostatnia wersja adnotacji została zachowana."
                )
            },
        )

    user_response = interrupt({
        "checkpoint": "shadow_checkpoint",
        "type": "approve_reject",
        "annotations": state.get("annotations", []),
        "shadow_corrected_text": state.get("shadow_corrected_text", ""),
        "iteration_count": iteration_count,
        "instructions": (
            'Wyślij {"action": "approve"}, '
            '{"action": "reject", "feedback": "..."} '
            'lub {"action": "abort"} aby zakończyć pipeline.'
        ),
    })

    try:
        response = CheckpointResponse(**user_response)
    except ValidationError as exc:
        raise ValueError(f"Nieprawidłowa odpowiedź shadow_checkpoint: {exc}") from exc

    if response.action == "abort":
        return Command(goto=END)

    if response.action == "approve":
        return {"shadow_approved": True}

    # reject — loop back to shadow_annotate with feedback
    return Command(
        goto="shadow_annotate",
        update={
            "shadow_approved": False,
            "shadow_feedback": response.feedback or "",
            "iteration_count": iteration_count + 1,
        },
    )
