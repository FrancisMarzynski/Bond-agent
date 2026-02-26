from pydantic import ValidationError
from langgraph.types import interrupt, Command
from langgraph.graph import END

from bond.graph.state import AuthorState
from bond.schemas import CheckpointResponse

SOFT_CAP_ITERATIONS = 3


def checkpoint_2_node(state: AuthorState) -> dict | Command:
    """
    Checkpoint 2: pause for human review of the stylized draft.

    Surfaces: draft, draft_validated, cp2_iterations.
    Resume format:
      Approve: {"action": "approve"}
      Reject:  {"action": "reject", "feedback": "Sekcja 'Jak zacząć' jest zbyt ogólna..."}
      Abort:   {"action": "abort"}

    Response is validated through CheckpointResponse — rejects strings like "false"
    or "tak" that would pass a naive truthy check on 'approved'.

    Soft cap: after SOFT_CAP_ITERATIONS rejections, continue with a warning (no hard block).
    Targeted revision: cp2_feedback passed to writer_node to revise flagged sections only.
    On abort: returns Command(goto=END), terminating the pipeline immediately.
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
            'Wyślij {"action": "approve"}, '
            '{"action": "reject", "feedback": "..."} '
            'lub {"action": "abort"} aby zakończyć pipeline.'
        ),
    }

    # Soft cap warning (does NOT block — user can still reject/approve/abort)
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

    try:
        response = CheckpointResponse(**user_response)
    except ValidationError as exc:
        raise ValueError(f"Nieprawidłowa odpowiedź checkpoint_2: {exc}") from exc

    if response.action == "abort":
        return Command(goto=END)

    if response.action == "approve":
        return {"cp2_approved": True}

    # reject — capture targeted feedback for writer_node
    return {
        "cp2_approved": False,
        "cp2_feedback": response.feedback or "",
        "cp2_iterations": cp2_iterations + 1,
    }
