from langgraph.types import interrupt

from bond.graph.state import AuthorState


def checkpoint_1_node(state: AuthorState) -> dict:
    """
    Checkpoint 1: pause for human review of research report and heading structure.

    Surfaces: research_report, heading_structure, cp1_iterations.
    Resume format:
      Approve: {"approved": True}
      Reject:  {"approved": False, "edited_structure": "# ...", "note": "Optional note"}

    On rejection: edited_structure + note are concatenated into cp1_feedback.
    structure_node reads cp1_feedback on its next run.
    """
    user_response = interrupt({
        "checkpoint": "checkpoint_1",
        "research_report": state.get("research_report", ""),
        "heading_structure": state.get("heading_structure", ""),
        "cp1_iterations": state.get("cp1_iterations", 0),
        "instructions": (
            "Zatwierdź lub odrzuć raport i strukturę nagłówków. "
            "Przy odrzuceniu: edytuj strukturę nagłówków bezpośrednio i dodaj opcjonalną notatkę."
        ),
    })

    if user_response.get("approved"):
        return {"cp1_approved": True}

    # Rejection: concatenate edited structure + note into cp1_feedback
    edited_structure = user_response.get("edited_structure", state.get("heading_structure", ""))
    note = user_response.get("note", "")
    feedback = edited_structure
    if note:
        feedback = f"{edited_structure}\n\nUwaga: {note}"

    return {
        "cp1_approved": False,
        "cp1_feedback": feedback,
        "cp1_iterations": state.get("cp1_iterations", 0) + 1,
    }
