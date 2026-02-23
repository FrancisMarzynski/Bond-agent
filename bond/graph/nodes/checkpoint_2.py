from langgraph.types import interrupt

from bond.graph.state import AuthorState

SOFT_CAP_ITERATIONS = 3


def checkpoint_2_node(state: AuthorState) -> dict:
    """
    Checkpoint 2: pause for human review of the stylized draft.

    Surfaces: draft, draft_validated, cp2_iterations.
    Resume format:
      Approve: {"approved": True}
      Reject:  {"approved": False, "feedback": "Sekcja 'Jak zacząć' jest zbyt ogólna..."}

    Soft cap: after SOFT_CAP_ITERATIONS rejections, continue with a warning (no hard block).
    Targeted revision: cp2_feedback passed to writer_node to revise flagged sections only.
    """
    cp2_iterations = state.get("cp2_iterations", 0)
    draft_validated = state.get("draft_validated", True)

    # Build interrupt payload
    interrupt_payload = {
        "checkpoint": "checkpoint_2",
        "draft": state.get("draft", ""),
        "draft_validated": draft_validated,
        "cp2_iterations": cp2_iterations,
        "instructions": (
            "Zatwierdź lub odrzuć draft. Przy odrzuceniu: wskaż konkretne sekcje do poprawki — "
            "pozostałe sekcje zostaną zachowane bez zmian."
        ),
    }

    # Soft cap warning (does NOT block — user can still reject/approve)
    if cp2_iterations >= SOFT_CAP_ITERATIONS:
        interrupt_payload["warning"] = (
            f"Uwaga: przekroczono {SOFT_CAP_ITERATIONS} iteracje poprawek. "
            "Możesz kontynuować lub zatwierdzić obecną wersję."
        )

    # Add draft_validated failure details if present
    if not draft_validated:
        interrupt_payload["validation_warning"] = (
            "Draft nie spełnia wszystkich wymogów SEO po automatycznych poprawkach. "
            "Rozważ zatwierdzenie i ręczną edycję lub odrzuć z feedbackiem."
        )

    user_response = interrupt(interrupt_payload)

    if user_response.get("approved"):
        return {"cp2_approved": True}

    # Rejection: capture targeted feedback for writer_node
    feedback = user_response.get("feedback", "")
    return {
        "cp2_approved": False,
        "cp2_feedback": feedback,
        "cp2_iterations": cp2_iterations + 1,
    }
