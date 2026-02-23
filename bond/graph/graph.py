import sqlite3
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from bond.graph.state import AuthorState
from bond.config import settings
from bond.graph.nodes.duplicate_check import duplicate_check_node as _duplicate_check_node
from bond.graph.nodes.researcher import researcher_node as _researcher_node
from bond.graph.nodes.structure import structure_node as _structure_node
from bond.graph.nodes.checkpoint_1 import checkpoint_1_node as _checkpoint_1_node
from bond.graph.nodes.writer import writer_node as _writer_node


def _checkpoint_2_node(state: AuthorState) -> dict:
    raise NotImplementedError("checkpoint_2_node not yet implemented (Plan 04)")


def _save_metadata_node(state: AuthorState) -> dict:
    raise NotImplementedError("save_metadata_node not yet implemented (Plan 04)")


# ---------------------------------------------------------------------------
# Dynamic node loader — Plans 02-04 register real implementations
# ---------------------------------------------------------------------------

_node_registry: dict = {
    "duplicate_check": _duplicate_check_node,
    "researcher": _researcher_node,
    "structure": _structure_node,
    "checkpoint_1": _checkpoint_1_node,
    "writer": _writer_node,
    "checkpoint_2": _checkpoint_2_node,
    "save_metadata": _save_metadata_node,
}


def register_node(name: str, fn) -> None:
    """Called by each nodes/*.py module to replace its stub."""
    _node_registry[name] = fn


# ---------------------------------------------------------------------------
# Routing functions (routing logic is stable — do not change in later plans)
# ---------------------------------------------------------------------------

def _route_after_duplicate_check(state: AuthorState) -> str:
    """Route to researcher unless user explicitly aborted the duplicate warning."""
    if state.get("duplicate_override") is False:
        return END
    return "researcher"


def _route_after_cp1(state: AuthorState) -> str:
    """Loop back to structure node on rejection; advance to writer on approval."""
    if state.get("cp1_approved"):
        return "writer"
    return "structure"


def _route_after_cp2(state: AuthorState) -> str:
    """Loop back to writer on rejection (soft cap enforced inside checkpoint_2 node);
    advance to save_metadata on approval."""
    if state.get("cp2_approved"):
        return "save_metadata"
    return "writer"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_author_graph() -> StateGraph:
    builder = StateGraph(AuthorState)

    # Register nodes (uses current registry — stubs until Plans 02-04 run)
    for name, fn in _node_registry.items():
        builder.add_node(name, fn)

    # Edges
    builder.add_edge(START, "duplicate_check")
    builder.add_conditional_edges(
        "duplicate_check",
        _route_after_duplicate_check,
        {"researcher": "researcher", END: END},
    )
    builder.add_edge("researcher", "structure")
    builder.add_edge("structure", "checkpoint_1")
    builder.add_conditional_edges(
        "checkpoint_1",
        _route_after_cp1,
        {"writer": "writer", "structure": "structure"},
    )
    builder.add_edge("writer", "checkpoint_2")
    builder.add_conditional_edges(
        "checkpoint_2",
        _route_after_cp2,
        {"save_metadata": "save_metadata", "writer": "writer"},
    )
    builder.add_edge("save_metadata", END)

    return builder


def compile_graph():
    """Compile the graph with SqliteSaver. check_same_thread=False is required."""
    import os
    os.makedirs(os.path.dirname(os.path.abspath(settings.checkpoint_db_path)), exist_ok=True)
    builder = build_author_graph()
    checkpointer = SqliteSaver(
        sqlite3.connect(settings.checkpoint_db_path, check_same_thread=False)
    )
    return builder.compile(checkpointer=checkpointer)
