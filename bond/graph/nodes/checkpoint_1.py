from pydantic import ValidationError
from langgraph.types import interrupt, Command
from langgraph.graph import END

from bond.graph.state import AuthorState
from bond.schemas import CheckpointResponse


def checkpoint_1_node(state: AuthorState) -> dict | Command:
    """
    Checkpoint 1: pause for human review of research report and heading structure.

    Surfaces: research_report, heading_structure, cp1_iterations.
    Resume format:
      Approve: {"action": "approve"}
      Reject:  {"action": "reject", "edited_structure": "# ...", "note": "Optional note"}
      Abort:   {"action": "abort"}

    Response is validated through CheckpointResponse — rejects strings like "false"
    or "tak" that would pass a naive truthy check on 'approved'.

    On rejection: edited_structure + note are concatenated into cp1_feedback.
    structure_node reads cp1_feedback on its next run.
    On abort: returns Command(goto=END), terminating the pipeline immediately.
    """
    user_response = interrupt({
        "checkpoint": "checkpoint_1",
        "research_report": state.get("research_report", ""),
        "heading_structure": state.get("heading_structure", ""),
        "cp1_iterations": state.get("cp1_iterations", 0),
        "instructions": (
            'Wyślij {"action": "approve"}, '
            '{"action": "reject", "edited_structure": "# ...", "note": "..."} '
            'lub {"action": "abort"} aby zakończyć pipeline.'
        ),
    })

    try:
        response = CheckpointResponse(**user_response)
    except ValidationError as exc:
        raise ValueError(f"Nieprawidłowa odpowiedź checkpoint_1: {exc}") from exc

    if response.action == "abort":
        return Command(goto=END)

    if response.action == "approve":
        return {"cp1_approved": True}

    # reject — concatenate edited structure + note into cp1_feedback
    edited = response.edited_structure or state.get("heading_structure", "")
    note = response.note or ""
    feedback = f"{edited}\n\nUwaga: {note}" if note else edited

    return {
        "cp1_approved": False,
        "cp1_feedback": feedback,
        "cp1_iterations": state.get("cp1_iterations", 0) + 1,
    }
